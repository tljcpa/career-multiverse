"""
Agent 基类。

所有 Agent 共享：
- LLM router 引用（决定调用哪个 tier）
- prompt 构造与解析的 helper
- 失败兜底（LLM 返回不合规时回退到规则决策）

为什么不用 LangChain / LangGraph：
- 这俩抽象层主要价值在"对话 memory / 工具调用 / 路径分支"，我们都不需要
- 我们的 Agent 本质是"接 state，返回 JSON 决策"的纯函数式，自己包一层更轻
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm import LLMRouter, LLMResponse, Tier

logger = logging.getLogger(__name__)


class AgentBase:
    """Agent 基类。子类实现具体 prompt 与决策逻辑"""

    # 默认 tier，子类按需覆盖
    DEFAULT_TIER: Tier = Tier.SECONDARY

    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def _call_llm(
        self,
        prompt: str,
        *,
        system: str = "",
        tier: Tier | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return await self._router.generate(
            prompt,
            system=system,
            tier=tier or self.DEFAULT_TIER,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """LLM 偶尔会用 ``` 包裹 JSON"""
        t = text.strip()
        if t.startswith("```"):
            first_nl = t.find("\n")
            if first_nl > 0:
                t = t[first_nl + 1 :]
            if t.endswith("```"):
                t = t[:-3]
        return t.strip()

    @classmethod
    def _parse_json_response(cls, text: str) -> Any:
        """从 LLM 返回里解析 JSON。失败时尝试提取第一个 {} 或 [] 块。
        若仍失败抛 ValueError 由调用方决定降级到规则"""
        cleaned = cls._strip_code_fences(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # 兜底：找第一个完整的 JSON 对象或数组
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = cleaned.find(open_ch)
            if start < 0:
                continue
            # 用括号深度匹配找完整片段
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(cleaned)):
                c = cleaned[i]
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start : i + 1])
                        except json.JSONDecodeError:
                            break
        # 最后兜底：抛错
        # 截断 raw 避免日志过长
        snippet = re.sub(r"\s+", " ", text)[:300]
        raise ValueError(f"无法解析 LLM JSON 输出: {snippet!r}")
