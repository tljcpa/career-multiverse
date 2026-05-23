"""
公司画像 + 岗位 JD。两层 schema：

第一层 OfficialJD：严格对齐赛事答疑文档官方推荐的 11 字段
（《AI 大赛答疑文档》第五板块 Q2 给出的"岗位 JD 格式"图）。
这一层保证评审认得出"按官方推荐格式生成的模拟数据"。

第二层 CompanyHiddenSignals：沙盘 sim 用的隐性维度
（hiring_bar / culture_tags / 35 岁占比 等）——这些字段不存在于官方 JD，
也不存在于用户能直接查到的招聘平台。**这是我们产品的差异化核心**：
"看到 JD 字段之外的东西，应届生最想知道的隐性匹配维度"。

CompanyProfile = OfficialJD 列表 + CompanyHiddenSignals（双层组合）
"""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# 第一层：官方推荐字段（严格对齐答疑文档 Q2 图）
# ============================================================


class OfficialJD(BaseModel):
    """官方推荐岗位 JD 格式（11 字段）。
    一家公司可有多个 JD（不同岗位）"""

    # 职位名称，例: "后端工程师", "AI 算法工程师"
    job_title: str
    # 职类名称（更宽的分类），例: "技术", "产品", "运营"
    job_category: str
    # 薪资。允许范围/k/年薪等多种表达，例: "15-25k·15薪", "本科 20-30 万/年"
    salary: str
    # 年限要求，例: "应届", "1-3 年", "5-10 年"
    years_required: str
    # 学历要求，例: "本科及以上", "硕士", "不限"
    degree_required: str
    # 城市要求
    city_required: str
    # 职位关键词，例: ["Python", "FastAPI", "微服务"]
    keywords: list[str] = Field(default_factory=list)
    # 职位描述（长文本，HR 用语风格）
    description: str
    # 公司名称。在 demo 中用代号（A 厂/B 厂），合规上挂"基于公开数据建模"水印
    company_name: str
    # 上班地址
    work_address: str
    # 发布时间
    publish_date: date


# ============================================================
# 第二层：隐性维度（产品差异化卖点）
# ============================================================


class HiringStyle(str, Enum):
    """招聘风格刻板印象。决定虚拟 HR 的提问倾向"""

    PEDIGREE_FIRST = "pedigree_first"  # 看学历背景
    PROJECT_HEAVY = "project_heavy"  # 看项目深度
    LEETCODE_HEAVY = "leetcode_heavy"  # 看算法题
    CULTURE_FIT = "culture_fit"  # 看文化匹配
    CASE_BASED = "case_based"  # 看商业 case sense


class CompanyHiddenSignals(BaseModel):
    """沙盘 sim 用的隐性信号——官方 JD 字段看不到，但应届生择业关心。
    这些字段构成我们产品差异化的核心数据维度"""

    # 招聘门槛 0-100。综合判断"普通应届生进入概率"，影响录取概率分布
    hiring_bar: int = Field(..., ge=0, le=100)

    # 招聘风格。影响 HR Agent 的提问倾向
    hiring_style: HiringStyle

    # 文化标签。例: ["996", "扁平", "P 级森严", "派系", "稳定"]
    # 给 HR Agent 的 system prompt 注入，影响其行为风格
    culture_tags: list[str] = Field(default_factory=list)

    # 业务增长性 0-100。低=夕阳/裁员高发，高=扩张。影响"入职后体验"模拟
    business_growth: int = Field(50, ge=0, le=100)

    # 35 岁以上员工占比估计 0-100。低=年龄歧视严重
    pct_over_35: int = Field(20, ge=0, le=100)

    # 隐藏门槛（JD 字面不写但实际筛简历会用）。
    # 例: ["学历卡 985", "性别隐性偏好", "本地户口加分"]
    # 这是产品最锋利的卖点之一："我们的 sim 算的是 JD 不写的事"
    hidden_filters: list[str] = Field(default_factory=list)


# ============================================================
# 顶层组合
# ============================================================


class CompanyProfile(BaseModel):
    """单家虚拟公司的完整画像。
    code_name 是 demo 用代号；inspired_by_hint 是内部建模溯源（不出现在 demo UI）"""

    # ===== 标识 =====
    code_name: str = Field(..., description="公司代号，如 'A 厂'")
    inspired_by_hint: str = Field("", description="灵感来源（仅内部 doc 用，不出 UI）")

    # ===== 公司基本面 =====
    industry: str  # 行业大类，例: "互联网", "金融", "国企"
    size_label: str  # 规模标签，例: "<100 人", "5000-50000 人", "MEGA"
    headquarters_city: str

    # ===== 该公司在沙盘里的 JD 列表（官方字段） =====
    # 一家公司多个岗位，sim 时按岗位分别匹配
    job_postings: list[OfficialJD] = Field(default_factory=list)

    # ===== 隐性维度（产品差异化） =====
    hidden_signals: CompanyHiddenSignals

    # ===== 数据治理 =====
    # 数据来源：synthetic 合成 / public_aggregated 公开聚合
    data_source: Literal["public_aggregated", "synthetic"] = "synthetic"
    # 画像生成日期，sim 时按时效衰减
    generated_at: date = Field(default_factory=date.today)
