"""
竞争者 persona 批量生成器（LLM 驱动，零手写）。

设计原则（同 collect_companies.py）：
1. 不硬编码任何具体人物，全部 LLM 按参数化分布生成
2. 字段严格对齐答疑文档 Q2 推荐的"简历 CV 格式"14 字段
3. 隐性信号（学校 tier 量化、项目含金量等）也由 LLM 推断后输出
4. 批量并发 + Pydantic 校验

输出：200 个 CandidateProfile（is_primary=False），用作沙盘里的竞争者池
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.models.candidate import CandidateProfile  # noqa: E402
from app.services.llm import Tier, build_router  # noqa: E402

# ============================================================
# 生成参数（按分布配比）
# ============================================================

# 学校档次分布。覆盖中国校招真实生态
SCHOOL_TIER_PLAN: list[tuple[str, int]] = [
    ("清北复交（top）", 8),
    ("C9/985 头部（985_top）", 20),
    ("普通 985（985）", 35),
    ("211（211）", 50),
    ("双非一本（double_non）", 50),
    ("二本及以下（lower）", 25),
    ("海外 QS 100 内（overseas_top）", 8),
    ("海外其他（overseas_other）", 4),
]
# 合计 200

# 学历 + 专业方向（每个 tier 内 LLM 自由分配）
MAJOR_HINTS = [
    "计算机/软件/AI",
    "电子信息/通信",
    "数学/统计/物理",
    "金融/经济/商科",
    "机械/自动化",
    "化学/生物/材料",
    "文科/管理类",
]


SYSTEM_PROMPT = """你是一个虚构数据生成器，为"AI 校招沙盘模拟"生成代表性的虚构求职者画像。

绝对规则：
1. 全部 synthetic 数据。姓名用化名（"张同学" "李同学" 等带"同学"后缀避免和真人重名）
2. 字段严格对齐答疑文档官方推荐的"简历 CV 格式"14 字段
3. 输出严格的 JSON 数组，不要 markdown 代码块，不要 ``` 包裹，不要解释文字
4. JSON 必须能被 Pydantic 直接解析为 CandidateProfile

输出规范：根 JSON 是数组，每项一个候选人，结构如下：

{
  "candidate_id": "compete_XXX 形式，XXX 是 3 位数",
  "is_primary": false,
  "official_cv": {
    "resume_quality": 0-100 整数,
    "name": "化名，'张同学' 'Li同学' 等",
    "gender": "男 / 女 / 未知 三选一",
    "job_status": "求职状态，如 '在校待找工作' '应届考虑机会'",
    "age": 20-28 整数,
    "work_years": "如 '应届' '应届+1段实习' '应届+多段实习'",
    "highest_degree": "本科 / 硕士 / 博士",
    "current_address": "城市，如 '北京' '上海'",
    "job_expectation": {
      "target_industries": ["1-3 个目标行业"],
      "target_roles": ["1-3 个目标岗位"],
      "target_cities": ["1-3 个目标城市"],
      "min_salary": "薪资期望文本，如 '15k·14薪'"
    },
    "work_internship_history": [
      {
        "company": "实习/工作公司（用代号或泛指如 '某中厂' '一家创业公司'）",
        "role": "实习岗位",
        "period": "如 '2024.06 - 2024.09'",
        "description": "简短描述"
      }
    ],
    "project_history": [
      {
        "name": "项目名",
        "role": "你的角色",
        "period": "时间",
        "description": "项目描述"
      }
    ],
    "education_history": [
      {
        "school": "学校（按 tier 选合理的，避免直接写真大学全名，写 '某 985'/'C9 院校' 等抽象表达，或写真校名但加 '(化名)'）",
        "degree": "本科 / 硕士 / 博士",
        "major": "专业",
        "period": "如 '2022.09 - 2026.06'"
      }
    ],
    "personal_strengths": "个人优势 50-100 字自我评价",
    "certificates": ["证书列表，可空"]
  },
  "hidden_signals": {
    "school_tier": "枚举: top/985_top/985/211/double_non/lower/overseas_top/overseas_other",
    "gpa_percentile": 0-100,
    "project_strength": 0-100,
    "internship_strength": 0-100,
    "achievements_strength": 0-100,
    "communication_score": 0-100,
    "stress_tolerance": 0-100,
    "overwork_tolerance": 0-100
  }
}

注意：
- hidden_signals.school_tier 必须和 official_cv.education_history 一致
- resume_quality 是综合质量评分（应届生绝大多数在 30-80 范围，<20 或 >90 都极少）
- 强项目+强实习+顶尖学校的候选人 resume_quality 偏高
- 项目和实习经历的"含金量"可以差异很大，故意造一些"学校好但项目水"或"学校一般但项目硬"的多样性
"""


def build_user_prompt(tier_label: str, count: int, start_id: int) -> str:
    return f"""请生成 {count} 个 "{tier_label}" 档次的虚构应届生求职者画像。

要求：
- candidate_id 从 compete_{start_id:03d} 开始连续编号
- 专业分布在以下范围里多样化分布: {MAJOR_HINTS}
- 学校 tier 整体匹配 "{tier_label}"，但内部允许 GPA / 项目含金量 / 软性特征的差异
- 性别比例约 1:1
- 城市分布合理（不要 200 个都在北京）

输出：严格 JSON 数组（长度 = {count}），无 markdown 包裹。"""


# ============================================================
# 生成核心
# ============================================================


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


# 真校名/真公司名 → 泛指代号。persona 里的"学校"和"实习公司"字段最容易漏
_REAL_NAME_REPLACEMENTS: dict[str, str] = {
    "字节跳动": "某头部短视频平台",
    "字节": "某头部短视频平台",
    "腾讯": "某 TOP 综合互联网厂",
    "阿里巴巴": "某 TOP 综合互联网厂",
    "阿里": "某 TOP 综合互联网厂",
    "美团": "某本地生活巨头",
    "百度": "某老牌搜索引擎厂",
    "京东": "某综合电商平台",
    "网易": "某老牌游戏+互联网厂",
    "滴滴": "某出行巨头",
    "小米": "某消费电子+IoT 厂",
    "快手": "某短视频平台",
    "拼多多": "某下沉电商平台",
    "华为": "某通信设备巨头",
    "中兴": "某通信设备厂",
    # 学校 → 泛指
    "清华大学": "某 C9 院校",
    "清华": "某 C9 院校",
    "北京大学": "某 C9 院校",
    "北大": "某 C9 院校",
    "复旦大学": "某 C9 院校",
    "复旦": "某 C9 院校",
    "上海交通大学": "某 C9 院校",
    "交大": "某 C9 院校",
    "浙江大学": "某 C9 院校",
    "浙大": "某 C9 院校",
    "南京大学": "某 C9 院校",
    "中国科学技术大学": "某 C9 院校",
    "中科大": "某 C9 院校",
    "西安交通大学": "某 C9 院校",
    "哈尔滨工业大学": "某 C9 院校",
    "哈工大": "某 C9 院校",
    "南京大学": "某 C9 院校",
    "南大": "某 C9 院校",
    # 新能源 / 制造（persona 里实习经历可能挂这些）
    "宁德时代": "某动力电池巨头",
    "宁德": "某动力电池巨头",
    "蔚来": "某新势力车企",
    "理想": "某新势力车企",
    "小鹏": "某新势力车企",
    "比亚迪": "某头部新能源车企",
}


def _sanitize(payload: list[dict]) -> tuple[list[dict], list[str]]:
    triggers: list[str] = []

    def walk(node: object, path: str) -> object:
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}") for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str):
            new = node
            for real, alias in _REAL_NAME_REPLACEMENTS.items():
                if real in new:
                    new = new.replace(real, alias)
                    triggers.append(f"{path}: '{real}'")
            return new
        return node

    return walk(payload, "$"), triggers


async def generate_personas_for_tier(
    router: Any, tier_label: str, count: int, start_id: int
) -> list[CandidateProfile]:
    prompt = build_user_prompt(tier_label, count, start_id)
    resp = await router.generate(
        prompt,
        system=SYSTEM_PROMPT,
        # 用 BACKGROUND 档（最便宜）—— persona 是群演，量大但单条不需要最强模型
        tier=Tier.BACKGROUND,
        max_tokens=8192,
        temperature=0.9,
    )

    try:
        data = json.loads(_strip_code_fences(resp.text))
    except json.JSONDecodeError as e:
        print(f"  [WARN] {tier_label}: JSON 解析失败 ({e})")
        return []

    if not isinstance(data, list):
        print(f"  [WARN] {tier_label}: LLM 返回不是数组")
        return []

    valid: list[CandidateProfile] = []
    for i, item in enumerate(data):
        try:
            valid.append(CandidateProfile.model_validate(item))
        except Exception as e:
            short_err = str(e).splitlines()[0][:120]
            print(f"  [WARN] {tier_label}#{i}: 校验失败 ({short_err})")
    print(
        f"  {tier_label}: 请求 {count}, LLM 返回 {len(data)}, 通过 {len(valid)}"
    )
    return valid


async def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "backend" / "data" / "personas" / "competitors_v1.json"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="单次 LLM 调用生成的 persona 数量。太大会超 8K token，太小并发开销大",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        help="SCHOOL_TIER_PLAN 各档人数的整数倍数。默认 1（=200 人），10 -> ~2000 人",
    )
    parser.add_argument(
        "--limit-batches",
        type=int,
        default=0,
        help="仅跑前 N 个 batch（小批验证用），0 表示全跑",
    )
    parser.add_argument(
        "--gen-provider",
        default="",
        help="覆盖 BACKGROUND 档 provider:model（如 deepseek:deepseek-chat）。留空用 .env 默认。",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        print("=== SYSTEM PROMPT (前 1500 字) ===")
        print(SYSTEM_PROMPT[:1500])
        print("...")
        print()
        print("=== 示例 USER PROMPT (清北复交 5 个) ===")
        print(build_user_prompt("清北复交（top）", 5, 1))
        return

    settings = get_settings()
    router = build_router(settings)

    # 可选：把 persona 生成的 BACKGROUND 档重路由到别的 provider（不改 .env）
    if args.gen_provider:
        prov_name, _, model = args.gen_provider.partition(":")
        if prov_name not in router._providers:
            raise SystemExit(
                f"--gen-provider 引用了未注册 provider={prov_name}，"
                f"已注册: {list(router._providers.keys())}"
            )
        router._routing[Tier.BACKGROUND] = (router._providers[prov_name], model)
        print(f"[override] BACKGROUND 档重路由到 {prov_name}:{model}")

    print("=== LLM 路由 ===")
    for t, target in router.describe_routing().items():
        print(f"  {t:11} -> {target}")
    print()

    # 按 tier 切分成多个 batch，每 batch 最多 batch_size 个。
    # start_id 只是喂给 prompt 的建议编号，最终会在落盘前统一重排，保证全局唯一。
    tasks_args: list[tuple[str, int, int]] = []
    cur_id = 1
    for tier_label, total in SCHOOL_TIER_PLAN:
        remaining = total * args.scale
        while remaining > 0:
            n = min(args.batch_size, remaining)
            tasks_args.append((tier_label, n, cur_id))
            cur_id += n
            remaining -= n

    if args.limit_batches > 0:
        tasks_args = tasks_args[: args.limit_batches]

    sem = asyncio.Semaphore(args.max_concurrency)
    max_attempts = 4

    async def run_one(tier_label: str, n: int, start: int) -> list[CandidateProfile]:
        async with sem:
            await asyncio.sleep(random.uniform(0, 1.5))
            # catch 异常 + 多次重试，绝不让单 batch 失败炸掉整个 gather
            for attempt in range(max_attempts):
                try:
                    out = await generate_personas_for_tier(
                        router, tier_label, n, start
                    )
                    if out:
                        return out
                except Exception as e:
                    short = str(e).splitlines()[0][:90]
                    print(f"  [ERR] {tier_label} 第 {attempt + 1} 次: {short}")
                if attempt < max_attempts - 1:
                    backoff = min(20.0, 4.0 * (2**attempt)) + random.uniform(0, 3)
                    await asyncio.sleep(backoff)
            print(f"  [GIVEUP] {tier_label}: {max_attempts} 次仍失败，本批放弃")
            return []

    print(f"开始生成 {len(tasks_args)} 个 batch（目标 ~{sum(t[1] for t in tasks_args)} 人）...")
    results = await asyncio.gather(*[run_one(*t) for t in tasks_args])
    await router.close()

    personas: list[CandidateProfile] = []
    for batch in results:
        personas.extend(batch)

    raw = [p.model_dump(mode="json") for p in personas]

    # 全局重排 candidate_id，保证唯一（scale 后各 batch 的 start_id 会重叠，
    # 且 LLM 本就常忽略 start_id 建议编号）。用零填充位宽适配总量。
    width = max(3, len(str(len(raw))))
    for idx, item in enumerate(raw, start=1):
        item["candidate_id"] = f"compete_{idx:0{width}d}"

    payload, triggers = _sanitize(raw)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"已生成 {len(payload)} 个 persona -> {out_path}")
    if triggers:
        print(f"sanitizer 触发 {len(triggers)} 处:")
        for t in triggers[:10]:
            print(f"  {t}")
        if len(triggers) > 10:
            print(f"  ... 共 {len(triggers)} 处")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
