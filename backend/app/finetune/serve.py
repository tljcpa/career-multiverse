"""
微调后分身的推理服务。

对外只暴露一个类 FinetunedPersonaService，方法：
  async def chat(prompt: str, *, system: str = "", max_tokens: int = 1024,
                 temperature: float = 0.7) -> str

这个签名与 LLMRouter.generate 的"业务视角"对齐——
都是"给我一段输出"，simulation 引擎可以"无感切换"到使用用户分身做决策。

为什么不直接复用 LLMRouter：
  LLMRouter 是"外部 OpenAI 兼容 provider"的封装；分身推理走的是
  本地加载的 transformers 模型，没有 HTTP API、tier、多模型路由的概念。
  让分身实现 LLMRouter.generate 的 *形态* 就够了——结构上是 duck typing。
  上游 simulation 引擎拿到 service 后包一层 adapter 调用即可。

三条推理路径（运行时自动选择，从优先到兜底）：

  1. real     有 GPU + 真 adapter（adapter_meta.json["mock"] == False，
              且 status == "ok"）
              → transformers + PEFT 加载 base + adapter，做真实推理

  2. mock     CPU 验证环境，或 adapter 是 train_mock 写的占位文件
              （adapter_meta.json["mock"] == True）
              → 不加载任何模型，返回固定 stub 字符串
              纯验证调用链路是否通顺

  3. rag_fallback 训练失败（status="failed"）或 adapter 文件缺失
              → 不用 adapter，把用户原始材料注入 system prompt，
              让 base 模型用 RAG 风格扮演用户
              （这一路径需要能加载 base 模型；CPU 环境也会走 mock）

关于 base 模型 vs 推理小模型：
  CPU 验证时不应该加载 7B base 模型——OOM 或慢到不可用。
  mock 路径设计的初衷就是"不加载任何模型"。
  如果在 CPU 上确实想试试推理（debugging serving 层），
  可以让 mock 路径下用 Qwen2.5-0.5B-Instruct，但实际项目里不需要——
  ChatA() stub 返回值已经能覆盖 simulation 引擎的 happy path。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# 服务元信息
# ============================================================


@dataclass
class ServiceInfo:
    """诊断用。simulation 启动时可打印，知道当前用的是真分身还是 stub"""

    user_id: str
    mode: str  # "real" / "mock" / "rag_fallback" / "uninitialized"
    base_model: str = ""
    adapter_dir: str = ""
    samples_used: int = 0
    reason: str = ""  # 走 fallback 的原因


# ============================================================
# 服务主体
# ============================================================


# Mock 模式下的 stub 回答池。
# 为什么有 4 种：让上游 sim 调用拿到不同 prompt 时不至于看到完全相同输出，
# 便于人肉验证 prompt → output 链路是否走通了（不是只回一句）。
MOCK_RESPONSES = [
    "我倾向接受这个机会，理由：方向匹配我的长板，城市也在期望范围内。",
    "我会拒绝这家。薪资低于期望且加班文化太重，性价比不合算。",
    "我想 negotiate base 上调 4k，附带远程办公 2 天/周。理由是我手上还有同档位 offer。",
    "本周计划再投 2-3 家中厂稳一稳保底，不急着决定。",
]


class FinetunedPersonaService:
    """用户分身推理服务"""

    def __init__(
        self,
        adapter_dir: str | Path,
        *,
        user_material: dict[str, Any] | None = None,
        mock: bool = False,
        seed: int | None = None,
    ) -> None:
        """
        Args:
            adapter_dir: adapter 目录路径（train.train() 输出的目录）
            user_material: 用户原始材料 dict，用于 rag_fallback 路径注入 system prompt。
                          dict 是为了不强耦合 UserMaterial dataclass，前端任意送
            mock: 强制走 mock 路径（即使 adapter 是真训出来的）。
                  用于 CPU 调试。--mock CLI 透传这一标志
            seed: stub 回答的随机种子，便于测试可复现
        """
        self._adapter_dir = Path(adapter_dir)
        self._user_material = user_material or {}
        self._force_mock = mock
        self._rng = random.Random(seed)

        # 决定运行模式
        self._info = self._resolve_mode()

        # 真模型实例：延迟加载（首次 chat 才 load，避免 import 期间崩）
        self._model = None  # 真模型 / PEFT model
        self._tokenizer = None
        # 异步锁，确保首次 load 不被并发触发两次
        self._load_lock = asyncio.Lock()

    # ----- mode 决议 -----

    def _resolve_mode(self) -> ServiceInfo:
        """根据 adapter_meta.json + force_mock 标志决定走哪条路径"""
        user_id = self._adapter_dir.parent.name if self._adapter_dir.parent.name else "unknown"

        # 强制 mock：直接返回，不读 meta
        if self._force_mock:
            return ServiceInfo(
                user_id=user_id,
                mode="mock",
                adapter_dir=str(self._adapter_dir),
                reason="force_mock flag enabled",
            )

        # 读 meta
        meta_path = self._adapter_dir / "adapter_meta.json"
        if not meta_path.exists():
            # 没训练过 / adapter 目录不存在 → 走 RAG 兜底
            return ServiceInfo(
                user_id=user_id,
                mode="rag_fallback",
                adapter_dir=str(self._adapter_dir),
                reason="adapter_meta.json 不存在",
            )

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            return ServiceInfo(
                user_id=user_id,
                mode="rag_fallback",
                adapter_dir=str(self._adapter_dir),
                reason=f"adapter_meta.json 解析失败: {e}",
            )

        status = meta.get("status", "unknown")
        if status == "failed":
            return ServiceInfo(
                user_id=user_id,
                mode="rag_fallback",
                adapter_dir=str(self._adapter_dir),
                base_model=meta.get("base_model", ""),
                reason="meta.status == failed（训练失败兜底）",
            )

        if meta.get("mock"):
            return ServiceInfo(
                user_id=user_id,
                mode="mock",
                adapter_dir=str(self._adapter_dir),
                base_model=meta.get("base_model", ""),
                samples_used=meta.get("samples_used", 0),
                reason="adapter 是 train_mock 写的占位",
            )

        return ServiceInfo(
            user_id=user_id,
            mode="real",
            adapter_dir=str(self._adapter_dir),
            base_model=meta.get("base_model", ""),
            samples_used=meta.get("samples_used", 0),
        )

    # ----- 对外接口 -----

    @property
    def info(self) -> ServiceInfo:
        return self._info

    async def chat(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """统一推理接口。返回纯文本（不带 LLMResponse 包装）"""
        mode = self._info.mode
        if mode == "mock":
            return await self._chat_mock(prompt, system=system)
        if mode == "rag_fallback":
            return await self._chat_rag_fallback(
                prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            )
        if mode == "real":
            return await self._chat_real(
                prompt, system=system, max_tokens=max_tokens, temperature=temperature,
            )
        # 理论上不会到这
        raise RuntimeError(f"未识别的 service mode: {mode}")

    # ----- mock 实现 -----

    async def _chat_mock(self, prompt: str, *, system: str) -> str:
        """完全离线、零依赖。
        实现策略：根据 prompt 内容选最贴近的 stub，否则随机一条。"""
        # 极简启发式：从 prompt 关键词分辨决策类别
        text = (system + "\n" + prompt).lower()
        if "offer" in text and ("accept" in text or "decline" in text or "拿到" in text):
            return MOCK_RESPONSES[0] if "高" in text else MOCK_RESPONSES[1]
        if "negotiate" in text or "谈" in text or "加薪" in text:
            return MOCK_RESPONSES[2]
        # 默认随机一条，让不同 prompt 至少有不同输出
        return self._rng.choice(MOCK_RESPONSES)

    # ----- rag_fallback 实现 -----

    async def _chat_rag_fallback(
        self,
        prompt: str,
        *,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """训练失败兜底：用 LLMRouter 调外部 LLM，把用户材料注入 system prompt。

        这一路径"借用" simulation 已初始化的 LLMRouter——
        FastAPI lifespan 会在启动时 init_router()，这里直接 get_router()。
        如果是脱离 FastAPI 的离线脚本调用，get_router 会抛错；
        此时上游可以选择直接构造一个临时 router 或转 mock。

        本路径不会出现在"happy path"——只有训练失败时才走，
        所以容许它对外部依赖更强。"""

        # 延迟 import，避免循环依赖（finetune ← services.llm ← config）
        try:
            from app.services.llm import get_router, Tier
            router = get_router()
        except Exception as e:
            # router 没初始化，最后兜底：返回降级提示
            logger.warning(f"rag_fallback 无法获取 LLMRouter，降级到固定回答: {e}")
            return "[rag_fallback no_router] 我倾向再观察一下，本周不做决定。"

        # 构造一段"用户口吻"的 system prompt
        material_brief = json.dumps(self._user_material, ensure_ascii=False)[:2000]
        rag_system = (
            (system or "")
            + "\n\n你现在扮演以下用户。仔细阅读用户材料，用第一人称回答问题。"
            + "保持用户的价值观与目标，不要编造与材料冲突的事实。\n\n"
            + "[用户材料]\n"
            + material_brief
        )

        resp = await router.generate(
            prompt,
            system=rag_system,
            tier=Tier.PRIMARY,  # 兜底走主用户档，保证质量
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.text

    # ----- real 实现 -----

    async def _chat_real(
        self,
        prompt: str,
        *,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """真模型推理。需要在 GPU 实例上首次调用时加载模型。
        加载耗时 30-90s（取决于网络/磁盘），所以做了惰性加载 + 异步锁"""

        # 双重检测惰性加载
        if self._model is None:
            async with self._load_lock:
                if self._model is None:
                    await self._lazy_load_model()

        # transformers 推理是同步的，用 to_thread 放后台不阻塞 event loop
        return await asyncio.to_thread(
            self._run_generate_sync,
            prompt, system, max_tokens, temperature,
        )

    async def _lazy_load_model(self) -> None:
        """惰性加载 base + adapter。
        失败时切换 mode 到 rag_fallback，不抛错"""
        try:
            # 延迟 import
            from transformers import AutoTokenizer, AutoModelForCausalLM
            from peft import PeftModel
            import torch

            base = self._info.base_model or "Qwen/Qwen2.5-7B-Instruct"
            logger.info(f"加载 base 模型: {base}")
            tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                base,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )
            logger.info(f"加载 adapter: {self._adapter_dir}")
            model = PeftModel.from_pretrained(model, str(self._adapter_dir))
            model.eval()
            self._model = model
            self._tokenizer = tokenizer
            logger.info("real 模式模型加载完成")
        except Exception as e:
            logger.warning(f"real 模式加载失败，切换到 rag_fallback: {e}")
            # 即时切换 mode，避免反复尝试加载
            self._info = ServiceInfo(
                user_id=self._info.user_id,
                mode="rag_fallback",
                adapter_dir=self._info.adapter_dir,
                base_model=self._info.base_model,
                reason=f"real 模式 lazy_load 失败: {e}",
            )

    def _run_generate_sync(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """同步推理。在 to_thread 里被调用。
        和训练时的 prompt 模板对齐，提升 in-distribution 一致性"""

        # 真模型推理需要 transformers 已成功 import（lazy_load 通过了）
        # 失败的话调用方早就被切到 rag_fallback 路径，不会到这里
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("模型未加载（应当不会到达：lazy_load 失败已切换路径）")

        # 用 chat template 拼接，避免手写 <|im_start|> 出错
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        else:
            messages.append({"role": "system", "content": "你是一个 AI 求职分身。"})
        messages.append({"role": "user", "content": prompt})

        tokenizer = self._tokenizer
        model = self._model

        # apply_chat_template + tokenizer 是 Qwen2.5 推理的标准方式
        prompt_str = tokenizer.apply_chat_template(  # type: ignore[union-attr]
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = tokenizer(prompt_str, return_tensors="pt").to(model.device)  # type: ignore[union-attr]

        # generate 参数：do_sample 跟随 temperature
        do_sample = temperature > 0
        outputs = model.generate(  # type: ignore[union-attr]
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=do_sample,
            temperature=temperature if do_sample else 1.0,
            top_p=0.9 if do_sample else 1.0,
            pad_token_id=tokenizer.eos_token_id,  # type: ignore[union-attr]
        )

        # 去掉 prompt 部分，只保留新生成的 tokens
        new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True)  # type: ignore[union-attr]
        return text.strip()

    async def close(self) -> None:
        """释放资源。simulation 结束时调用。
        mock / rag_fallback 路径无需释放；real 路径 del 模型"""
        if self._model is not None:
            del self._model
            self._model = None
        self._tokenizer = None
