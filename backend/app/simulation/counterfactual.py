"""
反事实分析模块。这是产品最大的差异化卖点：

不是"AI 给你建议"，而是 "AI 替你跑 N 个平行宇宙的春招，每个改一处变量，给你看结果如何变化"。

例如：
- 原始 candidate vs (project_strength + 15)
- 原始 candidate vs (移除上海作为目标城市)
- 原始 candidate vs (overwork_tolerance 提到 80)

输出对比表：每种改动下，1000 次 sim 的 offer 率/平均薪资/最终去向分布如何变化。
"""

from __future__ import annotations

import asyncio
import logging
import random
import statistics
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel

from ..models.candidate import CandidateProfile
from ..models.company import CompanyProfile
from ..services.llm import LLMRouter

from .engine import SimulationEngine
from .outcome import SimOutcome
from .state import init_sim_state

logger = logging.getLogger(__name__)


# ============================================================
# 反事实 mutation 定义
# ============================================================


@dataclass
class Mutation:
    """一个反事实改动。
    apply 函数接受 candidate 返回改动后的副本"""

    name: str
    description: str
    apply: callable  # CandidateProfile -> CandidateProfile


def mutation_project_boost(delta: int = 15) -> Mutation:
    """提升项目含金量评分"""

    def apply(c: CandidateProfile) -> CandidateProfile:
        new_signals = c.hidden_signals.model_copy(
            update={
                "project_strength": min(100, c.hidden_signals.project_strength + delta)
            }
        )
        return c.model_copy(update={"hidden_signals": new_signals})

    return Mutation(
        name=f"project_strength +{delta}",
        description=f"项目含金量评分提升 {delta} 分（相当于多做 1-2 个有深度的项目）",
        apply=apply,
    )


def mutation_resume_quality_boost(delta: int = 10) -> Mutation:
    def apply(c: CandidateProfile) -> CandidateProfile:
        new_cv = c.official_cv.model_copy(
            update={"resume_quality": min(100, c.official_cv.resume_quality + delta)}
        )
        return c.model_copy(update={"official_cv": new_cv})

    return Mutation(
        name=f"resume_quality +{delta}",
        description=f"整体简历质量评分提升 {delta} 分（重新打磨表达 + 突出关键点）",
        apply=apply,
    )


def mutation_overwork_boost(value: int = 90) -> Mutation:
    def apply(c: CandidateProfile) -> CandidateProfile:
        new_signals = c.hidden_signals.model_copy(
            update={"overwork_tolerance": value}
        )
        return c.model_copy(update={"hidden_signals": new_signals})

    return Mutation(
        name=f"overwork_tolerance = {value}",
        description=f"接受 996/高强度的程度提到 {value}（投递更激进、HR 看到此信号也更愿意发 offer）",
        apply=apply,
    )


def mutation_focus_industries(industries: list[str]) -> Mutation:
    """收窄目标行业（更聚焦）"""

    def apply(c: CandidateProfile) -> CandidateProfile:
        new_je = c.official_cv.job_expectation.model_copy(
            update={"target_industries": industries}
        )
        new_cv = c.official_cv.model_copy(update={"job_expectation": new_je})
        return c.model_copy(update={"official_cv": new_cv})

    return Mutation(
        name=f"target_industries = {industries}",
        description=f"将目标行业收窄到 {industries}",
        apply=apply,
    )


# ============================================================
# 多次 sim 聚合
# ============================================================


class OutcomeAggregate(BaseModel):
    """N 次 sim 后的统计聚合"""

    label: str  # "原始" 或 mutation name
    n_runs: int

    offer_rate: float  # 收到 >=1 个 offer 的 sim 占比
    mean_offers: float
    mean_applications: float
    mean_interviews: float
    mean_salary_when_settled: float  # 接受 offer 的 sim 里的平均薪资
    median_salary_when_settled: float
    settled_rate: float  # 最终接受 offer 的 sim 占比

    # 最终去向分布 top 5
    destination_distribution: dict[str, int]
    # 各 sim 接受 offer 的周次分布
    week_settled_distribution: dict[int, int]


def aggregate_outcomes(label: str, outcomes: list[SimOutcome]) -> OutcomeAggregate:
    n = len(outcomes)
    settled = [o for o in outcomes if o.final_destination_company]
    return OutcomeAggregate(
        label=label,
        n_runs=n,
        offer_rate=sum(1 for o in outcomes if o.total_offers > 0) / max(1, n),
        mean_offers=statistics.mean(o.total_offers for o in outcomes) if n > 0 else 0,
        mean_applications=statistics.mean(o.total_applications for o in outcomes) if n > 0 else 0,
        mean_interviews=statistics.mean(o.total_interviews for o in outcomes) if n > 0 else 0,
        mean_salary_when_settled=(
            statistics.mean(o.final_salary_wan for o in settled) if settled else 0.0
        ),
        median_salary_when_settled=(
            statistics.median(o.final_salary_wan for o in settled) if settled else 0.0
        ),
        settled_rate=len(settled) / max(1, n),
        destination_distribution=dict(
            Counter(o.final_destination_company for o in settled).most_common(5)
        ),
        week_settled_distribution=dict(
            Counter(o.final_week_when_settled for o in settled).most_common(8)
        ),
    )


# ============================================================
# 反事实运行器
# ============================================================


class CounterfactualRunner:
    """对一个 candidate 跑 N 次原始 sim + 对每个 mutation 跑 M 次 sim，
    输出对比 aggregate"""

    def __init__(
        self,
        router: LLMRouter,
        companies: list[CompanyProfile],
        competitor_pool: list[CandidateProfile],
        *,
        runs_per_variant: int = 30,
        max_concurrency: int = 8,
        seed: int = 42,
    ) -> None:
        self._router = router
        self._companies = companies
        self._competitor_pool = competitor_pool
        self._runs_per_variant = runs_per_variant
        self._max_concurrency = max_concurrency
        self._base_seed = seed

    async def run_baseline(
        self, candidate: CandidateProfile
    ) -> OutcomeAggregate:
        outcomes = await self._run_n_sims(candidate, label="原始", seed_offset=0)
        return aggregate_outcomes("原始", outcomes)

    async def run_mutation(
        self,
        candidate: CandidateProfile,
        mutation: Mutation,
        *,
        seed_offset: int = 10_000,
    ) -> OutcomeAggregate:
        mutated = mutation.apply(candidate)
        # diff 标识：让每次 sim 知道自己是反事实
        diff = mutation.name
        outcomes = await self._run_n_sims(
            mutated, label=mutation.name, seed_offset=seed_offset, diff=diff
        )
        return aggregate_outcomes(mutation.name, outcomes)

    async def _run_n_sims(
        self,
        candidate: CandidateProfile,
        *,
        label: str,
        seed_offset: int,
        diff: str = "",
    ) -> list[SimOutcome]:
        sem = asyncio.Semaphore(self._max_concurrency)

        async def one_sim(idx: int) -> SimOutcome:
            async with sem:
                rng = random.Random(self._base_seed + seed_offset + idx)
                state = init_sim_state(
                    candidate,
                    self._companies,
                    self._competitor_pool,
                    sim_id=f"{label}#{idx}",
                    rng=rng,
                )
                state.counterfactual_diff = diff
                engine = SimulationEngine(self._router, state, rng=rng)
                return await engine.run()

        tasks = [one_sim(i) for i in range(self._runs_per_variant)]
        return await asyncio.gather(*tasks)
