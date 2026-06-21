"""
求职者分身 Agent。

主用户的 AI 化身。每周做两类决策：
1. 本周投哪几家公司（act_apply_phase）
2. 对手上待响应的 offer 是接 / 拒 / 谈（act_offer_phase）

设计：
- 用 PRIMARY tier（主角，质量优先）
- 每次决策返回结构化 JSON，由 engine 转成 events
- LLM 出错时降级到规则决策（保证 sim 永远不会卡死）
"""

from __future__ import annotations

import json
import logging
import random

from app.services.llm import Tier

from .base import AgentBase
from ..models.candidate import CandidateProfile
from ..simulation.events import (
    ApplicationEvent,
    Event,
    EventType,
    OfferResponseEvent,
)
from ..simulation.state import SimulationState

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个虚构应届生求职者的 AI 决策化身。你只产生 JSON 决策，不产生任何解释文字。

你的身份: 春招中的应届生，目标是拿到尽可能符合自身偏好与能力匹配度的 offer。
你的行为模式:
- 不投每一家公司，只挑符合期望 + 自己有合理通过概率的
- 不会盲目接 offer，会权衡薪资 / 行业 / 加班 / 公司前景
- 手上有多个 offer 时知道谈判
- 早期投得激进些（试探市场），中期收缩到目标公司，后期保底

输出格式：严格 JSON。不要 markdown ``` 包裹，不要任何前后解释文字。
"""


class CandidateAgent(AgentBase):
    """求职者分身 Agent。主用户的 AI 化身"""

    DEFAULT_TIER = Tier.PRIMARY

    def __init__(self, router, candidate: CandidateProfile) -> None:
        super().__init__(router)
        self.candidate = candidate

    # ===== 决策 1：本周投哪几家 =====

    async def act_apply_phase(self, state: SimulationState) -> list[Event]:
        """本周投递决策。返回 ApplicationEvent 列表"""
        applied = state.applied_companies(self.candidate.candidate_id)
        # 候选公司：还没投过的
        available_companies = [
            c for c in state.companies if c.code_name not in applied
        ]
        if not available_companies:
            return []

        # 简化策略：每周最多产生 5 条投递（避免 prompt 太长 + LLM 太多）
        # 把候选列表压缩成精简 JSON 提供给 LLM
        company_summaries = []
        for c in available_companies[:30]:  # 一次最多看 30 家，避免 prompt 爆炸
            # 选第一个 JD 作为代表
            if not c.job_postings:
                continue
            jd = c.job_postings[0]
            company_summaries.append({
                "code_name": c.code_name,
                "industry": c.industry,
                "size": c.size_label,
                "first_job": jd.job_title,
                "salary": jd.salary,
                "city": jd.city_required,
                "keywords": jd.keywords[:5],
                "hidden_signals_visible_to_candidate": {
                    # 候选人只能看到部分隐性信号（实际就业是这样）
                    "culture_tags": c.hidden_signals.culture_tags[:3],
                },
            })

        # 主用户 self-view
        cv = self.candidate.official_cv
        candidate_brief = {
            "school_tier": self.candidate.hidden_signals.school_tier.value,
            "major": cv.education_history[0].major if cv.education_history else "?",
            "highest_degree": cv.highest_degree,
            "target_industries": cv.job_expectation.target_industries,
            "target_roles": cv.job_expectation.target_roles,
            "target_cities": cv.job_expectation.target_cities,
            "min_salary": cv.job_expectation.min_salary,
            "overwork_tolerance": self.candidate.hidden_signals.overwork_tolerance,
            "project_strength": self.candidate.hidden_signals.project_strength,
        }

        # 投递历史摘要
        active = state.primary_active_pipelines()
        offer_count = sum(
            1 for p in state.primary_applications() if p.stage == "offered"
        )

        prompt = f"""现在是春招第 {state.current_week + 1} / 13 周。

你的画像：
{json.dumps(candidate_brief, ensure_ascii=False, indent=2)}

候选公司池（还没投过的）：
{json.dumps(company_summaries, ensure_ascii=False, indent=2)}

你当前状态：
- 已有 {len(active)} 个 pipeline 在进行中
- 已经拿到 {offer_count} 个 offer 待响应

请决定本周投哪几家（0-5 家）。

输出格式（严格 JSON）:
{{
  "applications": [
    {{"company_code": "代号", "motivation": "为什么投这家（一句话）"}},
    ...
  ]
}}

如果本周不投任何家（比如手上 offer 够了），applications 留空数组。"""

        try:
            resp = await self._call_llm(
                prompt, system=SYSTEM_PROMPT, max_tokens=2048, temperature=0.7
            )
            data = self._parse_json_response(resp.text)
            apps = data.get("applications", [])
            if not isinstance(apps, list):
                return []
        except Exception as e:
            logger.warning(f"CandidateAgent apply LLM 失败，降级到规则: {e}")
            return self._fallback_apply(available_companies, n=2)

        events: list[Event] = []
        for a in apps:
            if not isinstance(a, dict):
                continue
            code = a.get("company_code", "").strip()
            company = state.company_by_code(code)
            if company is None or not company.job_postings:
                continue
            # 取第一个 JD
            jd = company.job_postings[0]
            events.append(
                ApplicationEvent(
                    week=state.current_week,
                    candidate_id=self.candidate.candidate_id,
                    company_code=code,
                    job_title=jd.job_title,
                    motivation=str(a.get("motivation", ""))[:200],
                )
            )
        return events

    # ===== 决策 2：响应待回的 offer =====

    async def act_offer_phase(self, state: SimulationState) -> list[Event]:
        """对所有待响应的 offer 做决策"""
        pending = state.primary_pending_offers()
        if not pending:
            return []

        cv = self.candidate.official_cv
        candidate_brief = {
            "target_industries": cv.job_expectation.target_industries,
            "min_salary": cv.job_expectation.min_salary,
            "overwork_tolerance": self.candidate.hidden_signals.overwork_tolerance,
        }

        offers_brief = []
        for p in pending:
            company = state.company_by_code(p.company_code)
            if company is None:
                continue
            offers_brief.append({
                "company_code": p.company_code,
                "job_title": p.job_title,
                "salary_wan": p.offer_salary_wan,
                "industry": company.industry,
                "culture_tags": company.hidden_signals.culture_tags[:3],
                "expires_week": p.offer_expires_week,
            })

        # 已接受的 offer（最多 1 个）
        accepted = state.primary_accepted_offer()
        already_accepted = None
        if accepted:
            already_accepted = {
                "company_code": accepted.company_code,
                "salary_wan": accepted.offer_salary_wan,
            }

        weeks_remaining = 13 - (state.current_week + 1)
        urgency_hint = ""
        if weeks_remaining <= 3:
            urgency_hint = f"""

【紧迫提示】只剩 {weeks_remaining} 周春招就结束了。继续 wait 风险大：
- 心仪公司若还没给 offer，后面可能也不会给
- 已有 offer 不锁定，可能被对手抢走 HC
- 强烈建议：从手上 offer 里选**最符合你画像**的一家 accept，其余 decline。
- 不应再有任何 wait（除非有 active 面试在最后阶段且公司明确说本周内出结果）"""

        prompt = f"""现在是春招第 {state.current_week + 1} / 13 周。剩余 {weeks_remaining} 周。

你的画像（关键偏好）：
{json.dumps(candidate_brief, ensure_ascii=False, indent=2)}

你已接受的 offer（如果有）：
{json.dumps(already_accepted, ensure_ascii=False) if already_accepted else "无"}

当前待响应的 offer：
{json.dumps(offers_brief, ensure_ascii=False, indent=2)}

请对每个 offer 做决策：
- accept: 接受（注意：接受一个就不能再接其他 offer）
- decline: 拒绝
- wait: 等几周再决定（offer 在 expires_week 失效前都可以等）
- negotiate: 谈判（要求加薪）
{urgency_hint}

输出格式（严格 JSON）:
{{
  "decisions": [
    {{"company_code": "代号", "action": "accept|decline|wait|negotiate", "reasoning": "理由一句话"}},
    ...
  ]
}}

约束：最多一个 accept。"""

        try:
            resp = await self._call_llm(
                prompt, system=SYSTEM_PROMPT, max_tokens=2048, temperature=0.5
            )
            data = self._parse_json_response(resp.text)
            decisions = data.get("decisions", [])
            if not isinstance(decisions, list):
                return []
        except Exception as e:
            logger.warning(f"CandidateAgent offer LLM 失败，降级到规则: {e}")
            return self._fallback_offer_response(pending, state)

        # engine 层硬约束：剩余 < 3 周仍 wait 会被强制升级为 accept 最高薪资
        weeks_remaining_check = 13 - (state.current_week + 1)
        force_accept_best = weeks_remaining_check <= 3 and accepted is None

        # 找当前 offer 池最高薪资作为"被迫 accept"的目标
        best_pending = max(pending, key=lambda x: x.offer_salary_wan) if pending else None

        events: list[Event] = []
        accept_count = 0
        for d in decisions:
            if not isinstance(d, dict):
                continue
            code = d.get("company_code", "")
            action = d.get("action", "wait")
            reasoning = str(d.get("reasoning", ""))[:200]
            p = next(
                (x for x in pending if x.company_code == code), None
            )
            if p is None:
                continue
            # 紧迫期：把 LLM 的 wait 升级为 accept（仅升级最高薪资那家），其余 decline
            if force_accept_best and action == "wait":
                if best_pending and code == best_pending.company_code and accept_count == 0:
                    action = "accept"
                    reasoning = "（紧迫期强制：剩余 < 3 周，接受最高薪资 offer）"
                else:
                    action = "decline"
                    reasoning = "（紧迫期：已选最高薪资 offer，拒绝其他）"
            # 强约束：最多 1 个 accept
            if action == "accept":
                if accept_count >= 1 or accepted is not None:
                    action = "wait"
                else:
                    accept_count += 1

            if action == "accept":
                events.append(
                    OfferResponseEvent(
                        event_type=EventType.OFFER_ACCEPTED,
                        week=state.current_week,
                        candidate_id=self.candidate.candidate_id,
                        company_code=code,
                        job_title=p.job_title,
                        reasoning=reasoning,
                    )
                )
            elif action == "decline":
                events.append(
                    OfferResponseEvent(
                        event_type=EventType.OFFER_DECLINED,
                        week=state.current_week,
                        candidate_id=self.candidate.candidate_id,
                        company_code=code,
                        job_title=p.job_title,
                        reasoning=reasoning,
                    )
                )
            elif action == "negotiate":
                events.append(
                    OfferResponseEvent(
                        event_type=EventType.OFFER_NEGOTIATING,
                        week=state.current_week,
                        candidate_id=self.candidate.candidate_id,
                        company_code=code,
                        job_title=p.job_title,
                        reasoning=reasoning,
                    )
                )
            # action == "wait" 不产生事件，下周再决定

        return events

    # ===== 兜底规则 =====

    def _fallback_apply(self, available, n: int = 2) -> list[Event]:
        """LLM 失败时的规则降级：随机投 n 家"""
        rng = random.Random()
        picks = rng.sample(available, k=min(n, len(available)))
        events: list[Event] = []
        for c in picks:
            if not c.job_postings:
                continue
            events.append(
                ApplicationEvent(
                    week=0,  # 调用方应该覆盖
                    candidate_id=self.candidate.candidate_id,
                    company_code=c.code_name,
                    job_title=c.job_postings[0].job_title,
                    motivation="（规则降级）",
                )
            )
        return events

    def _fallback_offer_response(self, pending, state) -> list[Event]:
        """LLM 失败时：薪资最高的 accept，其他 decline"""
        if not pending:
            return []
        best = max(pending, key=lambda p: p.offer_salary_wan)
        events: list[Event] = [
            OfferResponseEvent(
                event_type=EventType.OFFER_ACCEPTED,
                week=state.current_week,
                candidate_id=self.candidate.candidate_id,
                company_code=best.company_code,
                job_title=best.job_title,
                reasoning="（规则降级：薪资最高）",
            )
        ]
        for p in pending:
            if p.company_code == best.company_code:
                continue
            events.append(
                OfferResponseEvent(
                    event_type=EventType.OFFER_DECLINED,
                    week=state.current_week,
                    candidate_id=self.candidate.candidate_id,
                    company_code=p.company_code,
                    job_title=p.job_title,
                    reasoning="（规则降级）",
                )
            )
        return events
