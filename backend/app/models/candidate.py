"""
求职者画像 + 简历 CV。两层 schema：

第一层 OfficialCV：严格对齐赛事答疑文档官方推荐的 14 字段
（《AI 大赛答疑文档》第五板块 Q2 给出的"简历 CV 格式"图）。

第二层 CandidateHiddenSignals：沙盘 sim 用的隐性维度
（学校 tier 量化 / 项目含金量 / 软性特征等）——官方字段里"工作经历"是文本，
但 sim 需要数值化信号才能做大规模匹配。这一层把官方字段抽象成可计算的信号。

CandidateProfile = OfficialCV + CandidateHiddenSignals
"""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# 第一层：官方推荐字段（严格对齐答疑文档 Q2 图）
# ============================================================


class JobExpectation(BaseModel):
    """求职期望子结构（官方"求职期望"字段的展开）"""

    target_industries: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    target_cities: list[str] = Field(default_factory=list)
    min_salary: str = ""  # "15k·14薪" 这种文本表达


class WorkExperience(BaseModel):
    """工作/实习经历单项"""

    company: str
    role: str
    # 起止时间用字符串保留原文格式，例: "2024.06 - 2024.09"
    period: str
    description: str = ""


class ProjectExperience(BaseModel):
    """项目经历单项"""

    name: str
    role: str = ""
    period: str = ""
    description: str = ""


class EducationExperience(BaseModel):
    """教育经历单项"""

    school: str
    degree: str
    major: str
    period: str  # "2022.09 - 2026.06"


class OfficialCV(BaseModel):
    """官方推荐简历 CV 格式（14 字段）"""

    # 简历质量评分（官方字段，用 0-100 即可）
    resume_quality: int = Field(50, ge=0, le=100)
    name: str
    gender: Literal["男", "女", "未知"] = "未知"
    # 求职状态，例: "在校待找工作", "在职考虑机会", "应届"
    job_status: str
    age: int = Field(..., ge=15, le=60)
    # 工作年限，例: "应届", "1 年", "3-5 年"
    work_years: str
    # 最高学历，例: "本科", "硕士", "博士"
    highest_degree: str
    # 现居地址
    current_address: str
    # 求职期望（嵌套）
    job_expectation: JobExpectation
    # 工作/实习经历
    work_internship_history: list[WorkExperience] = Field(default_factory=list)
    # 项目经历
    project_history: list[ProjectExperience] = Field(default_factory=list)
    # 教育经历
    education_history: list[EducationExperience] = Field(default_factory=list)
    # 个人优势（自我评价，长文本）
    personal_strengths: str = ""
    # 资格证书
    certificates: list[str] = Field(default_factory=list)


# ============================================================
# 第二层：隐性信号（沙盘 sim 用的数值化抽象）
# ============================================================


class SchoolTier(str, Enum):
    """学校档次。中国校招最隐性也最权重的筛选维度"""

    TIER_TOP = "top"  # 清北复交
    TIER_985_TOP = "985_top"  # C9/985 头部
    TIER_985 = "985"  # 普通 985
    TIER_211 = "211"
    TIER_DOUBLE_NON = "double_non"  # 双非一本
    TIER_LOWER = "lower"  # 二本及以下
    TIER_OVERSEAS_TOP = "overseas_top"  # 海外 QS 100 内
    TIER_OVERSEAS_OTHER = "overseas_other"
    TIER_UPGRADE_FROM_VOCATIONAL = "upgrade_from_vocational"  # 专升本（统招）
    TIER_VOCATIONAL = "vocational"  # 专科 / 高职


class CandidateHiddenSignals(BaseModel):
    """沙盘 sim 用的数值化抽象信号。
    本质是把官方 CV 字段（多为文本）转成可计算的标量/标签"""

    # 学校档次（从 education_history 推断）
    school_tier: SchoolTier
    # 本专业 GPA 排名分位数
    gpa_percentile: int = Field(50, ge=0, le=100)

    # ===== 经历含金量评分（从经历文本推断） =====
    project_strength: int = Field(50, ge=0, le=100)
    internship_strength: int = Field(0, ge=0, le=100)
    achievements_strength: int = Field(0, ge=0, le=100)  # 竞赛/论文/开源

    # ===== 软性特征（影响面试表现，从对话或简历推断） =====
    communication_score: int = Field(50, ge=0, le=100)
    stress_tolerance: int = Field(50, ge=0, le=100)
    # 加班接受度 0-100。0=拒绝，100=996 可
    overwork_tolerance: int = Field(50, ge=0, le=100)


# ============================================================
# 顶层组合
# ============================================================


class CandidateProfile(BaseModel):
    """求职者完整画像 = 官方 CV + 隐性信号 + 原始材料引用"""

    candidate_id: str
    # 是否真人主用户。True = 主用户（值得做 LoRA），False = 沙盘竞争者
    is_primary: bool = False

    # ===== 官方字段（生成符合赛事推荐格式的模拟简历） =====
    official_cv: OfficialCV

    # ===== 隐性信号（沙盘 sim 用） =====
    hidden_signals: CandidateHiddenSignals

    # ===== 主用户专属（竞争者不填） =====
    # 原始材料引用，用于 LoRA 训练数据生成
    raw_resume_path: str = ""
    raw_github_url: str = ""
    raw_blog_urls: list[str] = Field(default_factory=list)


# ============================================================
# Simulation 决策记录（用于反事实分析）
# ============================================================


class SimulationDecision(BaseModel):
    """sim 过程中分身做的一个决策点"""

    timestamp_day: int  # sim 内的天数（1-90）
    decision_type: Literal[
        "apply",  # 投递
        "accept_interview",  # 接受面试
        "decline_interview",  # 拒绝面试
        "accept_offer",  # 接受 offer
        "decline_offer",  # 拒绝 offer
        "negotiate",  # 谈判
    ]
    company_code: str
    detail: str = ""
