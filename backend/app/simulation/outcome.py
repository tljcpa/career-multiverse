"""
单次 sim 的最终输出结构。

从 SimulationState 提取主用户的"求职旅程" + 关键 metric。
1000 次 sim 的 SimOutcome 列表会聚合成"平行宇宙报告"。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventType
from .state import SimulationState


class CompanyJourney(BaseModel):
    """主用户在一家公司的旅程总结"""

    company_code: str
    job_title: str
    # 最终阶段
    final_stage: str
    # 投递周
    applied_week: int
    # 走到了第几轮
    final_round: int = 0
    # 各轮评分
    interview_scores: list[int] = Field(default_factory=list)
    # 如果收到了 offer：薪资
    offer_salary_wan: float = 0.0
    # 是否最终入职这家
    is_final_destination: bool = False


class SimOutcome(BaseModel):
    """单次 sim 的最终结果，即"一个平行宇宙的春招结局"。

    1000 次 sim 后这些 SimOutcome 会聚合：
    - 平均拿到 offer 数
    - 各公司 offer 概率
    - 最终去向分布
    - 薪资分布
    """

    sim_id: str
    counterfactual_diff: str = ""

    # ===== 关键 metric =====
    total_applications: int
    total_interviews: int
    total_offers: int
    final_destination_company: str = ""  # 最终去向（空 = 没拿到任何 offer）
    final_destination_role: str = ""
    final_salary_wan: float = 0.0
    final_week_when_settled: int = -1  # 第几周搞定

    # ===== 详细 journey =====
    journeys: list[CompanyJourney] = Field(default_factory=list)


def extract_outcome(state: SimulationState) -> SimOutcome:
    """从 state 提取主用户 outcome"""
    pid = state.primary_id()

    # 统计
    n_applications = sum(
        1 for e in state.events
        if e.event_type == EventType.APPLICATION and e.candidate_id == pid
    )
    n_interviews = sum(
        1 for e in state.events
        if e.event_type == EventType.INTERVIEW and e.candidate_id == pid
    )
    n_offers = sum(
        1 for e in state.events
        if e.event_type == EventType.OFFER_ISSUED and e.candidate_id == pid
    )

    # 找最终去向
    accepted = state.primary_accepted_offer()
    final_company = accepted.company_code if accepted else ""
    final_role = accepted.job_title if accepted else ""
    final_salary = accepted.offer_salary_wan if accepted else 0.0
    # 找接受 offer 的那一周
    final_week = -1
    if accepted is not None:
        for e in state.events:
            if (
                e.event_type == EventType.OFFER_ACCEPTED
                and e.candidate_id == pid
                and e.company_code == accepted.company_code
            ):
                final_week = e.week
                break

    # 构建 journey
    journeys: list[CompanyJourney] = []
    for p in state.primary_applications():
        # 找 applied_week
        applied_week = 0
        for e in state.events:
            if (
                e.event_type == EventType.APPLICATION
                and e.candidate_id == pid
                and e.company_code == p.company_code
                and e.job_title == p.job_title
            ):
                applied_week = e.week
                break
        journeys.append(
            CompanyJourney(
                company_code=p.company_code,
                job_title=p.job_title,
                final_stage=p.stage,
                applied_week=applied_week,
                final_round=p.current_round,
                interview_scores=list(p.interview_scores),
                offer_salary_wan=p.offer_salary_wan,
                is_final_destination=(p.company_code == final_company and p.job_title == final_role),
            )
        )

    return SimOutcome(
        sim_id=state.sim_id,
        counterfactual_diff=state.counterfactual_diff,
        total_applications=n_applications,
        total_interviews=n_interviews,
        total_offers=n_offers,
        final_destination_company=final_company,
        final_destination_role=final_role,
        final_salary_wan=final_salary,
        final_week_when_settled=final_week,
        journeys=journeys,
    )
