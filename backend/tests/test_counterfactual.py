"""
反事实分析端到端测试。

跑：原始 + 3 个 mutation，各 5 次 sim（demo 显示用 30+，这里 5 是 dev 验证）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.models.candidate import CandidateProfile
from app.models.company import CompanyProfile
from app.services.llm import build_router
from app.simulation.counterfactual import (
    CounterfactualRunner,
    mutation_focus_industries,
    mutation_overwork_boost,
    mutation_project_boost,
    mutation_resume_quality_boost,
)


def _print_agg(agg) -> None:
    print(f"=== {agg.label} (N={agg.n_runs}) ===")
    print(f"  offer_rate     : {agg.offer_rate:.2%}")
    print(f"  settled_rate   : {agg.settled_rate:.2%}")
    print(f"  mean offers    : {agg.mean_offers:.2f}")
    print(f"  mean apps      : {agg.mean_applications:.2f}")
    print(f"  mean interviews: {agg.mean_interviews:.2f}")
    print(f"  mean salary    : {agg.mean_salary_when_settled:.1f} 万")
    print(f"  median salary  : {agg.median_salary_when_settled:.1f} 万")
    print(f"  top destinations: {agg.destination_distribution}")
    print(f"  week settled   : {agg.week_settled_distribution}")
    print()


async def main() -> None:
    companies = [
        CompanyProfile.model_validate(c)
        for c in json.load(open(PROJECT_ROOT / "data" / "companies" / "companies_v1.json"))
    ]
    personas = [
        CandidateProfile.model_validate(p)
        for p in json.load(open(PROJECT_ROOT / "data" / "personas" / "competitors_v1.json"))
    ]

    # 用一个"中间档"persona 当主用户（更明显看到反事实差异）
    # 选一个 985 学校、resume_quality 60 左右的
    mid_candidates = [
        p
        for p in personas
        if p.hidden_signals.school_tier.value in ("985", "211")
        and 50 <= p.official_cv.resume_quality <= 70
    ]
    primary = mid_candidates[0].model_copy(
        update={"is_primary": True, "candidate_id": "user_primary"}
    )
    print(
        f"主用户: {primary.official_cv.name} "
        f"({primary.hidden_signals.school_tier.value}, "
        f"resume={primary.official_cv.resume_quality}, "
        f"project={primary.hidden_signals.project_strength})"
    )
    print(f"目标: {primary.official_cv.job_expectation.target_roles}")
    print(f"目标行业: {primary.official_cv.job_expectation.target_industries}")
    print()

    settings = get_settings()
    router = build_router(settings)

    # dev 验证：5 次/variant，正式 demo 用 30-50 次
    runs_per_variant = 5

    runner = CounterfactualRunner(
        router,
        companies[:15],  # 公司池 15 家加速
        personas,
        runs_per_variant=runs_per_variant,
        max_concurrency=6,
    )

    baseline = await runner.run_baseline(primary)
    _print_agg(baseline)

    # 反事实 1: 简历质量 +10
    mut1 = mutation_resume_quality_boost(10)
    print(f"--- 反事实: {mut1.description} ---")
    agg1 = await runner.run_mutation(primary, mut1, seed_offset=10000)
    _print_agg(agg1)

    # 反事实 2: 项目含金量 +15
    mut2 = mutation_project_boost(15)
    print(f"--- 反事实: {mut2.description} ---")
    agg2 = await runner.run_mutation(primary, mut2, seed_offset=20000)
    _print_agg(agg2)

    # 反事实 3: 接受 996
    mut3 = mutation_overwork_boost(95)
    print(f"--- 反事实: {mut3.description} ---")
    agg3 = await runner.run_mutation(primary, mut3, seed_offset=30000)
    _print_agg(agg3)

    await router.close()

    # 持久化对比
    report = {
        "primary_candidate_id": primary.candidate_id,
        "runs_per_variant": runs_per_variant,
        "variants": [
            baseline.model_dump(mode="json"),
            agg1.model_dump(mode="json"),
            agg2.model_dump(mode="json"),
            agg3.model_dump(mode="json"),
        ],
    }
    out = PROJECT_ROOT / "data" / "sim_runs" / "counterfactual_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"反事实报告 -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
