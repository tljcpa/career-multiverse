"""
SimulationEngine：编排 13 周春招流程。

每周流程（5 阶段）：
1. 候选人投递（CandidateAgent.act_apply_phase）
2. HR 筛新简历（CompanyHRAgent.act_screening_phase）
3. 已筛过/已通过上轮的进入下一轮面试（InterviewerAgent.conduct_interview）
4. 通过所有轮次的发 offer（CompanyHRAgent.act_offer_phase）
5. 候选人响应 offer（CandidateAgent.act_offer_phase）

P0 简化：
- 只主用户调 LLM 决策；竞争者不调 LLM（D5-D6 再加竞争者投递规则）
- 公司 interview_rounds 字段决定要面几轮（默认看 hidden_signals.hiring_style 推断）
- offer 4 周内有效
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from ..models.company import CompanyProfile
from ..services.llm import LLMRouter
from ..agents.candidate import CandidateAgent
from ..agents.company_hr import CompanyHRAgent
from ..agents.competitor import CompetitorSimulator
from ..agents.interviewer import InterviewerAgent

from .events import Event
from .outcome import SimOutcome, extract_outcome
from .state import CandidatePipeline, SimulationState, TOTAL_WEEKS

logger = logging.getLogger(__name__)


# 默认每家公司面试轮数。calibration 后：每档 -1，让单次 sim 总面试数更真实
# 之前 5/4/3/2 导致 13 周内可面 40+ 次（夸张），现在 4/3/2/2 更接近真实春招节奏
def _default_interview_rounds(company: CompanyProfile) -> int:
    bar = company.hidden_signals.hiring_bar
    if bar >= 90:
        return 4
    if bar >= 80:
        return 3
    return 2


class SimulationEngine:
    def __init__(
        self,
        router: LLMRouter,
        state: SimulationState,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._router = router
        self.state = state
        self._rng = rng if rng is not None else random.Random()

        # 提前实例化 Agent，避免每周重建
        self.candidate_agent = CandidateAgent(router, state.primary_candidate)
        self.hr_agents = {
            c.code_name: CompanyHRAgent(router, c) for c in state.companies
        }
        self.interviewer_agents = {
            c.code_name: InterviewerAgent(router, c) for c in state.companies
        }
        # 竞争者用规则模拟，不调 LLM
        self.competitor_sim = CompetitorSimulator(rng=self._rng)

        # 公司面试轮数表
        self._rounds_required = {
            c.code_name: _default_interview_rounds(c) for c in state.companies
        }

    # ===== 主入口 =====

    async def run(self) -> SimOutcome:
        for week in range(TOTAL_WEEKS):
            await self._run_week(week)
            # 若已经接受 offer 提前结束（节省 token）
            if self.state.primary_accepted_offer() is not None:
                logger.info(
                    f"sim {self.state.sim_id}: 在第 {week + 1} 周接受 offer，提前结束"
                )
                break
        return extract_outcome(self.state)

    # ===== 单周流程 =====

    async def _run_week(self, week: int) -> None:
        self.state.current_week = week

        # ---- 0. 竞争者规则推进（影响市场拥挤度 + 占用 HC） ----
        # 放在最前，让 HR 在筛选主用户前已经看到本周市场上有多少人
        comp_events = self.competitor_sim.step_week(self.state)
        for ev in comp_events:
            self.state.add_event(ev)

        # ---- 1. 候选人投递 ----
        new_apps = await self.candidate_agent.act_apply_phase(self.state)
        for ev in new_apps:
            self.state.add_event(ev)

        # ---- 2. 各公司筛简历 ----
        # 收集本周（且 stage == applied）的 pipeline 按公司分组
        screening_tasks = []
        for company in self.state.companies:
            to_screen = self._collect_new_applications_for_company(company.code_name)
            if not to_screen:
                continue
            hr = self.hr_agents[company.code_name]
            screening_tasks.append(hr.act_screening_phase(self.state, to_screen))
        # 公司之间互不依赖，并发跑
        if screening_tasks:
            results = await asyncio.gather(*screening_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    logger.warning(f"screening 阶段某公司异常: {r}")
                    continue
                for ev in r:
                    self.state.add_event(ev)

        # ---- 3. 进行下一轮面试 ----
        # 找出所有"通过了筛选/上一轮"且本公司还没到最终轮的 pipeline
        interview_tasks = []
        for p in self._pipelines_ready_for_next_round():
            company = self.state.company_by_code(p.company_code)
            if company is None:
                continue
            interviewer = self.interviewer_agents[p.company_code]
            interview_tasks.append(
                interviewer.conduct_interview(
                    self.state,
                    self.state.primary_candidate,  # P0 只主用户面试
                    p.job_title,
                    p.current_round + 1,
                )
            )
        if interview_tasks:
            results = await asyncio.gather(*interview_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    logger.warning(f"interview 阶段异常: {r}")
                    continue
                self.state.add_event(r)

        # ---- 4. 通过所有轮次的发 offer ----
        offer_tasks = []
        for company in self.state.companies:
            eligible = self._pipelines_ready_for_offer(company)
            if not eligible:
                continue
            hr = self.hr_agents[company.code_name]
            offer_tasks.append(hr.act_offer_phase(self.state, eligible))
        if offer_tasks:
            results = await asyncio.gather(*offer_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    logger.warning(f"offer 阶段异常: {r}")
                    continue
                for ev in r:
                    self.state.add_event(ev)

        # ---- 5. 候选人响应 offer ----
        responses = await self.candidate_agent.act_offer_phase(self.state)
        for ev in responses:
            self.state.add_event(ev)

    # ===== Pipeline 查询辅助 =====

    def _collect_new_applications_for_company(
        self, company_code: str
    ) -> list[tuple[Any, str]]:
        """收集本公司本周新收到、stage=applied 的 (candidate, job_title) 列表。
        P0 阶段只有主用户，所以最多 1 条"""
        result = []
        for p in self.state.pipelines.values():
            if p.company_code != company_code or p.stage != "applied":
                continue
            # 找投递的事件确认是本周新投的（避免重复筛选）
            # 简化：stage=applied 表示还没筛过，本周就处理
            if p.candidate_id == self.state.primary_id():
                result.append((self.state.primary_candidate, p.job_title))
        return result

    def _pipelines_ready_for_next_round(self) -> list[CandidatePipeline]:
        """筛选通过或上一轮通过且未到 max round 的 pipeline。
        当前简化：每周每个 pipeline 最多面 1 轮"""
        result = []
        for p in self.state.pipelines.values():
            if p.candidate_id != self.state.primary_id():
                continue
            max_rounds = self._rounds_required.get(p.company_code, 3)
            # screened_in 状态 → 进入第 1 轮面试
            if p.stage == "screened_in":
                result.append(p)
            # interviewing 且上轮通过且未到最终轮 → 下一轮
            elif (
                p.stage == "interviewing"
                and p.rounds_passed == p.current_round  # 上轮过了
                and p.current_round < max_rounds
            ):
                result.append(p)
        return result

    def _pipelines_ready_for_offer(self, company: CompanyProfile) -> list[CandidatePipeline]:
        """本公司所有"已完成所有面试轮"的 pipeline"""
        max_rounds = self._rounds_required.get(company.code_name, 3)
        result = []
        for p in self.state.pipelines.values():
            if p.company_code != company.code_name:
                continue
            if p.stage != "interviewing":
                continue
            if p.rounds_passed >= max_rounds and p.current_round == p.rounds_passed:
                result.append(p)
        return result
