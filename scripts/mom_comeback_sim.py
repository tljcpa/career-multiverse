"""
"28岁全职宝妈绝境求生"高光案例：在 307 家大市场里真跑基线 + 反事实，拿真数字。

对应 _agy碾压洞察.txt 第2节剧本：
  1. 背景：28岁女性，文科背景，2年全职带娃职业空窗，目标项目管理岗
  2. 第一次跑（残酷现实）：基线画像真跑 N 次
  3. 反事实滑块：
     - 目标企业规模：大厂 -> 创业公司/中小公司（size 表达收窄到 STARTUP/SMALL）
     - 核心竞争力重构：不编造经历，只是把"两年带娃"如实对应到的软性维度提升
       （多线程协调/危机处理 -> communication_score + stress_tolerance +
        achievements_strength 小幅提升，因为筛选/面试 agent 实际读取的是这些
        hidden_signals，不是 personal_strengths 自由文本，engine 里没有读取
        personal_strengths，所以"重构叙事"必须落到这些真实被消费的字段上）
     - 预期薪资 -10%
  4. 第二次跑（翻盘 or 如实报告不及预期）

不改 app/simulation、app/agents 核心逻辑，只是外部脚本调用，复用
backend/app/api/aggregator.py 保证口径和线上一致。

用法：
    export LLM_PROVIDERS=deepseek
    export LLM_TIER_PRIMARY=deepseek:deepseek-chat
    export LLM_TIER_SECONDARY=deepseek:deepseek-chat
    export LLM_TIER_BACKGROUND=deepseek:deepseek-chat
    export DEEPSEEK_API_KEY=$(grep '^DEEPSEEK_API_KEY=' /root/智联AI比赛/.env | cut -d= -f2)
    python3 scripts/mom_comeback_sim.py --n 20 --cf-n 20 --concurrency 8 --competitors 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

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
    WorkExperience,
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


# ============================================================
# 全局限流补丁（只在本脚本内生效，不改核心 llm.py）
#
# 背景：DeepSeek 余额耗尽后改用 NVIDIA 免费层，免费层 RPM 很低，
# 高并发直接 429 -> 全量降级到规则决策 -> sim 结果失真（人人 0 offer）。
# 单个 sim 内部一周会并发 fire 多路 HR/interviewer LLM 调用，
# 叠加 sim 之间的并发，瞬时在飞请求数远超免费层配额。
#
# 解决：给 router.generate 包一层"全局信号量 + 429 感知的长退避"，
# 把整个进程的在飞 LLM 请求数硬压到 LLM_GLOBAL_CONCURRENCY（默认 2）。
# 这是纯粹的限流，不改任何业务/agent/engine 逻辑。
# ============================================================


def install_global_llm_throttle(router, *, max_inflight: int, max_retries: int = 8,
                                min_interval_sec: float = 0.0) -> None:
    """给 router.generate 包一层限流。

    两个旋钮：
    - max_inflight: 同时在飞的请求数上限（信号量）
    - min_interval_sec: 相邻两次请求"开始"之间的最小间隔（速率配速）。
      NVIDIA 免费层实测是 rolling RPM 预算（约 30 RPM），突发会立刻 429，
      但每 ~2s 一发就能稳定 200。所以真正的解法是配速，不只是限并发。
    """
    import random as _random

    sem = asyncio.Semaphore(max_inflight)
    pace_lock = asyncio.Lock()
    state = {"next_allowed": 0.0}

    async def _pace() -> None:
        if min_interval_sec <= 0:
            return
        async with pace_lock:
            now = asyncio.get_event_loop().time()
            wait = state["next_allowed"] - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = asyncio.get_event_loop().time()
            state["next_allowed"] = now + min_interval_sec

    orig_generate = router.generate

    async def throttled_generate(*args, **kwargs):
        last_err = None
        for attempt in range(max_retries):
            async with sem:
                await _pace()
                try:
                    return await orig_generate(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    msg = str(e)
                    is_429 = "429" in msg or "Too Many Requests" in msg
            # 退避放在 sem 之外，释放名额给别人，避免死等
            if attempt < max_retries - 1:
                if is_429:
                    # 429 用更长的退避 + 抖动：3s, 6s, 12s, 24s...（封顶 30s）
                    delay = min(30.0, 3.0 * (2 ** attempt)) + _random.uniform(0, 1.5)
                else:
                    delay = min(10.0, 1.0 * (2 ** attempt)) + _random.uniform(0, 0.5)
                await asyncio.sleep(delay)
        raise last_err if last_err else RuntimeError("throttled_generate 未知失败")

    router.generate = throttled_generate


def load_companies() -> list[CompanyProfile]:
    raw = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    return [CompanyProfile.model_validate(c) for c in raw]


def load_personas() -> list[CandidateProfile]:
    raw = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    return [CandidateProfile.model_validate(p) for p in raw]


# ============================================================
# персона: 28岁全职宝妈，文科背景，目标项目管理岗
# ============================================================


def build_mom_candidate_baseline() -> CandidateProfile:
    """基线画像：真实、不夸张。

    设定依据（对齐 agy 剧本"背景引入"）：
    - 28 岁，女性，文科背景（汉语言文学），本科，双非一本
    - 2 年全职带娃职业空窗（work_years 如实写"2年空窗后重返"，不编造经历）
    - 目标：项目管理岗（市场上纯"项目管理"JD 极少，扩展到"产品/运营"类
      校招-社招混合岗位，这是候选人真实会投的岗位范围）
    - 目标企业规模：偏好大厂/知名企业（基线里没有主动收窄，这正是"残酷"的来源之一：
      同时要跟应届生和资深社招竞争大厂坑位）
    - hidden_signals 全部从简历/经历如实推断，刻意不写"沟通能力强"这种模板话，
      给一个中等偏低、贴近真实空窗期候选人的基线
    """
    school_tier = SchoolTier.TIER_DOUBLE_NON  # 双非一本，文科

    edu = EducationExperience(
        school="某双非一本院校",
        degree="本科",
        major="汉语言文学",
        period="2016.09 - 2020.06",
    )
    work_gap = WorkExperience(
        company="（全职育儿）",
        role="全职家庭主妇 / 育儿",
        period="2024.03 - 2026.03",
        description="全职照顾 0-2 岁婴幼儿，独立处理家庭日常事务、突发状况与多方协调（就医、早教机构对接、家庭财务）。",
    )
    work_before = WorkExperience(
        company="某文化传播公司",
        role="行政专员",
        period="2020.07 - 2024.02",
        description="负责公司日常行政事务、会议统筹、跨部门文件流转，协助部门经理跟进多个并行的小型项目进度。",
    )

    cv = OfficialCV(
        resume_quality=52,
        name="林曼（化名）",
        gender="女",
        job_status="职业空窗后重返",
        age=28,
        work_years="4年工作经验（含2年全职育儿空窗）",
        highest_degree="本科",
        current_address="上海",
        job_expectation=JobExpectation(
            target_industries=["互联网/科技", "文化传媒", "教育"],
            target_roles=["项目管理", "产品运营", "产品经理", "运营专员"],
            target_cities=["上海", "北京"],
            min_salary="12-16k·13薪",
        ),
        work_internship_history=[work_before, work_gap],
        project_history=[],
        education_history=[edu],
        personal_strengths="做事细致、有耐心，愿意从头学习新领域知识。",
        certificates=["PMP（备考中）"],
    )
    hidden = CandidateHiddenSignals(
        school_tier=school_tier,
        gpa_percentile=55,
        project_strength=25,       # 文科+行政背景，缺乏对口"项目"经历
        internship_strength=15,    # 无正式实习，只有行政岗工作经历
        achievements_strength=10,  # 无竞赛/论文/出圈项目
        communication_score=55,    # 中等，未被刻意强调
        stress_tolerance=50,
        overwork_tolerance=40,     # 育儿后现实中对高强度加班接受度降低
    )
    return CandidateProfile(
        candidate_id="mom-comeback-baseline",
        is_primary=True,
        official_cv=cv,
        hidden_signals=hidden,
    )


def build_mom_candidate_counterfactual(base: CandidateProfile) -> CandidateProfile:
    """反事实：不改过去（work history 原文不动），只调"策略变量"。

    对应 agy 剧本三个滑块：
    1. 目标企业规模：大厂 -> 创业公司/中小公司
       —— engine 里候选人 agent 能看到 company.size_label，是自己在
          prompt 里权衡"符合期望+有合理通过概率"，所以这里通过收窄
          target_industries + 在 job_expectation 里显式点名规模偏好文本，
          引导 apply 阶段的 LLM 更倾向中小/创业公司 JD。
    2. 核心竞争力重构："两年带娃" -> "多线程危机处理能力"
       —— 关键：company_hr.py 的筛选 prompt 和 interviewer.py 的面试 prompt
          都不读 personal_strengths 自由文本，只读结构化 hidden_signals
          （project_strength/internship_strength/achievements_strength/
          communication_score/stress_tolerance）。所以"重构叙事"如果只改
          文本、不改这些数值，对真实 sim 结果零影响——是自欺欺人的演示。
          真正诚实的做法：把"两年带娃= 独立处理多线程任务+高压应对"如实
          换算成这几个维度的提升，幅度克制（+10~+15，不是编造成 90 分专家），
          因为这本来就是候选人真实具备、只是没被结构化字段捕捉到的能力。
       —— personal_strengths 文本也同步改写（不影响 sim 数值，但保持
          candidate.json 的"人设一致性"，用于演示/PPT 展示简历原文）。
    3. 预期薪资 -10%：12-16k -> 11-14k（数值下调，反映"务实"策略）
    """
    c = base.model_copy(deep=True)

    # ---- 1. 目标企业规模：收窄到中小/创业公司 ----
    new_je = c.official_cv.job_expectation.model_copy(
        update={
            "target_industries": ["互联网/科技-创业公司", "文化传媒", "教育"],
            "min_salary": "11-14k·13薪",  # ---- 3. 预期薪资 -10% ----
        }
    )
    new_cv = c.official_cv.model_copy(
        update={
            "job_expectation": new_je,
            "personal_strengths": (
                "两年全职育儿期间，独立处理婴幼儿看护、就医、早教对接、家庭财务等多条并行事务，"
                "培养出很强的多线程任务协调与突发危机应对能力；优先考虑成长型中小/创业公司，"
                "愿意从具体执行做起，快速补齐项目管理专业技能（PMP 备考中）。"
            ),
        }
    )

    # ---- 2. 核心竞争力重构 -> 落到真实被 sim 消费的 hidden_signals ----
    new_signals = c.hidden_signals.model_copy(
        update={
            "communication_score": min(100, c.hidden_signals.communication_score + 10),
            "stress_tolerance": min(100, c.hidden_signals.stress_tolerance + 15),
            "achievements_strength": min(100, c.hidden_signals.achievements_strength + 10),
        }
    )

    c = c.model_copy(update={"official_cv": new_cv, "hidden_signals": new_signals})
    c.candidate_id = base.candidate_id + "-cf-startup-reframe-salarydown"
    return c


def build_mom_candidate_action_plan(base: CandidateProfile) -> CandidateProfile:
    """第二个反事实（CF2）：不是"重新包装过去"，而是"未来 3-6 个月的行动计划"。

    第一个反事实（软性重构）真跑下来 offer_rate 依然是 0——因为筛选 agent 读的是
    project_strength / internship_strength / achievements_strength，而"把带娃说成多线程"
    只提升了沟通/抗压，没有提升这三个"可验证的经历硬度"维度。这是诚实的结论：
    **纯叙事重构骗不过市场，市场筛的是能被验证的东西。**

    所以 CF2 演的是"真的去补硬实力"这条路（沙盘用来对比"包装 vs 真做"的差别）：
    - PMP 从"备考中"变成"已拿证"（对口项目管理岗的硬资格）-> achievements 实质提升
    - 用育儿这段时间接了 1-2 个真实的自由职业/社区运营小项目并交付
      （如帮小机构做活动统筹、线上社群运营）-> project_strength 实质提升
      （从 25 -> 50，仍不夸张：是"入门有作品"而非"资深专家"）
    - internship_strength 略升（这些真实项目部分等价于实习经历）-> 15 -> 35
    - 叠加 CF1 的策略（创业公司偏好 + 薪资务实 + 软性提升）

    诚实边界：这是"如果她真的花半年补上可验证的经历，会怎样"的推演，
    **不是**教她把没做过的事写进简历。沙盘展示的正是"真做"和"包装"的分野。
    """
    # 先套用 CF1 的软性策略作为底子
    c = build_mom_candidate_counterfactual(base)

    # 再叠加"真的补上硬实力"
    new_signals = c.hidden_signals.model_copy(
        update={
            "project_strength": 50,       # 25 -> 50：有 1-2 个交付过的真实小项目
            "internship_strength": 35,    # 15 -> 35：真实项目部分等价实习
            "achievements_strength": 35,  # 20 -> 35：PMP 拿证 + 项目成果
        }
    )
    # resume_quality 也随之提升（有真实作品可写，简历更实）
    new_cv = c.official_cv.model_copy(
        update={
            "resume_quality": min(100, c.official_cv.resume_quality + 13),  # 52 -> 65
            "personal_strengths": (
                "职业空窗期内主动补齐硬实力：已取得 PMP 认证；以自由职业身份为 2 家小机构"
                "交付了活动统筹与线上社群运营项目（含完整策划、执行、复盘文档）。"
                "叠加两年育儿锻炼出的多线程协调与危机处理能力，目标成长型中小/创业公司的项目管理岗。"
            ),
            "certificates": ["PMP（已认证）"],
        }
    )
    c = c.model_copy(update={"official_cv": new_cv, "hidden_signals": new_signals})
    c.candidate_id = base.candidate_id + "-cf2-action-plan-real-substance"
    return c


# ============================================================
# 批量真跑（复刻 big_market_sim.py 的 run_batch）
# ============================================================


async def run_batch(candidate: CandidateProfile, companies, personas,
                    n_runs: int, concurrency: int, competitors: int,
                    base_seed: int, tag: str,
                    max_retries: int = 2, per_sim_timeout: int = 300) -> tuple[list[SimOutcome], dict]:
    router = get_router()
    sem = asyncio.Semaphore(concurrency)
    outcomes: list[SimOutcome] = []
    durations: list[float] = []
    failures: list[dict] = []

    async def one_sim(idx: int) -> None:
        async with sem:
            for attempt in range(max_retries + 1):
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
    ap.add_argument("--n", type=int, default=20, help="基线真跑次数")
    ap.add_argument("--cf-n", type=int, default=20, help="反事实真跑次数")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--competitors", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260703)
    ap.add_argument("--target-n", type=int, default=1000)
    ap.add_argument("--timeout", type=int, default=300, help="单 sim 超时秒数")
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--cf2-n", type=int, default=0, help="第二反事实（行动计划/真补硬实力）真跑次数，0=不跑")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--skip-cf1", action="store_true", help="跳过第一反事实（软性重构）")
    args = ap.parse_args()

    import os
    init_router()
    router = get_router()
    # 全局限流：把整个进程在飞 LLM 请求压到 LLM_GLOBAL_CONCURRENCY（默认 2），
    # 适配 NVIDIA 免费层低 RPM。DeepSeek 有余额时可调高。
    global_conc = int(os.environ.get("LLM_GLOBAL_CONCURRENCY", "2"))
    min_interval = float(os.environ.get("LLM_MIN_INTERVAL_SEC", "0"))
    install_global_llm_throttle(router, max_inflight=global_conc, min_interval_sec=min_interval)
    print(f"LLM 路由: {router.describe_routing()} | 在飞上限={global_conc} | 配速间隔={min_interval}s", flush=True)

    companies = load_companies()
    personas = load_personas()
    all_codes = [c.code_name for c in companies]
    print(f"市场规模: {len(companies)} 家公司 / {len(personas)} 竞争者池", flush=True)

    baseline = build_mom_candidate_baseline()
    cf = build_mom_candidate_counterfactual(baseline)

    print(f"基线候选人: {baseline.official_cv.name} / {baseline.hidden_signals.school_tier.value} / "
          f"{baseline.official_cv.highest_degree} / {baseline.official_cv.age}岁", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    report: dict = {
        "generated_at": ts,
        "case_name": "28岁全职宝妈绝境求生 -> 反事实翻盘",
        "market": {"companies": len(companies), "competitor_pool": len(personas)},
        "baseline_candidate": {
            "name": baseline.official_cv.name,
            "age": baseline.official_cv.age,
            "school_tier": baseline.hidden_signals.school_tier.value,
            "degree": baseline.official_cv.highest_degree,
            "job_status": baseline.official_cv.job_status,
            "target_roles": baseline.official_cv.job_expectation.target_roles,
            "min_salary": baseline.official_cv.job_expectation.min_salary,
            "hidden_signals": baseline.hidden_signals.model_dump(mode="json"),
            "resume_quality": baseline.official_cv.resume_quality,
        },
        "counterfactual_candidate": {
            "target_industries": cf.official_cv.job_expectation.target_industries,
            "min_salary": cf.official_cv.job_expectation.min_salary,
            "hidden_signals": cf.hidden_signals.model_dump(mode="json"),
            "personal_strengths": cf.official_cv.personal_strengths,
        },
        "config": {
            "n_baseline": args.n,
            "n_counterfactual": args.cf_n,
            "concurrency": args.concurrency,
            "competitors_per_sim": args.competitors,
            "target_n": args.target_n,
            "seed": args.seed,
        },
    }

    # ===== 基线：残酷现实 =====
    if args.skip_baseline:
        print("\n===== 跳过基线批次 =====", flush=True)
        report["baseline_report"] = None
    else:
        print("\n===== 基线批次（残酷现实）开始 =====", flush=True)
        base_outcomes, base_meta = await run_batch(
            baseline, companies, personas,
            n_runs=args.n, concurrency=args.concurrency, competitors=args.competitors,
            base_seed=args.seed, tag="mom_base",
            max_retries=args.max_retries, per_sim_timeout=args.timeout,
        )
        report["baseline_run_meta"] = base_meta
        report["baseline_report"] = (
            aggregate_report("基线：28岁全职宝妈原始策略", base_outcomes, all_codes, args.target_n)
            if base_outcomes else None
        )

    # ===== 反事实 1：软性策略调整（创业公司+叙事重构+薪资-10%）=====
    if args.skip_cf1:
        print("\n===== 跳过反事实1（软性重构）=====", flush=True)
        report["counterfactual_report"] = None
    else:
        print("\n===== 反事实1批次（软性策略调整）开始 =====", flush=True)
        cf_outcomes, cf_meta = await run_batch(
            cf, companies, personas,
            n_runs=args.cf_n, concurrency=args.concurrency, competitors=args.competitors,
            base_seed=args.seed + 777, tag="mom_cf",
            max_retries=args.max_retries, per_sim_timeout=args.timeout,
        )
        report["counterfactual_run_meta"] = cf_meta
        report["counterfactual_report"] = (
            aggregate_report("反事实1：创业公司+叙事重构+薪资-10%", cf_outcomes, all_codes, args.target_n)
            if cf_outcomes else None
        )

    # ===== 反事实 2：行动计划（真补可验证硬实力：PMP拿证+真实项目）=====
    if args.cf2_n > 0:
        cf2 = build_mom_candidate_action_plan(baseline)
        report["counterfactual2_candidate"] = {
            "target_industries": cf2.official_cv.job_expectation.target_industries,
            "min_salary": cf2.official_cv.job_expectation.min_salary,
            "hidden_signals": cf2.hidden_signals.model_dump(mode="json"),
            "resume_quality": cf2.official_cv.resume_quality,
            "personal_strengths": cf2.official_cv.personal_strengths,
        }
        print("\n===== 反事实2批次（行动计划/真补硬实力）开始 =====", flush=True)
        cf2_outcomes, cf2_meta = await run_batch(
            cf2, companies, personas,
            n_runs=args.cf2_n, concurrency=args.concurrency, competitors=args.competitors,
            base_seed=args.seed + 1313, tag="mom_cf2",
            max_retries=args.max_retries, per_sim_timeout=args.timeout,
        )
        report["counterfactual2_run_meta"] = cf2_meta
        report["counterfactual2_report"] = (
            aggregate_report("反事实2：行动计划(PMP拿证+真实项目)+创业公司+薪资-10%",
                             cf2_outcomes, all_codes, args.target_n)
            if cf2_outcomes else None
        )

    report["llm_usage"] = get_llm_usage()

    out_file = OUT_DIR / f"mom_comeback_report_{ts}.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out_file}", flush=True)
    print("LLM 消耗:", get_llm_usage(), flush=True)

    # ---- 命令行摘要，方便直接抄进逐字稿 ----
    def _summ(rep):
        if not rep:
            return "无成功样本"
        agg = rep["aggregate"]
        return (f"真跑 {rep['n_real_sims']} 次 | offer_rate(真实点估计)="
                f"{sum(1 for o in rep['raw_outcomes'] if o['total_offers']>0)}/{rep['n_real_sims']} | "
                f"mean_offers={agg['mean_offers']:.2f} | settled_rate真实="
                f"{sum(1 for o in rep['raw_outcomes'] if o['final_destination_company'])}/{rep['n_real_sims']} | "
                f"mean_salary_when_settled={agg['mean_salary_when_settled']:.2f}万")

    print("\n===== 摘要 =====")
    print("基线:", _summ(report.get("baseline_report")))
    print("反事实1(软性重构):", _summ(report.get("counterfactual_report")))
    if report.get("counterfactual2_report") is not None:
        print("反事实2(行动计划):", _summ(report.get("counterfactual2_report")))

    await shutdown_router()


if __name__ == "__main__":
    asyncio.run(main())
