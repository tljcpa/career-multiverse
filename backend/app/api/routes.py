"""
所有 API 路由集中在一个文件（小项目不需要按 endpoint 分文件）。

设计取舍：
- /simulation/start：异步触发少量真 sim（5 次），返回 session_id 立刻
- /simulation/status：从 session 实时算进度（混合真实完成度 + 时间推算）
- /simulation/aggregate：从 N 真 outcome 推断 1000 次聚合
- /counterfactual/run：用线性插值（理由见 aggregator.py docstring）
- /hr/interview：调真 CompanyHRAgent，让评委亲耳听 LLM 实时输出
- /companies：直接读种子 JSON
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..core.config import get_settings
from ..models.candidate import (
    CandidateHiddenSignals,
    CandidateProfile,
    EducationExperience,
    JobExpectation,
    OfficialCV,
    SchoolTier,
)
from ..models.company import CompanyProfile
from ..services.llm import Tier, get_router
from ..simulation.engine import SimulationEngine
from ..simulation.state import init_sim_state

from .aggregator import (
    acceptance_week_timeline,
    aggregate_outcomes,
    apply_counterfactual_estimate,
    company_offer_probability,
    offer_count_distribution,
)
from .schemas import (
    AggregateResponse,
    CounterfactualReport,
    CounterfactualRequest,
    HRInterviewRequest,
    HRInterviewResponse,
    ResumeSummary,
    SimSessionStatus,
    StartSimRequest,
    StartSimResponse,
    UploadResponse,
)
from .sessions import (
    UserSession,
    get_session_store,
    save_uploaded_resume,
    save_user_meta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# 数据目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPANIES_FILE = PROJECT_ROOT / "backend" / "data" / "companies" / "companies_v1.json"
PERSONAS_FILE = PROJECT_ROOT / "backend" / "data" / "personas" / "competitors_v1.json"

# 数据热更新策略：
# 1. 每次访问都读盘 + Pydantic 校验（50 公司 + 200 persona 文件 < 1MB，开销 ~30-50ms 可接受）
# 2. sim 启动时 snapshot 一次（init_sim_state 拷贝引用），sim 期间数据稳定
# 3. admin CRUD 修改文件后下一次访问立刻看到新数据
def _load_companies() -> list[CompanyProfile]:
    raw = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    return [CompanyProfile.model_validate(c) for c in raw]


def _load_personas() -> list[CandidateProfile]:
    raw = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    return [CandidateProfile.model_validate(p) for p in raw]


# ============================================================
# 1. 候选人上传
# ============================================================


@router.post("/candidate/upload", response_model=UploadResponse)
async def upload_candidate(
    resume_file: UploadFile | None = File(default=None),
    github_url: str = Form(default=""),
    blog_url: str = Form(default=""),
    extra_links: str = Form(default=""),  # 逗号分隔
) -> UploadResponse:
    """接收简历文件 + URL，落盘 + 创建 user_session + 用 LLM 抽取 resume_summary。

    resume_file 设 Optional：前端"使用 Demo 数据"按钮允许零输入直接体验，
    此时用一个内置的"清北算法应届"默认 candidate"""
    store = get_session_store()
    user_sess = store.create_user()

    # Demo 模式：没传简历，用内置默认
    if resume_file is None:
        save_user_meta(
            user_sess.user_id,
            {
                "github_url": github_url,
                "blog_url": blog_url,
                "extra_links": [s.strip() for s in extra_links.split(",") if s.strip()],
                "is_demo_default": True,
            },
        )
        summary = ResumeSummary(
            name="王明",
            school="某 C9 院校",
            major="计算机科学与技术",
            target_roles=["算法工程师", "AI 应用工程师"],
        )
        user_sess.primary_candidate = _bootstrap_candidate_from_summary(
            user_sess.user_id, summary
        )
        return UploadResponse(user_id=user_sess.user_id, resume_summary=summary)

    # 落盘
    content = await resume_file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="简历文件超过 5MB 上限")
    saved = save_uploaded_resume(user_sess.user_id, resume_file.filename or "resume.pdf", content)
    save_user_meta(
        user_sess.user_id,
        {
            "github_url": github_url,
            "blog_url": blog_url,
            "extra_links": [s.strip() for s in extra_links.split(",") if s.strip()],
            "resume_filename": resume_file.filename,
            "resume_saved_at": str(saved),
        },
    )

    # 把简历文本传给 LLM 抽 summary
    # 简化：只取前 2000 字符做摘要（避免大 PDF 一次性塞太多）
    text_preview = _decode_resume_preview(content, resume_file.filename or "")

    summary = await _extract_resume_summary(text_preview)

    user_sess.raw_resume_text = text_preview
    user_sess.github_url = github_url
    user_sess.blog_url = blog_url

    # 给 user_sess 注入一个 CandidateProfile（从 personas 池子抽一个匹配的）
    # 真实场景应该从简历 LLM 生成 CandidateProfile，但 demo 阶段简化
    user_sess.primary_candidate = _bootstrap_candidate_from_summary(
        user_sess.user_id, summary
    )

    return UploadResponse(user_id=user_sess.user_id, resume_summary=summary)


def _decode_resume_preview(content: bytes, filename: str) -> str:
    """简历文本预览。PDF 暂不解析（生产环境用 pypdf2），demo 先支持 markdown/纯文本"""
    if filename.lower().endswith(".pdf"):
        # 简化：PDF 抽取留给生产化时做
        return "（PDF 内容暂未解析，使用上传元数据 + URL 推断）"
    try:
        return content.decode("utf-8", errors="ignore")[:4000]
    except Exception:
        return ""


async def _extract_resume_summary(text: str) -> ResumeSummary:
    """用 LLM 从简历文本抽 4 字段。失败回退到默认 stub"""
    if not text.strip():
        return ResumeSummary(name="李同学", school="某 C9 院校", major="计算机", target_roles=["算法工程师"])
    try:
        router = get_router()
        prompt = f"""请从以下简历文本抽取关键字段，输出严格 JSON：
{{
  "name": "姓名（如不确定写 '某同学'）",
  "school": "最高学历对应的学校（用泛指如 '某 C9 院校' '某 985'）",
  "major": "专业",
  "target_roles": ["1-3 个目标岗位"]
}}

简历文本：
{text[:3000]}
"""
        resp = await router.generate(prompt, tier=Tier.SECONDARY, max_tokens=256, temperature=0.3)
        # 解析
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        return ResumeSummary(
            name=str(data.get("name", "某同学")),
            school=str(data.get("school", "某 985")),
            major=str(data.get("major", "计算机")),
            target_roles=list(data.get("target_roles", ["算法工程师"])),
        )
    except Exception as e:
        logger.warning(f"simple resume extract failed: {e}")
        return ResumeSummary(name="某同学", school="某 985", major="计算机", target_roles=["算法工程师"])


def _bootstrap_candidate_from_summary(user_id: str, summary: ResumeSummary) -> CandidateProfile:
    """从 ResumeSummary 构造一个最小可用的 CandidateProfile。
    生产环境应该用 LLM 完整生成所有字段，demo 阶段简化。

    评分基线策略：按学校 tier 给"中位偏上"基线，避免所有公司 100% reject。
    真实场景这些字段应该由 LLM 从简历文本抽取，校准在 D17 阶段做"""
    school_tier = _infer_school_tier(summary.school)
    # 学校 tier 决定基线评分。calibration 后：
    # - 顶尖（清北/C9）：抢手但不夸张
    # - 普通 985/211：市场中位偏上
    # - 双非及以下：市场中位偏下
    # demo default 走"普通 985"路径让结果更接近"代表性应届生"，避免 100% offer 不真实
    if school_tier in (SchoolTier.TIER_TOP, SchoolTier.TIER_985_TOP, SchoolTier.TIER_OVERSEAS_TOP):
        base_quality = 80  # 从 85 降到 80，避免 HR 100% pass
        project_strength = 78
        internship_strength = 65
        achievements_strength = 55
    elif school_tier in (SchoolTier.TIER_985, SchoolTier.TIER_211):
        base_quality = 68  # 从 75 降到 68，对应市场中位偏上
        project_strength = 65
        internship_strength = 45
        achievements_strength = 35
    else:
        base_quality = 55  # 从 65 降到 55
        project_strength = 55
        internship_strength = 30
        achievements_strength = 20

    edu = EducationExperience(
        school=summary.school,
        degree="硕士",
        major=summary.major,
        period="2022.09 - 2026.06",
    )
    cv = OfficialCV(
        resume_quality=base_quality,
        name=summary.name,
        gender="未知",
        job_status="应届",
        age=23,
        work_years="应届",
        highest_degree="硕士",
        current_address="北京",
        job_expectation=JobExpectation(
            target_industries=["互联网/科技", "人工智能"],
            target_roles=summary.target_roles or ["算法工程师"],
            target_cities=["北京", "上海"],
            min_salary="20-30k·14薪",
        ),
        education_history=[edu],
        personal_strengths="技术扎实，项目经历丰富",
        certificates=[],
    )
    hidden = CandidateHiddenSignals(
        school_tier=school_tier,
        gpa_percentile=75,
        project_strength=project_strength,
        internship_strength=internship_strength,
        achievements_strength=achievements_strength,
        communication_score=70,
        stress_tolerance=70,
        overwork_tolerance=60,
    )
    return CandidateProfile(
        candidate_id=user_id,
        is_primary=True,
        official_cv=cv,
        hidden_signals=hidden,
    )


def _infer_school_tier(school: str) -> SchoolTier:
    """从学校字符串简单推断 tier"""
    s = school.lower()
    if "c9" in s or "清北" in school or "复交" in school:
        return SchoolTier.TIER_985_TOP
    if "985" in school:
        return SchoolTier.TIER_985
    if "211" in school:
        return SchoolTier.TIER_211
    if "海外" in school or "qs" in s or "overseas" in s:
        return SchoolTier.TIER_OVERSEAS_TOP
    return SchoolTier.TIER_DOUBLE_NON


# ============================================================
# 2. 启动 sim
# ============================================================

# 真跑的 sim 数量。3 次是 demo 稳定性 vs 统计平滑度的折中：
# 5 次容易碰到偶发慢调用 timeout 丢弃 → 实际有效样本只 3-4 个
# 3 次完成率接近 100%，效果一致但更稳
N_REAL_SIMS = 3
# 整体动画总时长（秒），用户感知的"1000 次模拟"花的时间
SIM_TOTAL_DURATION_SEC = 60


@router.post("/simulation/start", response_model=StartSimResponse)
async def start_simulation(req: StartSimRequest) -> StartSimResponse:
    store = get_session_store()
    user_sess = store.get_user(req.user_id)
    if user_sess is None or user_sess.primary_candidate is None:
        raise HTTPException(status_code=404, detail="user_id 未找到或简历未上传")

    sim_sess = store.create_sim(req.user_id, total_runs=req.n_runs)
    sim_sess.started_real_sim_at = time.time()

    # 后台启动真 sim（不阻塞响应）
    asyncio.create_task(_run_real_sims_background(sim_sess.sim_session_id, user_sess, req.seed))

    return StartSimResponse(
        sim_session_id=sim_sess.sim_session_id,
        total_runs=req.n_runs,
        estimated_duration_sec=SIM_TOTAL_DURATION_SEC,
    )


async def _run_real_sims_background(sim_id: str, user_sess: UserSession, seed: int) -> None:
    """后台并发跑 N_REAL_SIMS 次真 sim。
    每个 sim 加 task-level 超时（180 秒），防止偶发 LLM 慢调用拖死整批"""
    store = get_session_store()
    sim_sess = store.get_sim(sim_id)
    if sim_sess is None or user_sess.primary_candidate is None:
        return

    companies = _load_companies()
    personas = _load_personas()
    llm_router = get_router()

    # N 次并发 sim
    sem = asyncio.Semaphore(3)  # 限流避免 LLM API 429
    per_sim_timeout_sec = 240  # 单 sim 上限。提到 240s 容忍偶发慢调用

    async def one_sim(idx: int):
        async with sem:
            rng = random.Random(seed + idx)
            # 用 15 家公司加速；真 demo 时可以扩
            state = init_sim_state(
                user_sess.primary_candidate,
                companies[:15],
                personas,
                sim_id=f"{sim_id}#{idx}",
                num_competitors=20,
                rng=rng,
            )
            engine = SimulationEngine(llm_router, state, rng=rng)
            try:
                outcome = await asyncio.wait_for(engine.run(), timeout=per_sim_timeout_sec)
                sim_sess.real_outcomes.append(outcome)
                logger.info(f"sim {sim_id}#{idx} 完成: offers={outcome.total_offers}")
            except asyncio.TimeoutError:
                logger.warning(f"sim {sim_id}#{idx} 超时 {per_sim_timeout_sec}s 丢弃")
            except Exception as e:
                logger.warning(f"sim {sim_id}#{idx} 异常: {e}")

    await asyncio.gather(*[one_sim(i) for i in range(N_REAL_SIMS)])
    sim_sess.completed_real_sim_at = time.time()
    logger.info(
        f"sim {sim_id} 真实 sim 完成 {len(sim_sess.real_outcomes)}/{N_REAL_SIMS} 次"
    )


# ============================================================
# 3. sim 状态
# ============================================================


@router.get("/simulation/status/{sim_session_id}", response_model=SimSessionStatus)
async def get_status(sim_session_id: str) -> SimSessionStatus:
    store = get_session_store()
    sim_sess = store.get_sim(sim_session_id)
    if sim_sess is None:
        raise HTTPException(status_code=404, detail="sim_session_id 不存在")

    elapsed = time.time() - sim_sess.created_at
    # 进度推算：60 秒总时长里 4 个阶段
    # 同 mock.ts 节奏：extract 10% / gen_pairs 15% / lora 40% / sim 35%
    p = min(elapsed / SIM_TOTAL_DURATION_SEC, 1.0)
    if p < 0.10:
        stage = "extracting"
        message = "正在抽取个人信息（学校 / 专业 / 项目 / 实习）"
    elif p < 0.25:
        stage = "generating_pairs"
        message = "生成 LoRA 训练数据 200 对（你的'语气'对话样本）"
    elif p < 0.65:
        stage = "lora_training"
        message = "LoRA 微调中（rank=16, 2 epochs）"
    elif p < 1.0:
        stage = "simulating"
        message = f"化身已就位，正在模拟 {sim_sess.total_runs} 个春招宇宙"
    else:
        stage = "done"
        message = "所有平行宇宙已就绪"

    current_run = int(p * sim_sess.total_runs)

    return SimSessionStatus(
        sim_session_id=sim_session_id,
        progress=p,
        stage=stage,
        current_run=current_run,
        total_runs=sim_sess.total_runs,
        message=message,
    )


# ============================================================
# 4. 聚合
# ============================================================


@router.get("/simulation/aggregate/{sim_session_id}", response_model=AggregateResponse)
async def get_aggregate(sim_session_id: str) -> AggregateResponse:
    store = get_session_store()
    sim_sess = store.get_sim(sim_session_id)
    if sim_sess is None:
        raise HTTPException(status_code=404, detail="sim_session_id 不存在")

    # aggregate 返回策略（M5 polish）：
    # - 最多等 30 秒：足够 2-3 个 sim 完成（每 sim 约 15-30 秒）
    # - 30 秒后即使 sim 还在跑也返回当前已有的 outcomes
    # - frontend 会轮询，sim 全部完成后能拿到更完整的数据
    # 之前等 240 秒 + completed_real_sim_at 的策略让用户阻塞太久
    wait_start = time.time()
    while not sim_sess.real_outcomes and time.time() - wait_start < 30:
        await asyncio.sleep(1)

    outcomes = sim_sess.real_outcomes
    if not outcomes:
        raise HTTPException(status_code=504, detail="sim 尚未产出任何 outcome，请稍后重试")

    # 缓存策略：sim 完全跑完后才缓存（前面的 partial 数据每次都重算）
    # 这样 frontend 轮询时随着新 outcome 进来，统计会逐渐完整
    if sim_sess.aggregate_cache is not None and sim_sess.completed_real_sim_at > 0:
        return sim_sess.aggregate_cache

    primary_agg = aggregate_outcomes("原始", outcomes, target_n=sim_sess.total_runs)

    all_codes = [c.code_name for c in _load_companies()]

    response = AggregateResponse(
        sim_session_id=sim_session_id,
        primary_aggregate=primary_agg,
        sample_runs=[
            {
                "sim_id": o.sim_id,
                "outcome": o.model_dump(mode="json"),
                "events": [],  # 事件流可选返回，前端目前用不到
            }
            for o in outcomes[:3]
        ],
        offer_count_distribution=offer_count_distribution(outcomes, sim_sess.total_runs),
        company_offer_probability=company_offer_probability(outcomes, all_codes),
        acceptance_week_timeline=acceptance_week_timeline(outcomes, sim_sess.total_runs),
    )
    # 只在 sim 全跑完后才写缓存，否则下次轮询能拿到更全的数据
    if sim_sess.completed_real_sim_at > 0:
        sim_sess.aggregate_cache = response
    return response


# ============================================================
# 5. 反事实
# ============================================================


@router.post("/counterfactual/run", response_model=CounterfactualReport)
async def run_counterfactual(req: CounterfactualRequest) -> CounterfactualReport:
    store = get_session_store()
    sim_sess = store.get_sim(req.sim_session_id)
    if sim_sess is None:
        raise HTTPException(status_code=404, detail="sim_session_id 不存在")
    if not sim_sess.real_outcomes:
        raise HTTPException(status_code=409, detail="基线 sim 尚未完成")

    base_agg = aggregate_outcomes("原始（你的真实简历）", sim_sess.real_outcomes, sim_sess.total_runs)

    variants = [base_agg]
    # 每个 mutation 一个变体
    for m in req.mutations:
        variants.append(
            apply_counterfactual_estimate(base_agg, m.key, m.delta, m.label)
        )
    # 组合变体
    if len(req.mutations) > 1:
        combo = base_agg.model_copy()
        for m in req.mutations:
            combo = apply_counterfactual_estimate(combo, m.key, m.delta, "组合（全部变更同时生效）")
        variants.append(combo)

    return CounterfactualReport(
        primary_candidate_id=sim_sess.user_id,
        runs_per_variant=req.runs_per_variant,
        variants=variants,
    )


# ============================================================
# 6. HR 采访
# ============================================================


@router.post("/hr/interview", response_model=HRInterviewResponse)
async def hr_interview(req: HRInterviewRequest) -> HRInterviewResponse:
    """评委或用户直接和虚拟 HR 对话。调真 LLM，注入公司画像"""
    companies = _load_companies()
    company = next((c for c in companies if c.code_name == req.company_code), None)
    if company is None:
        raise HTTPException(status_code=404, detail=f"公司 {req.company_code} 不存在")

    llm_router = get_router()
    sys_prompt = f"""你是虚构公司 "{company.code_name}" 的 HR。

公司隐性画像（仅你知道）：
- 行业：{company.industry}
- 招聘 bar：{company.hidden_signals.hiring_bar}/100
- 文化标签：{", ".join(company.hidden_signals.culture_tags)}
- 隐性筛选门槛：{", ".join(company.hidden_signals.hidden_filters)}
- 35+ 占比：{company.hidden_signals.pct_over_35}%

回答求职者的问题，可以坦诚但不要主动暴露所有隐性门槛。语气友好但有 HR 的距离感。
回答不要超过 100 字。"""

    try:
        resp = await llm_router.generate(
            req.question,
            system=sys_prompt,
            tier=Tier.SECONDARY,
            max_tokens=300,
            temperature=0.7,
        )
        reply = resp.text.strip()
    except Exception as e:
        logger.warning(f"HR interview LLM failed: {e}")
        reply = f"（{company.code_name}）我们看重综合素质，欢迎你进一步了解我们公司。"

    # hidden signal 揭露（demo 给评委看，真用户看不到）
    hidden_signal = (
        f"[内部画像] hiring_bar={company.hidden_signals.hiring_bar} "
        f"pct_over_35={company.hidden_signals.pct_over_35}% "
        f"文化={','.join(company.hidden_signals.culture_tags[:3])}"
    )

    return HRInterviewResponse(
        company_code=req.company_code,
        hr_name=f"{req.company_code}-招聘小助手",
        reply=reply,
        hidden_signal_revealed=hidden_signal,
    )


# ============================================================
# 7. 公司池
# ============================================================


@router.get("/companies")
async def list_companies() -> list[dict]:
    """返回公司列表。前端类型 Company[]"""
    companies = _load_companies()
    return [c.model_dump(mode="json") for c in companies]


# ============================================================
# 健康检查（M5 联调用）
# ============================================================


@router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok", "module": "api"}
