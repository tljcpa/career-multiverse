"""
LLM 抽象层。

设计目标（按维护性优先级排序）：
1. 业务代码只关心"用什么档位的模型"，不关心具体 provider
   ——业务代码调 router.generate(prompt, tier=Tier.PRIMARY)
2. 切换模型 = 改 .env 一行，0 行业务代码变动
3. 加新 provider（Kimi/GLM/豆包）= 加一行 .env，0 行代码变动
   ——因为绝大多数大陆模型都兼容 OpenAI 协议
4. 加非 OpenAI 协议的 provider（如 Claude）= 实现一个 LLMProvider 协议类
   ——目前不实现，等真有需求再加

为什么不一开始就支持非 OpenAI 协议：
- 系统 prompt：don't design for hypothetical future requirements
- Protocol 已经留好接口，未来加 ClaudeProvider 即可
- 现在多写一份只是无用代码

为什么不做 fallback（DeepSeek 挂了自动切 Qwen）：
- 增加行为不确定性，1000 次 sim 时谁也说不清结果是哪个模型出的
- 现有 3 次重试已经覆盖偶发抖动
- 整个 provider 挂掉是另一个问题，到时候改 .env 切换即可
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Protocol

import httpx
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Tier(str, Enum):
    """Agent 重要性档位。业务代码用这个，不用具体模型名"""

    # 主角：求职者分身的大脑、关键反事实推理
    # 量小但质量要求最高
    PRIMARY = "primary"
    # 配角：公司 HR、面试官的对话
    # 量中等，质量要稳
    SECONDARY = "secondary"
    # 群演：竞争者分身、市场环境信号
    # 量大（200+ 并发），价格敏感
    BACKGROUND = "background"


class LLMResponse(BaseModel):
    """统一响应。屏蔽 provider 差异"""

    text: str
    provider: str  # 哪个 provider 产生的，便于追踪
    model: str  # 哪个具体模型
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    """LLM provider 协议。
    任何 provider（OpenAI 兼容 / Claude / 自托管）实现这个接口即可注册"""

    name: str

    async def chat(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse: ...

    async def close(self) -> None: ...


class OpenAICompatProvider:
    """OpenAI 兼容协议 provider。
    覆盖大陆主流模型：DeepSeek / Qwen（dashscope 兼容模式）/ Kimi /
    GLM / 阶跃 / 豆包 / 文心兼容版 ……

    所有这些 provider 的差异只有 base_url 和 api_key。
    协议层面完全一致，所以一个类够用"""

    def __init__(self, name: str, base_url: str, api_key: str) -> None:
        self.name = name
        # 去掉末尾斜杠，统一拼接
        self._base = base_url.rstrip("/")
        self._key = api_key
        # 共享 httpx client：1000 次并发时连接复用极大降低开销
        # 60s 超时：留余量给推理较慢的 R1 类模型
        self._http = httpx.AsyncClient(timeout=60.0)

    async def chat(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self._key}"}

        # 3 次重试 + 指数退避（1s/2s/4s）。
        # 1000 次并发跑 sim 时偶发 429/502 是常态，retry 必须有
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._http.post(
                    f"{self._base}/chat/completions",
                    json=body,
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return LLMResponse(
                    text=text,
                    provider=self.name,
                    model=model,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
                # 最后一次不要 sleep，直接抛
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(
            f"provider={self.name} model={model} 调用失败（3 次重试后）: {last_err}"
        )

    async def close(self) -> None:
        await self._http.aclose()


class LLMRouter:
    """Tier → (provider, model) 路由器。
    业务代码唯一面对的入口，不感知 provider 切换"""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        tier_routing: dict[Tier, tuple[str, str]],
    ) -> None:
        """
        Args:
            providers: provider_name → provider 实例
            tier_routing: Tier 枚举 → (provider_name, model_name)
        """
        self._providers = providers
        self._routing: dict[Tier, tuple[LLMProvider, str]] = {}
        for tier, (provider_name, model) in tier_routing.items():
            if provider_name not in providers:
                raise ValueError(
                    f"tier={tier.value} 引用了未注册的 provider={provider_name}。"
                    f"已注册: {list(providers.keys())}。"
                    f"检查 .env 的 LLM_PROVIDERS 是否包含 {provider_name}"
                )
            self._routing[tier] = (providers[provider_name], model)

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        tier: Tier = Tier.SECONDARY,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """业务代码唯一调用入口"""
        if tier not in self._routing:
            raise ValueError(
                f"tier={tier.value} 未配置路由。检查 .env 的 LLM_TIER_{tier.value.upper()}"
            )
        provider, model = self._routing[tier]
        return await provider.chat(
            system=system,
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def describe_routing(self) -> dict[str, str]:
        """启动时打印当前路由，方便确认"""
        return {
            tier.value: f"{provider.name}:{model}"
            for tier, (provider, model) in self._routing.items()
        }

    async def close(self) -> None:
        # 多 provider 可能共享或独立 http 连接池，每个都 close
        for p in self._providers.values():
            await p.close()


# ============ 工厂：从 settings 构建 router ============

# provider 注册表：provider 名 -> (base_url 字段, api_key 字段)
# 加新 provider 只改这一处。所有 provider 都假设 OpenAI 兼容协议。
# 非 OpenAI 协议（如 Claude）将来通过一个独立工厂分支添加，不在此表
_OPENAI_COMPAT_REGISTRY: dict[str, tuple[str, str]] = {
    "deepseek": ("deepseek_base_url", "deepseek_api_key"),
    "qwen": ("qwen_base_url", "qwen_api_key"),
    "kimi": ("kimi_base_url", "kimi_api_key"),
    "glm": ("glm_base_url", "glm_api_key"),
    "stepfun": ("stepfun_base_url", "stepfun_api_key"),
    "doubao": ("doubao_base_url", "doubao_api_key"),
}


def _parse_tier_spec(spec: str) -> tuple[str, str]:
    """解析 "provider:model" 字符串"""
    if ":" not in spec:
        raise ValueError(
            f"tier 路由格式错误: {spec!r}。应为 'provider_name:model_name'，"
            f"例如 'deepseek:deepseek-chat'"
        )
    provider, model = spec.split(":", 1)
    return provider.strip(), model.strip()


def build_router(settings: Settings) -> LLMRouter:
    """从 settings 构建 router 单例。
    在 FastAPI lifespan 启动时调用一次"""

    providers: dict[str, LLMProvider] = {}
    for name in settings.llm_providers:
        name = name.strip().lower()
        if name not in _OPENAI_COMPAT_REGISTRY:
            raise ValueError(
                f"未知 provider={name}。已支持: {list(_OPENAI_COMPAT_REGISTRY.keys())}。"
                f"如需加新 provider，在 _OPENAI_COMPAT_REGISTRY 加一行 + .env 加 KEY/URL"
            )
        url_field, key_field = _OPENAI_COMPAT_REGISTRY[name]
        base_url = getattr(settings, url_field, "")
        api_key = getattr(settings, key_field, "")
        if not api_key:
            # key 缺失：直接报错，不静默跳过，否则 sim 时才发现某档没 key 就晚了
            raise ValueError(
                f"provider={name} 已启用但 {key_field.upper()} 为空，"
                f"请在 .env 设置或从 LLM_PROVIDERS 移除"
            )
        providers[name] = OpenAICompatProvider(name, base_url, api_key)

    # 解析 tier 路由
    tier_routing: dict[Tier, tuple[str, str]] = {
        Tier.PRIMARY: _parse_tier_spec(settings.llm_tier_primary),
        Tier.SECONDARY: _parse_tier_spec(settings.llm_tier_secondary),
        Tier.BACKGROUND: _parse_tier_spec(settings.llm_tier_background),
    }

    return LLMRouter(providers, tier_routing)


# ============ 单例管理 ============

_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    """业务代码调用入口"""
    if _router is None:
        raise RuntimeError("LLM router 未初始化，请确认 FastAPI lifespan 已启动")
    return _router


def init_router() -> LLMRouter:
    """app 启动时调用"""
    global _router
    _router = build_router(get_settings())
    return _router


async def shutdown_router() -> None:
    """app 关闭时调用"""
    global _router
    if _router is not None:
        await _router.close()
        _router = None
