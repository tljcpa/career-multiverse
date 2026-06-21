"""
API 层 Pydantic schema。

字段命名严格对齐 frontend/src/types/contracts.ts 和 docs/api_contract.md。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 候选人上传
# ============================================================


class ResumeSummary(BaseModel):
    name: str
    school: str
    major: str
    target_roles: list[str]


class UploadResponse(BaseModel):
    user_id: str
    resume_summary: ResumeSummary


class CompositeBreakdown(BaseModel):
    """综合分的每项贡献明细，让评委看到 83 怎么来的（不再黑盒）"""
    base_avg: float  # (项目 + 实习 + 成就) / 3
    school_bonus: int  # 学校档加成
    school_tier_label: str  # 如"985 头部 / C9"
    degree_bonus: int  # 学历加成
    degree_label: str  # 如"硕士"
    comm_adjust: float  # 沟通修正 (沟通 - 50) * 0.1
    raw_total: float  # clamp 前
    final: float  # clamp 后（即 composite_score）


class CandidateSignalsBrief(BaseModel):
    """前端展示用的求职者画像五维（candidate.hidden_signals 子集）"""
    school_tier: str
    school_tier_label: str
    gpa_percentile: int
    project_strength: int
    internship_strength: int
    achievements_strength: int
    communication_score: int
    composite_score: float  # 综合分（用于市场匹配）
    composite_breakdown: CompositeBreakdown


class CompanyMatchItem(BaseModel):
    code_name: str
    industry: str
    hiring_bar: int
    gap: int  # composite_score - hiring_bar，正=够格，负=有差距
    label: str  # "够格" / "挑战" / "保底"


class CoachingResponse(BaseModel):
    """Report 页关键结论 - LLM 个性化建议"""
    summary: str  # 一段话总结（替代模板文案）
    advices: list[str]  # 1-3 条可执行建议（如"项目含金量是你的瓶颈，建议接 1-2 个开源贡献"）
    biggest_gap: str  # 五维里最差的维度名 + 数值
    top_strength: str  # 五维里最强的维度名 + 数值


class CandidateProfileResponse(BaseModel):
    """profile 页用：resume_summary + 五维画像 + Top-5 候选公司 + 评分理由"""
    user_id: str
    resume_summary: ResumeSummary
    signals: CandidateSignalsBrief
    top_companies: list[CompanyMatchItem]
    market_summary: str  # 一句话总结
    # 每维评分理由（透明化）。key: dim 名称，value: 自然语言理由
    # 真实简历：LLM 真评估出来的；demo 模式：基于 school_tier+major 推断的可读理由
    reasoning: dict[str, str] = Field(default_factory=dict)


# ============================================================
# Simulation 会话
# ============================================================


SimStage = Literal[
    "queued",
    "extracting",
    "matching_market",
    "sim_running",
    "simulating",
    "done",
]


class StartSimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(..., min_length=1, max_length=64)
    n_runs: int = Field(1000, ge=1, le=10000)
    seed: int = Field(42, ge=0, le=2**31)


class StartSimResponse(BaseModel):
    sim_session_id: str
    total_runs: int
    estimated_duration_sec: int


class SimSessionStatus(BaseModel):
    sim_session_id: str
    progress: float  # 0..1
    stage: SimStage
    current_run: int
    total_runs: int
    message: str


# ============================================================
# 聚合结果
# ============================================================


class OutcomeAggregate(BaseModel):
    label: str
    n_runs: int
    offer_rate: float
    mean_offers: float
    mean_applications: float
    mean_interviews: float
    mean_salary_when_settled: float
    median_salary_when_settled: float
    settled_rate: float
    destination_distribution: dict[str, int]
    week_settled_distribution: dict[str, int]


class CompanyOfferProbability(BaseModel):
    company_code: str
    probability: float


class AcceptanceWeekPoint(BaseModel):
    week: int
    count: int


class AggregateResponse(BaseModel):
    sim_session_id: str
    primary_aggregate: OutcomeAggregate
    # 抽样 sim_run（供前端决策树展示用）
    sample_runs: list[dict]
    # frontend 期望的额外字段（mock.ts 已经定义好这套结构）
    offer_count_distribution: dict[str, int]
    company_offer_probability: list[CompanyOfferProbability]
    acceptance_week_timeline: list[AcceptanceWeekPoint]


# ============================================================
# 反事实
# ============================================================


MutationKey = Literal[
    "resume_quality",
    "project_strength",
    "overwork_tolerance",
    "school_tier",
    "risk_appetite",
]


class MutationDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: MutationKey
    # delta 业务含义：评分增量（resume/project 维度 ±20-30 / school_tier ±2 档），
    # 加 bound 防 NaN/Inf/极端值（之前 LLM input audit 抓到 delta=10000 / NaN 会产出不一致结果）
    delta: float = Field(..., ge=-200, le=200)
    label: str = Field(..., min_length=1, max_length=100)


class CounterfactualRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sim_session_id: str = Field(..., min_length=1, max_length=64)
    mutations: list[MutationDelta] = Field(..., min_length=1, max_length=10)
    runs_per_variant: int = Field(200, ge=1, le=2000)


class CounterfactualReport(BaseModel):
    primary_candidate_id: str
    runs_per_variant: int
    variants: list[OutcomeAggregate]


# ============================================================
# HR 采访
# ============================================================


class HRInterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_code: str = Field(..., min_length=1, max_length=64)
    user_id: str = Field(..., min_length=1, max_length=64)
    question: str = Field(..., min_length=1, max_length=500)  # 防 prompt 注入 + DB 爆


class HRInterviewResponse(BaseModel):
    company_code: str
    hr_name: str
    reply: str
    hidden_signal_revealed: str | None = None
