"""
竞争者 Agent。

设计：竞争者**不调 LLM**（200 个 × 13 周调 LLM 成本爆炸），用纯规则模拟。
目的不是给竞争者真实决策，而是：
1. 制造市场拥挤度（HR 看到候选池里很多人）
2. 占用公司 HC，让主用户的 offer 概率更真实
3. 评委 demo 时可以"采访某个竞争者"——这时才补一次 LLM 调用

规则：
- 每周每个竞争者随机投 1-2 家（按目标行业匹配）
- 投递偏好基于学校 tier 和 hiring_bar 的匹配度
- 竞争者会自动通过筛选/面试到某个轮次，不真跑 LLM（按概率模型）
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..models.candidate import CandidateProfile, SchoolTier
from ..models.company import CompanyProfile
from ..simulation.events import (
    ApplicationEvent,
    Event,
    EventType,
    InterviewEvent,
    OfferEvent,
    ScreeningEvent,
)
from ..simulation.state import SimulationState

# 学校 tier 折算成 0-100 的"档次分"
_TIER_SCORE: dict[SchoolTier, int] = {
    SchoolTier.TIER_TOP: 95,
    SchoolTier.TIER_985_TOP: 88,
    SchoolTier.TIER_985: 78,
    SchoolTier.TIER_211: 68,
    SchoolTier.TIER_DOUBLE_NON: 55,
    SchoolTier.TIER_LOWER: 40,
    SchoolTier.TIER_OVERSEAS_TOP: 85,
    SchoolTier.TIER_OVERSEAS_OTHER: 60,
}


@dataclass
class CompetitorSimulator:
    """对一个 sim 内的所有竞争者跑规则模拟。
    挂在 engine 上每周调一次"""

    rng: random.Random

    def step_week(self, state: SimulationState) -> list[Event]:
        """单周步进，为所有竞争者产生事件"""
        events: list[Event] = []
        events.extend(self._competitors_apply(state))
        events.extend(self._competitors_screening(state))
        events.extend(self._competitors_interview(state))
        events.extend(self._competitors_offer(state))
        return events

    # ===== 1. 竞争者投递 =====

    def _competitors_apply(self, state: SimulationState) -> list[Event]:
        """每周每个竞争者随机投 0-2 家。
        投递概率随周次变化：早期激进、中期收敛、后期保底"""
        events: list[Event] = []
        # 早期 1-2 周激进，中期收敛，后期偶尔补
        if state.current_week <= 1:
            apply_chance = 0.85
            max_apps = 2
        elif state.current_week <= 6:
            apply_chance = 0.5
            max_apps = 2
        else:
            apply_chance = 0.2
            max_apps = 1

        for comp in state.competitors:
            if self.rng.random() > apply_chance:
                continue
            applied_companies = state.applied_companies(comp.candidate_id)
            # 候选公司：还没投过的、且行业匹配
            candidates = [
                c
                for c in state.companies
                if c.code_name not in applied_companies
                and self._industry_match(c, comp)
            ]
            if not candidates:
                continue
            # 偏好：tier 越高的候选人越倾向投 hiring_bar 高的公司
            picks = self._pick_companies_by_tier(comp, candidates, max_apps)
            for company in picks:
                if not company.job_postings:
                    continue
                jd = company.job_postings[0]
                events.append(
                    ApplicationEvent(
                        week=state.current_week,
                        candidate_id=comp.candidate_id,
                        company_code=company.code_name,
                        job_title=jd.job_title,
                        motivation="（规则竞争者）",
                    )
                )
        return events

    def _industry_match(self, company: CompanyProfile, comp: CandidateProfile) -> bool:
        """候选人目标行业里是否提及该公司行业。模糊匹配"""
        targets = comp.official_cv.job_expectation.target_industries
        if not targets:
            return True  # 没填目标的全投
        ind = company.industry
        return any(t in ind or ind in t for t in targets)

    def _pick_companies_by_tier(
        self,
        comp: CandidateProfile,
        candidates: list[CompanyProfile],
        max_apps: int,
    ) -> list[CompanyProfile]:
        """高 tier 投高 bar，低 tier 投低 bar，加随机扰动"""
        tier_score = _TIER_SCORE.get(comp.hidden_signals.school_tier, 60)
        # 每家公司的"匹配度" = 1 - |tier_score - hiring_bar| / 50
        scored = []
        for c in candidates:
            diff = abs(tier_score - c.hidden_signals.hiring_bar)
            match = max(0.0, 1.0 - diff / 50)
            # 加点随机
            score = match + self.rng.random() * 0.3
            scored.append((score, c))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [c for _, c in scored[:max_apps]]

    # ===== 2. 竞争者筛选（规则） =====

    def _competitors_screening(self, state: SimulationState) -> list[Event]:
        """竞争者的简历筛选：基于 tier vs bar 决定通过率"""
        events: list[Event] = []
        for p in list(state.pipelines.values()):
            if p.candidate_id == state.primary_id():
                continue
            if p.stage != "applied":
                continue
            comp = next(
                (c for c in state.competitors if c.candidate_id == p.candidate_id),
                None,
            )
            company = state.company_by_code(p.company_code)
            if comp is None or company is None:
                continue
            tier_score = _TIER_SCORE.get(comp.hidden_signals.school_tier, 60)
            # 通过率：tier_score 高于 hiring_bar 时高，低时低
            # 简化：差距每 10 分映射到 10% 概率
            diff = tier_score - company.hidden_signals.hiring_bar
            pass_prob = max(0.05, min(0.85, 0.5 + diff / 100))
            passed = self.rng.random() < pass_prob
            ev_type = EventType.SCREENING_PASS if passed else EventType.SCREENING_REJECT
            events.append(
                ScreeningEvent(
                    event_type=ev_type,
                    week=state.current_week,
                    candidate_id=p.candidate_id,
                    company_code=p.company_code,
                    job_title=p.job_title,
                    reasoning="（规则竞争者筛选）",
                    score=comp.official_cv.resume_quality,
                )
            )
        return events

    # ===== 3. 竞争者面试（规则） =====

    def _competitors_interview(self, state: SimulationState) -> list[Event]:
        """竞争者的面试推进：每周推一轮，按概率挂"""
        events: list[Event] = []
        for p in list(state.pipelines.values()):
            if p.candidate_id == state.primary_id():
                continue
            company = state.company_by_code(p.company_code)
            comp = next(
                (c for c in state.competitors if c.candidate_id == p.candidate_id),
                None,
            )
            if company is None or comp is None:
                continue
            # screened_in 推进到第 1 轮
            ready_for_round = None
            if p.stage == "screened_in":
                ready_for_round = 1
            elif (
                p.stage == "interviewing"
                and p.rounds_passed == p.current_round
                and p.current_round < self._max_rounds(company)
            ):
                ready_for_round = p.current_round + 1
            if ready_for_round is None:
                continue
            tier_score = _TIER_SCORE.get(comp.hidden_signals.school_tier, 60)
            base_score = (tier_score + comp.official_cv.resume_quality) / 2
            score = int(base_score + self.rng.randint(-15, 15))
            score = max(0, min(100, score))
            passed = score >= 60
            events.append(
                InterviewEvent(
                    week=state.current_week,
                    candidate_id=p.candidate_id,
                    company_code=p.company_code,
                    job_title=p.job_title,
                    round_num=ready_for_round,
                    interview_kind="（规则面试）",
                    score=score,
                    passed=passed,
                    feedback="（规则竞争者）",
                )
            )
        return events

    # ===== 4. 竞争者拿 offer（规则） =====

    def _competitors_offer(self, state: SimulationState) -> list[Event]:
        """通过所有轮次的竞争者发 offer。这会占用公司 HC"""
        events: list[Event] = []
        for p in list(state.pipelines.values()):
            if p.candidate_id == state.primary_id():
                continue
            company = state.company_by_code(p.company_code)
            if company is None:
                continue
            if p.stage != "interviewing":
                continue
            if (
                p.rounds_passed >= self._max_rounds(company)
                and p.current_round == p.rounds_passed
            ):
                # 估算薪资
                jd = next(
                    (j for j in company.job_postings if j.job_title == p.job_title),
                    None,
                )
                salary = 20.0
                if jd is not None:
                    from .company_hr import CompanyHRAgent

                    salary = CompanyHRAgent._estimate_salary(jd.salary)
                events.append(
                    OfferEvent(
                        week=state.current_week,
                        candidate_id=p.candidate_id,
                        company_code=p.company_code,
                        job_title=p.job_title,
                        salary_offer_wan=salary,
                        expires_week=min(state.current_week + 4, 12),
                    )
                )
        return events

    @staticmethod
    def _max_rounds(company: CompanyProfile) -> int:
        bar = company.hidden_signals.hiring_bar
        if bar >= 90:
            return 5
        if bar >= 80:
            return 4
        if bar >= 70:
            return 3
        return 2
