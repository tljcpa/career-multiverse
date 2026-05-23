"""
LoRA 微调训练脚本。

真实路径（阿里云 PAI-DSW，有 GPU）：
  Unsloth + Qwen2.5-7B-Instruct + LoRA + 4bit 量化 + 2e-4 lr。
  在 A10 24G 上单卡可跑，约 30-45 分钟收敛（数据 200-500 对、3 epoch）。

Mock 路径（CPU、本机 dev、CI verify）：
  --mock 标志启用，不加载任何 GPU 框架。
  只做：
    1. 读 jsonl，验证至少 200 条样本（验收线之一）
    2. 在 adapter 目录写假 adapter_config.json + adapter_meta.json
    3. 写"训练日志"占位文件
  serve.py 看到 adapter_meta.json["mock"]==True 时走纯 stub 推理路径。

为什么把 Unsloth 等重依赖延迟到函数内导入：
  本机 CPU 上不应该装 torch/unsloth/peft/accelerate（占空间巨大）。
  --mock 路径下整个 import chain 不会触发这些 import，因此本机也能 import train。
  真训练时（GPU 实例）才 import 它们，import error 直接报缺包，给出装包提示。

兜底约定：
  真训练失败（OOM / NaN / 数据格式错）会抛 RuntimeError。
  上游 finetune_pipeline.py 捕获后写 marker 文件 adapter_meta.json["status"]="failed"，
  让 serve.py 自动降级到 RAG 风格推理。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================


@dataclass
class TrainConfig:
    """训练超参。默认值是经验上 7B + 200-500 对 SFT 数据的稳态配置"""

    # 数据
    sft_jsonl_path: Path
    adapter_out_dir: Path

    # 基座模型
    # Unsloth 仓库的 4bit 预量化版本，下载快 + 显存省。
    # 选择理由备忘：
    #   Qwen2.5-7B-Instruct: 中文好、Apache 2.0、能听懂"以 X 口吻"指令、
    #                        Unsloth 一档支持、A10 单卡能训
    base_model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"

    # LoRA
    # r=16 是 7B + 几百条 SFT 数据的甜区。再大基本无收益且更易 overfit。
    lora_r: int = 16
    lora_alpha: int = 16
    lora_dropout: float = 0.0  # Unsloth fast path 要求 dropout=0

    # 训练
    learning_rate: float = 2e-4   # Unsloth/LoRA 经验值
    num_epochs: int = 3           # 200-500 样本 3 epoch 足够拟合"用户口吻"
    batch_size: int = 2           # A10 24G 实测安全值
    grad_accum: int = 4           # effective batch = 8
    max_seq_length: int = 2048    # SFT 数据单条 < 1k token，2048 充分覆盖
    warmup_steps: int = 5
    weight_decay: float = 0.01
    seed: int = 3407              # Unsloth 推荐种子


# ============================================================
# Mock 路径（CPU 本机 / CI verify）
# ============================================================


def train_mock(cfg: TrainConfig) -> dict:
    """完全离线的"训练"——只写 adapter 元信息，不加载任何模型。
    返回的字典写入 adapter_meta.json，供 serve.py 识别"""

    # 1. 校验输入 jsonl 存在且 >= 200 条（验收线）
    if not cfg.sft_jsonl_path.exists():
        raise FileNotFoundError(f"SFT 数据不存在: {cfg.sft_jsonl_path}")
    line_count = 0
    with cfg.sft_jsonl_path.open("r", encoding="utf-8") as f:
        for _ in f:
            line_count += 1
    if line_count < 200:
        # 这里给 warn 不抛，便于 verify 路径继续跑；上游 verify 单独 check 数量
        logger.warning(
            f"SFT 样本数 {line_count} < 200，未达验收线。"
            "mock 模式继续，但请检查 data_gen 是否正常"
        )

    # 2. 准备输出目录
    cfg.adapter_out_dir.mkdir(parents=True, exist_ok=True)

    # 3. 写一个最小化的 fake adapter_config.json（PEFT 标准结构）
    #    serve.py 在 mock 模式下不会真加载，但留这个文件方便人肉 ls 看
    fake_adapter_config = {
        "peft_type": "LORA",
        "base_model_name_or_path": cfg.base_model,
        "r": cfg.lora_r,
        "lora_alpha": cfg.lora_alpha,
        "lora_dropout": cfg.lora_dropout,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "task_type": "CAUSAL_LM",
        # 标记这是 mock 占位，避免被误用真加载
        "_mock_placeholder": True,
    }
    (cfg.adapter_out_dir / "adapter_config.json").write_text(
        json.dumps(fake_adapter_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4. 写一个体积忽略的 dummy weights 文件，让 LS 看起来像 adapter 目录
    #    真训练时这个文件由 PEFT save_pretrained 写。
    #    内容是 byte stream 占位，不可被 torch.load
    (cfg.adapter_out_dir / "adapter_model.safetensors").write_bytes(
        b"MOCK_ADAPTER_PLACEHOLDER_DO_NOT_LOAD"
    )

    # 5. 写关键元信息（serve.py 读这个判断走哪条推理路径）
    meta = {
        "user_id": cfg.adapter_out_dir.parent.name,
        "base_model": cfg.base_model,
        "status": "ok",
        "mock": True,
        "samples_used": line_count,
        "trained_at": int(time.time()),
        "config": {
            "lora_r": cfg.lora_r,
            "lora_alpha": cfg.lora_alpha,
            "learning_rate": cfg.learning_rate,
            "num_epochs": cfg.num_epochs,
            "batch_size": cfg.batch_size,
            "grad_accum": cfg.grad_accum,
        },
    }
    (cfg.adapter_out_dir / "adapter_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[mock train] 已写入占位 adapter -> {cfg.adapter_out_dir}")
    return meta


# ============================================================
# 真训练路径（GPU 实例）
# ============================================================


def train_real(cfg: TrainConfig) -> dict:
    """真训练。仅在有 GPU 的实例上执行。

    为什么把 import 放函数内：见模块 docstring。
    为什么不写 try/except 包住整个训练：让上游 finetune_pipeline.py 统一捕获
                                  并写 status=failed，单一兜底入口"""

    # 延迟导入，本机 dev 不需要装这些
    try:
        import torch  # noqa: F401
        from unsloth import FastLanguageModel  # noqa: F401
        from datasets import load_dataset  # noqa: F401
        from trl import SFTTrainer  # noqa: F401
        from transformers import TrainingArguments  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"训练依赖缺失: {e}。需要在 GPU 实例上安装: "
            "torch unsloth peft accelerate transformers trl datasets bitsandbytes。"
            "或者加 --mock 走 CPU 验证路径"
        ) from e

    # === 加载 base + 套 LoRA ===
    model, tokenizer = FastLanguageModel.from_pretrained(  # type: ignore[name-defined]
        model_name=cfg.base_model,
        max_seq_length=cfg.max_seq_length,
        load_in_4bit=True,
        dtype=None,  # Unsloth 自适应（A10/A100 用 bfloat16）
    )
    model = FastLanguageModel.get_peft_model(  # type: ignore[name-defined]
        model,
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        # Qwen 系列标准 4 个投影模块。Unsloth 文档同名
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",  # 显存大幅节省
        random_state=cfg.seed,
    )

    # === 数据 ===
    # SFT jsonl 每行三字段 instruction/input/output（外加 meta 字段被忽略）。
    # Unsloth/TRL 的 SFTTrainer 习惯用单个 "text" 字段，自己拼好。
    raw = load_dataset(  # type: ignore[name-defined]
        "json",
        data_files=str(cfg.sft_jsonl_path),
        split="train",
    )

    PROMPT_TPL = (
        "<|im_start|>system\n你是一个 AI 求职分身。<|im_end|>\n"
        "<|im_start|>user\n{instruction}\n\n{input}<|im_end|>\n"
        "<|im_start|>assistant\n{output}<|im_end|>"
    )

    def fmt(example: dict) -> dict:
        text = PROMPT_TPL.format(
            instruction=example.get("instruction", ""),
            input=example.get("input", ""),
            output=example.get("output", ""),
        )
        return {"text": text}

    dataset = raw.map(fmt, remove_columns=raw.column_names)

    # === 训练器 ===
    args = TrainingArguments(  # type: ignore[name-defined]
        per_device_train_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        warmup_steps=cfg.warmup_steps,
        num_train_epochs=cfg.num_epochs,
        learning_rate=cfg.learning_rate,
        fp16=False,
        bf16=True,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=cfg.weight_decay,
        lr_scheduler_type="linear",
        seed=cfg.seed,
        output_dir=str(cfg.adapter_out_dir / "training_logs"),
        save_strategy="no",  # 只在最后手动保存 adapter，避免中间 checkpoint 占盘
        report_to="none",
    )
    trainer = SFTTrainer(  # type: ignore[name-defined]
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=cfg.max_seq_length,
        packing=False,  # SFT 数据条数不多，packing 收益小，关掉避免边界 bug
        args=args,
    )
    trainer.train()

    # === 保存 adapter ===
    cfg.adapter_out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(cfg.adapter_out_dir))
    tokenizer.save_pretrained(str(cfg.adapter_out_dir))

    # 写元信息
    sample_count = 0
    with cfg.sft_jsonl_path.open("r", encoding="utf-8") as f:
        for _ in f:
            sample_count += 1
    meta = {
        "user_id": cfg.adapter_out_dir.parent.name,
        "base_model": cfg.base_model,
        "status": "ok",
        "mock": False,
        "samples_used": sample_count,
        "trained_at": int(time.time()),
        "config": {
            "lora_r": cfg.lora_r,
            "lora_alpha": cfg.lora_alpha,
            "learning_rate": cfg.learning_rate,
            "num_epochs": cfg.num_epochs,
            "batch_size": cfg.batch_size,
            "grad_accum": cfg.grad_accum,
        },
    }
    (cfg.adapter_out_dir / "adapter_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[real train] adapter 已落盘 -> {cfg.adapter_out_dir}")
    return meta


# ============================================================
# 统一入口
# ============================================================


def train(cfg: TrainConfig, *, mock: bool) -> dict:
    """对外统一入口。mock=True 走 CPU 占位，否则真训练"""
    if mock:
        return train_mock(cfg)
    return train_real(cfg)


# ============================================================
# CLI
# ============================================================


def _main_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="LoRA 微调单用户分身")
    parser.add_argument("--sft", required=True, help="SFT 数据 jsonl 路径")
    parser.add_argument("--out", required=True, help="adapter 输出目录")
    parser.add_argument("--mock", action="store_true", help="CPU 占位模式")
    parser.add_argument(
        "--base-model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    args = parser.parse_args(argv)

    cfg = TrainConfig(
        sft_jsonl_path=Path(args.sft),
        adapter_out_dir=Path(args.out),
        base_model=args.base_model,
        num_epochs=args.epochs,
        learning_rate=args.lr,
    )

    meta = train(cfg, mock=args.mock)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _main_cli(sys.argv[1:])
