"""
离线批量 sim：在 307 家大市场里真跑 N 次 SimulationEngine，聚合成一份新的平行春招报告。

用法（在 backend/ 目录下跑，或脚本内部已把 backend 加进 sys.path）：
    export LLM_PROVIDERS=deepseek
    export LLM_TIER_PRIMARY=deepseek:deepseek-chat
    export LLM_TIER_SECONDARY=deepseek:deepseek-chat
    export LLM_TIER_BACKGROUND=deepseek:deepseek-chat
    export DEEPSEEK_API_KEY=$(grep '^DEEPSEEK_API_KEY=' /root/智联AI比赛/.env | cut -d= -f2)
    python3 scripts/big_market_sim.py --n 30 --concurrency 10 --competitors 50

设计要点：
- 不改 app/simulation、app/agents 核心逻辑，只是外部脚本调用它们。
- 真跑：每次 SimulationEngine.run() 跑满 13 周（除非提前接 offer）。
- 并发用 asyncio.Semaphore 控 8-12 路；单 sim 超时丢弃，不炸整批。
- 复用 backend/app/api/aggregator.py 的聚合函数，保证和线上口径一致。
- demo 候选人 = 线上 "使用 Demo 数据" 按钮那个王明（C9 计算机硕士），
  这样新报告是"同一个人在更大市场里"的结果，可与旧 49 家小市场对比。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

# 把 backend 加进 import path（脚本可从任意 cwd 跑）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.llm import init_router, get_router, get_llm_usage, shutdown_router  # noqa: E402
from app.simulation.engine import SimulationEngine  # noqa: E402
from app.simulation.state import init_sim_state  # noqa: E402
from app.simulation.outcome import SimOutcome  # noqa: E402
from app.models.candidate import (  # noqa: E402
    CandidateHiddenSignals,
    CandidateProfile,
    EducationExperience,
    JobExpectation,
    OfficialCV,
    SchoolTier,
)
from app.models.company import CompanyProfile  # noqa: E402

from app.api.aggregator import (  # noqa: E402
    aggregate_outcomes,
    offer_count_distribution,
    company_offer_probability,
    acceptance_week_timeline,
)

COMPANIES_FILE = BACKEND / "data" / "companies" / "companies_v1.json"
PERSONAS_FILE = BACKEND / "data" / "personas" / "competitors_v1.json"
OUT_DIR = BACKEND / "data" / "sim_runs"


def load_companies() -> list[CompanyProfile]:
    raw = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    return [CompanyProfile.model_validate(c) for c in raw]


def load_personas() -> list[CandidateProfile]:
    raw = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    return [CandidateProfile.model_validate(p) for p in raw]


def build_demo_candidate() -> CandidateProfile:
    """复刻 routes.py 里 "使用 Demo 数据" 按钮构造的那个王明。

    对齐 _bootstrap_candidate_from_summary 在 demo 分支的口径：
    - summary: 王明 / 某 C9 院校 / 计算机科学与技术 / 目标算法+AI应用
    - llm_degree = "硕士"，scores 为空（走 985_top 学校档默认基线）
    这样离线跑出来的候选人 hidden_signals 与线上 demo 完全一致。
    """
    school_tier = SchoolTier.TIER_985_TOP
    # 985_top 默认基线（照抄 routes._bootstrap_candidate_from_summary）
    base_quality = 80
    default_proj, default_intern, default_achv = 78, 65, 55
    default_gpa, default_comm = 75, 70
    resolved_degree = "硕士"

    edu = EducationExperience(
        school="某 C9 院校",
        degree=resolved_degree,
        major="计算机科学与技术",
        period="2022.09 - 2026.06",
    )
    cv = OfficialCV(
        resume_quality=base_quality,
        name="王明",
        gender="未知",
        job_status="应届",
        age=23,
        work_years="应届",
        highest_degree=resolved_degree,
        current_address="北京",
        job_expectation=JobExpectation(
            target_industries=["互联网/科技", "人工智能"],
            target_roles=["算法工程师", "AI 应用工程师"],
            target_cities=["北京", "上海"],
            min_salary="20-30k·14薪",
        ),
        education_history=[edu],
        personal_strengths="技术扎实，项目经历丰富",
        certificates=[],
    )
    hidden = CandidateHiddenSignals(
        school_tier=school_tier,
        gpa_percentile=default_gpa,
        project_strength=default_proj,
        internship_strength=default_intern,
        achievements_strength=default_achv,
        communication_score=default_comm,
        stress_tolerance=70,
        overwork_tolerance=60,
    )
    return CandidateProfile(
        candidate_id="demo-wangming-bigmarket",
        is_primary=True,
        official_cv=cv,
        hidden_signals=hidden,
    )


def mutate_candidate(base: CandidateProfile, project_delta: int = 0,
                     resume_quality_delta: int = 0) -> CandidateProfile:
    """反事实：真改候选人的 hidden_signals / resume_quality，再真跑 sim。

    不是 aggregator 里写死的线性 sensitivity 系数，而是把新数值喂回 SimulationEngine 重跑。
    """
    c = base.model_copy(deep=True)
    if project_delta:
        c.hidden_signals.project_strength = max(0, min(100, c.hidden_signals.project_strength + project_delta))
    if resume_quality_delta:
        c.official_cv.resume_quality = max(0, min(100, c.official_cv.resume_quality + resume_quality_delta))
    # 反事实候选人换个 id，避免和基线混淆
    c.candidate_id = base.candidate_id + f"-cf-p{project_delta}-r{resume_quality_delta}"
    return c


async def run_batch(candidate: CandidateProfile, companies, personas,
                    n_runs: int, concurrency: int, competitors: int,
                    base_seed: int, tag: str,
                    max_retries: int = 2, per_sim_timeout: int = 300) -> tuple[list[SimOutcome], dict]:
    """真跑 n_runs 次 SimulationEngine。返回 (成功 outcomes, 运行元数据)"""
    router = get_router()
    sem = asyncio.Semaphore(concurrency)
    outcomes: list[SimOutcome] = []
    durations: list[float] = []
    failures: list[dict] = []

    async def one_sim(idx: int) -> None:
        async with sem:
            for attempt in range(max_retries + 1):
                # 每次 attempt 换 seed 分量，重试不完全重复相同的随机路径
                rng = random.Random(base_seed + idx * 1000 + attempt)
                state = init_sim_state(
                    candidate,
                    companies,
                    personas,
                    sim_id=f"{tag}#{idx}",
                    num_competitors=competitors,
                    rng=rng,
                )
                engine = SimulationEngine(router, state, rng=rng)
                t0 = time.perf_counter()
                try:
                    outcome = await asyncio.wait_for(engine.run(), timeout=per_sim_timeout)
                    dt = time.perf_counter() - t0
                    durations.append(dt)
                    outcomes.append(outcome)
                    print(f"[{tag}] sim #{idx} 完成 (attempt {attempt}): "
                          f"apps={outcome.total_applications} interviews={outcome.total_interviews} "
                          f"offers={outcome.total_offers} dest={outcome.final_destination_company or '未签约'} "
                          f"salary={outcome.final_salary_wan} week={outcome.final_week_when_settled} "
                          f"{dt:.1f}s", flush=True)
                    return
                except asyncio.TimeoutError:
                    print(f"[{tag}] sim #{idx} 超时 {per_sim_timeout}s (attempt {attempt})", flush=True)
                    if attempt == max_retries:
                        failures.append({"idx": idx, "reason": "timeout"})
                except Exception as e:  # noqa: BLE001
                    print(f"[{tag}] sim #{idx} 异常 (attempt {attempt}): {e}", flush=True)
                    if attempt == max_retries:
                        failures.append({"idx": idx, "reason": str(e)})
                    else:
                        await asyncio.sleep(2 ** attempt)

    batch_t0 = time.perf_counter()
    await asyncio.gather(*[one_sim(i) for i in range(n_runs)])
    batch_dt = time.perf_counter() - batch_t0

    meta = {
        "n_requested": n_runs,
        "n_succeeded": len(outcomes),
        "n_failed": len(failures),
        "failures": failures,
        "concurrency": concurrency,
        "competitors_per_sim": competitors,
        "total_wall_sec": round(batch_dt, 1),
        "per_sim_sec": {
            "min": round(min(durations), 1) if durations else 0,
            "max": round(max(durations), 1) if durations else 0,
            "mean": round(sum(durations) / len(durations), 1) if durations else 0,
        },
    }
    return outcomes, meta


def aggregate_report(label: str, outcomes: list[SimOutcome], all_codes: list[str],
                     target_n: int) -> dict:
    """用线上同一套 aggregator 聚合成报告 dict"""
    agg = aggregate_outcomes(label, outcomes, target_n=target_n)
    return {
        "label": label,
        "n_real_sims": len(outcomes),
        "aggregate": agg.model_dump(mode="json"),
        "offer_count_distribution": offer_count_distribution(outcomes, target_n),
        "company_offer_probability": [
            p.model_dump(mode="json")
            for p in company_offer_probability(outcomes, all_codes, top_n=15)
        ],
        "acceptance_week_timeline": [
            p.model_dump(mode="json") for p in acceptance_week_timeline(outcomes, target_n)
        ],
        # 也存原始 outcome 关键 metric，便于事后核对（不是聚合，是真实每次）
        "raw_outcomes": [
            {
                "sim_id": o.sim_id,
                "total_applications": o.total_applications,
                "total_interviews": o.total_interviews,
                "total_offers": o.total_offers,
                "final_destination_company": o.final_destination_company,
                "final_salary_wan": o.final_salary_wan,
                "final_week_when_settled": o.final_week_when_settled,
            }
            for o in outcomes
        ],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="真跑几次基线 sim")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--competitors", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260701)
    ap.add_argument("--target-n", type=int, default=1000, help="聚合表征次数")
    ap.add_argument("--counterfactual", action="store_true",
                    help="额外真跑反事实（项目+15 / 简历质量-20）")
    ap.add_argument("--cf-n", type=int, default=15, help="每个反事实变体真跑几次")
    args = ap.parse_args()

    init_router()
    router = get_router()
    print("LLM 路由:", router.describe_routing(), flush=True)

    companies = load_companies()
    personas = load_personas()
    all_codes = [c.code_name for c in companies]
    print(f"市场规模: {len(companies)} 家公司 / {len(personas)} 竞争者池", flush=True)

    candidate = build_demo_candidate()
    print(f"候选人: {candidate.official_cv.name} / {candidate.hidden_signals.school_tier.value} / "
          f"{candidate.official_cv.highest_degree}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    report: dict = {
        "generated_at": ts,
        "market": {"companies": len(companies), "competitor_pool": len(personas)},
        "candidate": {
            "name": candidate.official_cv.name,
            "school": candidate.official_cv.education_history[0].school,
            "school_tier": candidate.hidden_signals.school_tier.value,
            "degree": candidate.official_cv.highest_degree,
            "hidden_signals": candidate.hidden_signals.model_dump(mode="json"),
            "resume_quality": candidate.official_cv.resume_quality,
        },
        "config": {
            "n_runs": args.n,
            "concurrency": args.concurrency,
            "competitors_per_sim": args.competitors,
            "target_n": args.target_n,
            "seed": args.seed,
        },
    }

    # ===== 基线 =====
    print("\n===== 基线批次开始 =====", flush=True)
    base_outcomes, base_meta = await run_batch(
        candidate, companies, personas,
        n_runs=args.n, concurrency=args.concurrency, competitors=args.competitors,
        base_seed=args.seed, tag="base",
    )
    report["baseline_run_meta"] = base_meta
    if not base_outcomes:
        print("!! 基线一次都没成功，退出", flush=True)
        report["baseline_report"] = None
    else:
        report["baseline_report"] = aggregate_report(
            "原始（王明·大市场）", base_outcomes, all_codes, args.target_n
        )

    # ===== 反事实（可选）=====
    if args.counterfactual and base_outcomes:
        print("\n===== 反事实：项目含金量 +15 =====", flush=True)
        cand_p15 = mutate_candidate(candidate, project_delta=15)
        p15_outcomes, p15_meta = await run_batch(
            cand_p15, companies, personas,
            n_runs=args.cf_n, concurrency=args.concurrency, competitors=args.competitors,
            base_seed=args.seed + 777, tag="cf_proj15",
        )
        report["cf_project_plus15"] = {
            "run_meta": p15_meta,
            "report": aggregate_report("项目含金量 +15", p15_outcomes, all_codes, args.target_n)
            if p15_outcomes else None,
            "candidate_project_strength": cand_p15.hidden_signals.project_strength,
        }

        print("\n===== 反事实：简历质量 -20 =====", flush=True)
        cand_r20 = mutate_candidate(candidate, resume_quality_delta=-20)
        r20_outcomes, r20_meta = await run_batch(
            cand_r20, companies, personas,
            n_runs=args.cf_n, concurrency=args.concurrency, competitors=args.competitors,
            base_seed=args.seed + 999, tag="cf_resume-20",
        )
        report["cf_resume_minus20"] = {
            "run_meta": r20_meta,
            "report": aggregate_report("简历质量 -20", r20_outcomes, all_codes, args.target_n)
            if r20_outcomes else None,
            "candidate_resume_quality": cand_r20.official_cv.resume_quality,
        }

    report["llm_usage"] = get_llm_usage()

    out_file = OUT_DIR / f"big_market_report_{ts}.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out_file}", flush=True)
    print("LLM 消耗:", get_llm_usage(), flush=True)

    await shutdown_router()


if __name__ == "__main__":
    asyncio.run(main())
