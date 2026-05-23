"""
端到端 smoke test：跑一次完整 13 周 sim。

不是单元测试，是 dev 验证脚本。需要 .env 里 DEEPSEEK_API_KEY 真实可用。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 让脚本能 import app.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.models.candidate import CandidateProfile
from app.models.company import CompanyProfile
from app.services.llm import build_router
from app.simulation.engine import SimulationEngine
from app.simulation.state import init_sim_state


async def main() -> None:
    # 1. 载入种子数据
    companies = [
        CompanyProfile.model_validate(c)
        for c in json.load(open(PROJECT_ROOT / "data" / "companies" / "companies_v1.json"))
    ]
    personas = [
        CandidateProfile.model_validate(p)
        for p in json.load(open(PROJECT_ROOT / "data" / "personas" / "competitors_v1.json"))
    ]

    # 2. 选第一个 persona 当主用户（实际使用时主用户从前端上传）
    primary = personas[0].model_copy(
        update={"is_primary": True, "candidate_id": "user_primary"}
    )
    print(f"主用户: {primary.official_cv.name}({primary.hidden_signals.school_tier.value}) "
          f"目标: {primary.official_cv.job_expectation.target_roles}")
    print(f"目标行业: {primary.official_cv.job_expectation.target_industries}")
    print(f"目标城市: {primary.official_cv.job_expectation.target_cities}")
    print()

    # 3. 初始化 state（公司池用前 15 家加速 demo；正式 sim 用全部）
    state = init_sim_state(
        primary,
        companies[:15],
        personas[1:],
        sim_id="smoke_e2e_001",
        num_competitors=20,
    )
    print(f"sim 配置: 公司池={len(state.companies)} 竞争者={len(state.competitors)}")
    print()

    # 4. 跑引擎
    settings = get_settings()
    router = build_router(settings)
    engine = SimulationEngine(router, state)

    print("=== sim 开始 ===")
    outcome = await engine.run()
    await router.close()

    # 5. 报告
    print()
    print(f"=== sim 结束（第 {state.current_week + 1} 周） ===")
    print(f"总投递: {outcome.total_applications}")
    print(f"总面试: {outcome.total_interviews}")
    print(f"总 offer: {outcome.total_offers}")
    print(f"最终去向: {outcome.final_destination_company} / {outcome.final_destination_role}")
    print(f"最终薪资: {outcome.final_salary_wan} 万")
    print(f"第几周搞定: {outcome.final_week_when_settled}")
    print()
    print("各公司 journey:")
    for j in outcome.journeys:
        marker = "★" if j.is_final_destination else "  "
        print(
            f"  {marker} W{j.applied_week:02d} 投 {j.company_code:10} {j.job_title[:20]:20}"
            f" -> {j.final_stage:12} 面试轮数={j.final_round} 分数={j.interview_scores}"
        )

    # 6. 持久化（便于检查事件流）
    out_dir = PROJECT_ROOT / "data" / "sim_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{state.sim_id}.json"
    out_path.write_text(
        json.dumps(
            {
                "sim_id": state.sim_id,
                "outcome": outcome.model_dump(mode="json"),
                "events": [ev.model_dump(mode="json") for ev in state.events],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n完整 sim 记录 -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
