"""
Simulation 事件类型定义。

设计原则：
- 事件是不可变 record，描述 sim 时间线上发生的一件事
- 事件本身不含决策逻辑，只是结果的物理记录
- 决策由 Agent 在 engine 编排下产生事件
- state.py 把事件汇集成可查询状态，outcome.py 从事件流提取最终结论
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """事件类型枚举。每个 tick 内可能产生多种事件"""

    APPLICATION = "application"  # 候选人投递了一份简历
    SCREENING_PASS = "screening_pass"  # HR 筛选通过
    SCREENING_REJECT = "screening_reject"  # HR 筛选拒绝
    INTERVIEW = "interview"  # 进行了一轮面试
    OFFER_ISSUED = "offer_issued"  # 公司发出 offer
    OFFER_ACCEPTED = "offer_accepted"  # 候选人接受 offer
    OFFER_DECLINED = "offer_declined"  # 候选人拒绝 offer
    OFFER_NEGOTIATING = "offer_negotiating"  # 候选人开始谈判
    NEGOTIATION_RESOLVED = "negotiation_resolved"  # 谈判结果
    REJECT_AFTER_INTERVIEW = "reject_after_interview"  # 面试后被拒
    CANDIDATE_WITHDRAW = "candidate_withdraw"  # 候选人主动撤回


# ============================================================
# 各事件类型的 payload
# ============================================================


class ApplicationEvent(BaseModel):
    """候选人投递简历事件"""

    event_type: Literal[EventType.APPLICATION] = EventType.APPLICATION
    week: int  # 0-12 对应春招 13 周
    candidate_id: str
    company_code: str
    job_title: str
    # 候选人投递时的策略动机（来自 LLM 决策的解释，用于反事实分析）
    motivation: str = ""


class ScreeningEvent(BaseModel):
    """HR 简历筛选事件"""

    event_type: Literal[EventType.SCREENING_PASS, EventType.SCREENING_REJECT]
    week: int
    candidate_id: str
    company_code: str
    job_title: str
    # HR 的筛选理由（从 prompt 输出抽取，用于评委 demo 时"采访 HR"）
    reasoning: str = ""
    # 0-100 评分（HR 视角对这份简历的质量打分）
    score: int = 0


class InterviewEvent(BaseModel):
    """面试事件。一次面试 = 一轮"""

    event_type: Literal[EventType.INTERVIEW] = EventType.INTERVIEW
    week: int
    candidate_id: str
    company_code: str
    job_title: str
    # 第几轮（1-起步）
    round_num: int
    # 这一轮的面试类型，例 "技术面"/"HR 面"/"压力面"
    interview_kind: str
    # 面试评分 0-100
    score: int
    # 是否通过本轮
    passed: bool
    # 面试官的关键反馈（可作为"采访 HR"时的输出）
    feedback: str = ""


class OfferEvent(BaseModel):
    """offer 发放事件"""

    event_type: Literal[EventType.OFFER_ISSUED] = EventType.OFFER_ISSUED
    week: int
    candidate_id: str
    company_code: str
    job_title: str
    # 薪资带的具体出价（万/年）
    salary_offer_wan: float
    # offer 有效期截止周（一般 +2 ~ +4 周）
    expires_week: int


class OfferResponseEvent(BaseModel):
    """候选人对 offer 的响应"""

    event_type: Literal[
        EventType.OFFER_ACCEPTED,
        EventType.OFFER_DECLINED,
        EventType.OFFER_NEGOTIATING,
    ]
    week: int
    candidate_id: str
    company_code: str
    job_title: str
    reasoning: str = ""


class NegotiationResolvedEvent(BaseModel):
    """谈判结果"""

    event_type: Literal[EventType.NEGOTIATION_RESOLVED] = EventType.NEGOTIATION_RESOLVED
    week: int
    candidate_id: str
    company_code: str
    # 是否达成新条件
    accepted: bool
    # 谈判后的最终薪资（如果接受）
    final_salary_wan: float = 0.0


class RejectionEvent(BaseModel):
    """面试后被拒事件"""

    event_type: Literal[EventType.REJECT_AFTER_INTERVIEW] = EventType.REJECT_AFTER_INTERVIEW
    week: int
    candidate_id: str
    company_code: str
    after_round: int
    reasoning: str = ""


class WithdrawEvent(BaseModel):
    """候选人主动撤回"""

    event_type: Literal[EventType.CANDIDATE_WITHDRAW] = EventType.CANDIDATE_WITHDRAW
    week: int
    candidate_id: str
    company_code: str
    reasoning: str = ""


# 联合类型，便于事件列表存储与序列化
Event = (
    ApplicationEvent
    | ScreeningEvent
    | InterviewEvent
    | OfferEvent
    | OfferResponseEvent
    | NegotiationResolvedEvent
    | RejectionEvent
    | WithdrawEvent
)
