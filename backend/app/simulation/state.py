"""
SimulationState：单次 sim 的完整状态对象。

持有：
- 静态：公司池、候选人池、主用户
- 动态：当前周、所有发生过的事件、各候选人正在进行的流程
- 派生查询：方便 Agent 决策时调用（"我已经投了哪些公司"、"哪些 offer 待响应"等）

为什么把全部状态聚合到一个对象：
- sim 周期内所有 Agent 决策都基于"完整快照"
- 序列化整个对象方便 1000 次 sim 的快照对比（反事实分析用）
- 单线程 asyncio 内不需要锁
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.models.candidate import CandidateProfile
from app.models.company import CompanyProfile

from .events import (
    ApplicationEvent,
    Event,
    EventType,
    InterviewEvent,
    OfferEvent,
    OfferResponseEvent,
    ScreeningEvent,
)


# 一次春招大致 3 个月 = 13 周
TOTAL_WEEKS: int = 13


@dataclass
class CandidatePipeline:
    """单个候选人对一家公司的"流程状态"。
    用 dataclass 是因为 sim 内频繁更新，避免 Pydantic 校验开销"""

    candidate_id: str
    company_code: str
    job_title: str

    # 当前所处阶段
    # applied: 已投递未筛选
    # screened_in: 筛选通过等待面试
    # interviewing: 面试中（含 current_round）
    # offered: 已发 offer 待响应
    # accepted: 候选人接受
    # rejected: 任意环节被拒
    # withdrawn: 候选人撤回
    stage: str = "applied"

    current_round: int = 0  # 进行到第几轮面试（0 = 还没开始）
    rounds_passed: int = 0  # 通过了几轮
    interview_scores: list[int] = field(default_factory=list)

    # offer 信息（offered 后填充）
    offer_salary_wan: float = 0.0
    offer_expires_week: int = -1


@dataclass
class SimulationState:
    """单次 sim 的完整状态"""

    # ===== 静态资源 =====
    primary_candidate: CandidateProfile
    companies: list[CompanyProfile]
    # 沙盘里的活跃竞争者（从 200 个池子里抽 N 个相关的）
    competitors: list[CandidateProfile] = field(default_factory=list)

    # ===== 时间 =====
    current_week: int = 0

    # ===== 事件流（不可变 append-only） =====
    events: list[Event] = field(default_factory=list)

    # ===== 各候选人 × 各公司的流程状态 =====
    # key = (candidate_id, company_code, job_title)
    # 一个候选人可在不同公司同时进行流程，互不影响
    pipelines: dict[tuple[str, str, str], CandidatePipeline] = field(
        default_factory=dict
    )

    # ===== sim 元数据 =====
    sim_id: str = ""
    # 是否启用反事实模式（在反事实分析时复制 state 并改变主候选人某些字段）
    counterfactual_diff: str = ""

    # ===== 工具方法 =====

    def add_event(self, event: Event) -> None:
        """记录事件并按需更新 pipelines 状态"""
        self.events.append(event)
        # 根据事件类型同步 pipelines
        if isinstance(event, ApplicationEvent):
            key = (event.candidate_id, event.company_code, event.job_title)
            self.pipelines[key] = CandidatePipeline(
                candidate_id=event.candidate_id,
                company_code=event.company_code,
                job_title=event.job_title,
                stage="applied",
            )
        elif isinstance(event, ScreeningEvent):
            key = (event.candidate_id, event.company_code, event.job_title)
            p = self.pipelines.get(key)
            if p is not None:
                if event.event_type == EventType.SCREENING_PASS:
                    p.stage = "screened_in"
                else:
                    p.stage = "rejected"
        elif isinstance(event, InterviewEvent):
            key = (event.candidate_id, event.company_code, event.job_title)
            p = self.pipelines.get(key)
            if p is not None:
                p.current_round = event.round_num
                p.interview_scores.append(event.score)
                if event.passed:
                    p.rounds_passed += 1
                    p.stage = "interviewing"
                else:
                    p.stage = "rejected"
        elif isinstance(event, OfferEvent):
            key = (event.candidate_id, event.company_code, event.job_title)
            p = self.pipelines.get(key)
            if p is not None:
                p.stage = "offered"
                p.offer_salary_wan = event.salary_offer_wan
                p.offer_expires_week = event.expires_week
        elif isinstance(event, OfferResponseEvent):
            key = (event.candidate_id, event.company_code, event.job_title)
            p = self.pipelines.get(key)
            if p is not None:
                if event.event_type == EventType.OFFER_ACCEPTED:
                    p.stage = "accepted"
                elif event.event_type == EventType.OFFER_DECLINED:
                    p.stage = "rejected"

    # ===== 派生查询（Agent 决策时常用） =====

    def primary_id(self) -> str:
        return self.primary_candidate.candidate_id

    def primary_applications(self) -> list[CandidatePipeline]:
        """主用户已投/进行中的所有 pipeline"""
        pid = self.primary_id()
        return [p for p in self.pipelines.values() if p.candidate_id == pid]

    def primary_active_pipelines(self) -> list[CandidatePipeline]:
        """主用户当前还活着（未拒/未撤）的流程"""
        return [
            p
            for p in self.primary_applications()
            if p.stage not in ("rejected", "withdrawn", "accepted")
        ]

    def primary_pending_offers(self) -> list[CandidatePipeline]:
        """主用户当前手上待响应的 offer"""
        return [p for p in self.primary_applications() if p.stage == "offered"]

    def primary_accepted_offer(self) -> CandidatePipeline | None:
        """主用户已接受的 offer（最多 1 个）"""
        for p in self.primary_applications():
            if p.stage == "accepted":
                return p
        return None

    def applied_companies(self, candidate_id: str) -> set[str]:
        """某候选人已投过的公司 code 集合，避免重复投"""
        return {
            p.company_code
            for p in self.pipelines.values()
            if p.candidate_id == candidate_id
        }

    def company_by_code(self, code: str) -> CompanyProfile | None:
        for c in self.companies:
            if c.code_name == code:
                return c
        return None


# ============================================================
# 构造工厂
# ============================================================


def init_sim_state(
    primary: CandidateProfile,
    all_companies: list[CompanyProfile],
    competitor_pool: list[CandidateProfile],
    *,
    sim_id: str = "",
    num_competitors: int = 30,
    rng: random.Random | None = None,
) -> SimulationState:
    """初始化 sim 状态。从竞争者分身池（当前 1947 人）里抽 num_competitors 个作为本次 sim 的竞争者"""
    r = rng if rng is not None else random.Random()
    selected_competitors = r.sample(
        competitor_pool, k=min(num_competitors, len(competitor_pool))
    )
    return SimulationState(
        primary_candidate=primary,
        companies=all_companies,
        competitors=selected_competitors,
        sim_id=sim_id,
    )
