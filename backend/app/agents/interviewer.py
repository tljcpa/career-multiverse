"""
面试官 Agent。

模拟一轮面试：基于 候选人画像 + 公司 hiring_style → 评分 + feedback。
和 CompanyHRAgent 分开是因为：
1. demo 时评委想"采访面试官"，面试官有独立的人格 + 输出
2. HR 决策 vs 面试评分是两类不同的认知任务，分开 prompt 质量更好

设计：
- 用 SECONDARY tier
- 不需要保持对话状态，每轮独立打分
"""

from __future__ import annotations

import json
import logging
import random

from app.services.llm import Tier

from .base import AgentBase
from ..models.candidate import CandidateProfile
from ..models.company import CompanyProfile, HiringStyle
from ..simulation.events import Event, InterviewEvent
from ..simulation.state import SimulationState

logger = logging.getLogger(__name__)


# 不同 hiring_style 决定面试 kind
HIRING_STYLE_INTERVIEW_KIND: dict[HiringStyle, list[str]] = {
    HiringStyle.LEETCODE_HEAVY: ["算法一面", "算法二面", "系统设计面", "HR 面"],
    HiringStyle.PROJECT_HEAVY: ["项目深挖一面", "项目深挖二面", "技术 leader 面", "HR 面"],
    HiringStyle.PEDIGREE_FIRST: ["简历追问面", "专业知识面", "导师面", "HR 面"],
    HiringStyle.CULTURE_FIT: ["技术初面", "behavioral 面", "价值观面", "HR 终面"],
    HiringStyle.CASE_BASED: ["case interview 一", "case interview 二", "partner 面", "HR 面"],
}


SYSTEM_PROMPT_TEMPLATE = """你是 "{code_name}" 公司的面试官 AI。这是第 {round_num} 轮：{interview_kind}。

公司招聘风格：{hiring_style_desc}
公司文化：{culture_tags}

你的行为模式：
- 严格按公司风格评估
- 给 0-100 评分（60 是及格线）
- 给一段一句话的关键反馈，可用作"采访面试官"输出

输出严格 JSON，不要 markdown 包裹。
"""


class InterviewerAgent(AgentBase):
    DEFAULT_TIER = Tier.SECONDARY

    def __init__(self, router, company: CompanyProfile) -> None:
        super().__init__(router)
        self.company = company

    def interview_kind(self, round_num: int) -> str:
        """第几轮对应什么类型的面试"""
        kinds = HIRING_STYLE_INTERVIEW_KIND.get(
            self.company.hidden_signals.hiring_style,
            ["技术面", "项目面", "leader 面", "HR 面"],
        )
        idx = min(round_num - 1, len(kinds) - 1)
        return kinds[idx]

    async def conduct_interview(
        self,
        state: SimulationState,
        candidate: CandidateProfile,
        job_title: str,
        round_num: int,
    ) -> Event:
        """进行一轮面试，返回 InterviewEvent"""
        kind = self.interview_kind(round_num)
        cv = candidate.official_cv

        # 候选人简介（这次面试的输入）
        cand_brief = {
            "candidate_id": candidate.candidate_id,
            "school_tier": candidate.hidden_signals.school_tier.value,
            "highest_degree": cv.highest_degree,
            "major": cv.education_history[0].major if cv.education_history else "?",
            "resume_quality": cv.resume_quality,
            "project_strength": candidate.hidden_signals.project_strength,
            "internship_strength": candidate.hidden_signals.internship_strength,
            "achievements_strength": candidate.hidden_signals.achievements_strength,
            "communication_score": candidate.hidden_signals.communication_score,
            "stress_tolerance": candidate.hidden_signals.stress_tolerance,
        }

        prompt = f"""候选人画像：
{json.dumps(cand_brief, ensure_ascii=False, indent=2)}

岗位：{job_title}
本轮：第 {round_num} 轮，{kind}

请基于候选人画像 + 公司风格，模拟本轮面试并打分。

输出格式（严格 JSON）:
{{
  "score": 0-100,
  "passed": true|false,
  "feedback": "一句话关键反馈（可作为'采访面试官'输出）"
}}"""

        # 构建 system prompt
        from .company_hr import HIRING_STYLE_DESCRIPTIONS

        system = SYSTEM_PROMPT_TEMPLATE.format(
            code_name=self.company.code_name,
            round_num=round_num,
            interview_kind=kind,
            hiring_style_desc=HIRING_STYLE_DESCRIPTIONS.get(
                self.company.hidden_signals.hiring_style, ""
            ),
            culture_tags=", ".join(self.company.hidden_signals.culture_tags),
        )

        try:
            resp = await self._call_llm(
                prompt, system=system, max_tokens=512, temperature=0.5
            )
            data = self._parse_json_response(resp.text)
            score = int(data.get("score", 0)) if isinstance(data.get("score"), (int, float)) else 0
            passed = bool(data.get("passed", False))
            feedback = str(data.get("feedback", ""))[:300]
        except Exception as e:
            logger.warning(
                f"Interviewer({self.company.code_name}) LLM 失败，降级: {e}"
            )
            score, passed, feedback = self._fallback_score(candidate)

        return InterviewEvent(
            week=state.current_week,
            candidate_id=candidate.candidate_id,
            company_code=self.company.code_name,
            job_title=job_title,
            round_num=round_num,
            interview_kind=kind,
            score=score,
            passed=passed,
            feedback=feedback,
        )

    def _fallback_score(self, candidate: CandidateProfile) -> tuple[int, bool, str]:
        """LLM 失败时：基于简历质量 + 公司 hiring_bar 估分"""
        rng = random.Random()
        base = candidate.official_cv.resume_quality
        # 高 hiring_bar 的公司打分更严
        bar_penalty = (self.company.hidden_signals.hiring_bar - 50) // 3
        score = max(0, min(100, base - bar_penalty + rng.randint(-10, 10)))
        passed = score >= 60
        return score, passed, "（规则降级）"
