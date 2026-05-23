"""
API 层 Pydantic schema。

字段命名严格对齐 frontend/src/types/contracts.ts 和 docs/api_contract.md。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


# ============================================================
# Simulation 会话
# ============================================================


SimStage = Literal[
    "queued",
    "extracting",
    "generating_pairs",
    "lora_training",
    "simulating",
    "done",
]


class StartSimRequest(BaseModel):
    user_id: str
    n_runs: int = 1000
    seed: int = 42


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
    key: MutationKey
    delta: float
    label: str


class CounterfactualRequest(BaseModel):
    sim_session_id: str
    mutations: list[MutationDelta]
    runs_per_variant: int = 200


class CounterfactualReport(BaseModel):
    primary_candidate_id: str
    runs_per_variant: int
    variants: list[OutcomeAggregate]


# ============================================================
# HR 采访
# ============================================================


class HRInterviewRequest(BaseModel):
    company_code: str
    user_id: str
    question: str


class HRInterviewResponse(BaseModel):
    company_code: str
    hr_name: str
    reply: str
    hidden_signal_revealed: str | None = None
