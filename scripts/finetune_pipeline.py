"""
端到端 LoRA 微调 pipeline CLI。

串联三步：
  1. data_gen   生成 SFT jsonl
  2. train      产出 adapter
  3. serve verify  实例化 FinetunedPersonaService 并发一条 chat，确认链路通

用法：
  # CPU 验证模式（无 GPU、无 LLM key 可用）
  python scripts/finetune_pipeline.py --user-id test --mock

  # 真训练（阿里云 GPU 实例）
  python scripts/finetune_pipeline.py \\
    --user-id user_primary \\
    --resume backend/data/raw/sample_resume.md \\
    --github https://github.com/user

退出码：
  0  全流程通过
  1  数据生成失败（样本数 < 200 或异常）
  2  训练失败
  3  serve verify 失败

失败兜底：见 backend/app/finetune/__init__.py 顶部 docstring。
即使训练失败，serve.py 也能用 RAG 模式跑通，pipeline 不强制非 0 退出
（除非 verify 也挂——那是真的不能用了）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 让 backend/ 进入 sys.path，使 app.* 能 import
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# 上面这行 sys.path 必须在 import app.* 之前。E402 故意忽略
from app.finetune.data_gen import (  # noqa: E402
    UserMaterial,
    generate_sft_dataset,
    generate_mock_sft_dataset,
)
from app.finetune.train import TrainConfig, train  # noqa: E402
from app.finetune.serve import FinetunedPersonaService  # noqa: E402
from app.services.llm import build_router  # noqa: E402
from app.core.config import get_settings  # noqa: E402

logger = logging.getLogger(__name__)


# ============================================================
# 路径约定
# ============================================================


def sft_path_for(user_id: str) -> Path:
    """SFT 数据落盘路径。用 user_id 命名以支持多用户并存"""
    return PROJECT_ROOT / "backend" / "data" / "finetune" / f"sft_{user_id}.jsonl"


def adapter_dir_for(user_id: str) -> Path:
    """adapter 输出目录。多一层 <user_id>/adapter/ 是为了未来可能并存
    多个 adapter 版本（adapter_v1, adapter_v2）"""
    return PROJECT_ROOT / "backend" / "data" / "finetuned" / user_id / "adapter"


# ============================================================
# Pipeline 主体
# ============================================================


async def run_pipeline(
    *,
    user_id: str,
    resume_path: str,
    github_url: str,
    blog_urls: list[str],
    target_roles: list[str],
    target_industries: list[str],
    target_cities: list[str],
    mock: bool,
    max_concurrency: int,
    batch_size: int,
    verify_prompt: str,
) -> int:
    """主流程。返回 exit code"""

    sft_jsonl = sft_path_for(user_id)
    adapter_dir = adapter_dir_for(user_id)
    sft_jsonl.parent.mkdir(parents=True, exist_ok=True)
    adapter_dir.mkdir(parents=True, exist_ok=True)

    # ====== 加载简历文本 ======
    resume_text = ""
    if resume_path:
        p = Path(resume_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if p.exists():
            resume_text = p.read_text(encoding="utf-8")
        else:
            logger.warning(f"简历文件不存在: {p}（继续，按空简历处理）")

    material = UserMaterial(
        user_id=user_id,
        resume_text=resume_text,
        github_url=github_url,
        blog_urls=blog_urls,
        target_roles=target_roles,
        target_industries=target_industries,
        target_cities=target_cities,
    )

    # ====== Step 1: 数据生成 ======
    print(f"[1/3] 生成 SFT 数据 -> {sft_jsonl}")
    try:
        if mock:
            n_samples = generate_mock_sft_dataset(material, sft_jsonl)
        else:
            settings = get_settings()
            router = build_router(settings)
            try:
                n_samples = await generate_sft_dataset(
                    router,
                    material,
                    out_path=sft_jsonl,
                    max_concurrency=max_concurrency,
                    batch_size=batch_size,
                )
            finally:
                await router.close()
    except Exception as e:
        logger.exception(f"数据生成阶段异常: {e}")
        return 1

    print(f"    生成 {n_samples} 条样本")
    if n_samples < 200:
        # 不达验收线。mock 模式默认就 220 条不会到这；真模式可能因为 LLM 频繁失败到这
        print(f"    [WARN] 样本数 < 200，未达验收线")
        if not mock:
            # 真模式下样本不够直接失败，避免训出一个低质量 adapter
            return 1

    # ====== Step 2: 训练 ======
    print(f"[2/3] 训练 LoRA adapter -> {adapter_dir}")
    train_cfg = TrainConfig(
        sft_jsonl_path=sft_jsonl,
        adapter_out_dir=adapter_dir,
    )
    try:
        meta = train(train_cfg, mock=mock)
    except Exception as e:
        logger.exception(f"训练阶段异常: {e}")
        # 写一个 failed marker，让 serve 自动走 rag_fallback
        (adapter_dir / "adapter_meta.json").write_text(
            json.dumps(
                {
                    "user_id": user_id,
                    "status": "failed",
                    "mock": mock,
                    "error": str(e)[:500],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("    [WARN] 训练失败，已写 failed marker，serve 会降级到 RAG 模式")
        # 不直接 return——继续走 verify，看 RAG 兜底能不能跑通
        meta = {"status": "failed"}

    print(f"    训练完成: status={meta.get('status')} mock={meta.get('mock')}")

    # ====== Step 3: Serve verify ======
    print(f"[3/3] 验证 serve 链路（mock={mock}）")
    try:
        service = FinetunedPersonaService(
            adapter_dir,
            user_material={
                "user_id": user_id,
                "resume_text": resume_text[:500],
                "target_roles": target_roles,
                "target_industries": target_industries,
                "target_cities": target_cities,
            },
            mock=mock,
            seed=42,
        )
        print(f"    service mode = {service.info.mode}; reason={service.info.reason or '-'}")
        reply = await service.chat(
            verify_prompt,
            system="你是用户的求职分身。用一句话回答。",
            max_tokens=128,
            temperature=0.7,
        )
        # 限制输出长度，避免 CI 打满日志
        snippet = reply.strip().replace("\n", " ")[:200]
        print(f"    chat reply (前 200 字): {snippet}")
        if not snippet:
            print("    [FAIL] chat 返回空字符串")
            return 3
    except Exception as e:
        logger.exception(f"serve verify 失败: {e}")
        return 3
    finally:
        # 释放资源（mock/RAG 模式 no-op）
        try:
            await service.close()  # type: ignore[possibly-unbound]
        except Exception:
            pass

    print("[done] pipeline 全流程通过")
    return 0


# ============================================================
# CLI
# ============================================================


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoRA 微调端到端 pipeline")
    p.add_argument("--user-id", required=True)
    p.add_argument(
        "--resume",
        default="",
        help="简历文本文件（已转 markdown / 纯文本）。可为空",
    )
    p.add_argument("--github", default="", help="用户 GitHub 主页 URL")
    p.add_argument(
        "--blog",
        action="append",
        default=[],
        help="blog URL（可多次指定）",
    )
    p.add_argument(
        "--target-role",
        action="append",
        default=[],
        help="目标岗位（可多次指定）",
    )
    p.add_argument(
        "--target-industry",
        action="append",
        default=[],
    )
    p.add_argument(
        "--target-city",
        action="append",
        default=[],
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="CPU 验证模式：mock 数据生成 + mock 训练 + mock 推理",
    )
    p.add_argument("--max-concurrency", type=int, default=4)
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument(
        "--verify-prompt",
        default="本周拿到一个 28k 的 offer，公司 996，你接吗？",
        help="serve verify 时发的测试 prompt",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    args = parse_args(argv if argv is not None else sys.argv[1:])
    code = asyncio.run(
        run_pipeline(
            user_id=args.user_id,
            resume_path=args.resume,
            github_url=args.github,
            blog_urls=args.blog,
            target_roles=args.target_role,
            target_industries=args.target_industry,
            target_cities=args.target_city,
            mock=args.mock,
            max_concurrency=args.max_concurrency,
            batch_size=args.batch_size,
            verify_prompt=args.verify_prompt,
        )
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
