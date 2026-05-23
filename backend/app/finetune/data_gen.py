"""
SFT 训练数据生成器。

输入：用户原始材料
  - 简历文本（PDF 已转 Markdown 或纯文本）
  - GitHub URL（仓库列表 / pinned repo 描述）
  - blog URL 列表（文章标题 + 摘要）
输出：backend/data/finetune/sft_<user_id>.jsonl

每条 jsonl 形态对齐 HuggingFace Alpaca/Unsloth 的标准三元组：
  {"instruction": "...", "input": "...", "output": "...", "meta": {...}}

为什么是这种 schema：
  Unsloth 的 to_sharegpt / standardize_sharegpt 都能直接吃这个三元组；
  HF AutoTrain / LLaMA-Factory 也认。换框架只改 train.py，不动数据。

为什么"求职决策"为主题，不是一般对话：
  我们要的不是"会唠嗑的用户分身"，而是"能在沙盘做投递/谈判/接拒决策的分身"。
  所以训练目标紧紧围绕 simulation 里 CandidateAgent 会做的几类决策。

为什么用 BACKGROUND tier 生成：
  数据生成属于"批量、价格敏感"场景；BACKGROUND 是项目里最便宜的档（按 .env 当前
  配置仍是 deepseek-chat，等 qwen-turbo key 到位会自动切）。质量已足够——
  SFT 数据不需要 SOTA 模型生成，更看重多样性。

并发与速率：
  默认 4 路并发（与 collect_personas.py 一致），失败不致命，最终落盘的样本数
  > 200 即视为通过。

【重要】调用方负责：
  data_gen 不做用户材料抓取（GitHub / blog 真实爬虫属另一个 service 范畴）。
  这里把 GitHub URL / blog URL 当"输入提示"传给 LLM，由 LLM 基于其先验粗略联想
  典型贡献者画像；如果未来接入了真爬虫，调一下 build_user_facts 即可，不改下游。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.llm import LLMRouter, Tier, build_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================
# 输入数据结构
# ============================================================


@dataclass
class UserMaterial:
    """用户上传的原始材料汇总。
    不强制要求字段都填——只要有 resume_text 一条也能训出能用的 persona"""

    user_id: str
    # 简历正文。PDF 调用方应先转 markdown / 文本，保留段落即可
    resume_text: str = ""
    # GitHub 主页 URL（如 https://github.com/<username>）
    github_url: str = ""
    # 多个 blog 文章 URL 或者站点 URL
    blog_urls: list[str] = field(default_factory=list)
    # 期望职位（用户在前端勾选的）
    target_roles: list[str] = field(default_factory=list)
    target_industries: list[str] = field(default_factory=list)
    target_cities: list[str] = field(default_factory=list)
    # 用户已经填好的 14 字段 CV（如果有），可让生成更精准。dict 形式避免循环依赖
    cv_brief: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 训练对的"题型分布"
# ============================================================

# 题型分布。每种题型代表 simulation 里一类决策行为。
# 数量配比是经验值：
#   投递决策（apply）和 offer 响应（accept/decline）是 sim 里出现频次最高的，配额最大；
#   谈判（negotiate）量少但需要差异化样本；
#   自我介绍 / 价值观 / 反思类是给模型"声音 / tone"基底，量适中。
DECISION_BUCKETS: list[tuple[str, int]] = [
    # bucket_key, target_count
    ("apply_decision", 80),       # 看到一条 JD 决定投不投
    ("offer_response", 80),       # 拿到 offer 决定 accept/decline/negotiate
    ("self_intro", 30),           # 自我介绍 / 面试开场
    ("why_this_company", 30),     # "为什么投这家"
    ("strength_weakness", 25),    # 优劣势复盘
    ("negotiation", 25),          # 谈判话术
    ("priority_tradeoff", 25),    # 多个 offer 横向对比
    ("week_reflection", 25),      # 周复盘 / 心态
]
# 合计 320。> 200 验收线，留 buffer 容忍 LLM 偶发跳过


# 每个 bucket 对应一段 user prompt 模板。
# 模板里的 {facts} 由 build_user_facts() 注入；{batch_size} 控制单次返回几条。
BUCKET_PROMPTS: dict[str, str] = {
    "apply_decision": """
请基于用户画像，模拟 {batch_size} 条 "看到 JD 决定投不投" 的训练样本。

每条样本：
- instruction: 固定为 "以这位用户的口吻，决定是否投递以下岗位，给出 accept/decline 和理由"
- input: 一段拟真的岗位 JD 摘要（公司代号、岗位名、城市、薪资、关键词、可能的隐性信号 1-2 条）。
         要求"匹配度故意有差异"——不要 {batch_size} 条全是高匹配，应该 1/3 高匹配、
         1/3 中匹配（有遗憾点）、1/3 低匹配（用户大概率会拒）。
- output: 用户的回答。包含：
  * 决定（accept 或 decline）
  * 1-3 条理由，必须能映射回画像里的具体字段（"我目标行业是 X" / "我项目都在 Y"）
  * 如果 decline，用婉转但坚定的语气
""",
    "offer_response": """
请基于用户画像，模拟 {batch_size} 条 "拿到 offer 后决定 accept / decline / negotiate" 的训练样本。

每条样本：
- instruction: 固定为 "以这位用户的口吻，回应以下 offer"
- input: offer 描述（公司、岗位、薪资、加班文化标签、过期周数等）。
         差异化覆盖：超出预期 offer、勉强达标 offer、明显低于期望 offer。
- output: 用户的回应。包含：
  * 决定（accept / decline / negotiate）
  * 理由，引用画像偏好字段
  * 若 negotiate，给出具体加薪幅度或额外诉求
""",
    "self_intro": """
请基于用户画像，模拟 {batch_size} 条 "自我介绍 / 面试开场白" 的训练样本。

每条样本：
- instruction: 固定为 "用 30 秒做一段面向 <场景> 的自我介绍"，
               <场景> 在以下里随机一个：技术面、HR 面、群面破冰、Networking 茶歇
- input: 留空字符串 ""
- output: 1-3 句自我介绍。必须是"用户口吻"，不能机械堆 keywords，
         要体现画像里的项目 / 价值观 / 目标。
""",
    "why_this_company": """
请基于用户画像，模拟 {batch_size} 条 "为什么投这家公司 / 这个岗位" 的训练样本。

每条样本：
- instruction: 固定 "回答：为什么选择 <公司代号> 的 <岗位>？"
- input: 简短公司描述 + 岗位描述
- output: 体现用户独立思考的 motivation。不能说"贵公司很好"这种废话。
         要么用画像里的项目经历挂钩岗位，要么用价值观挂钩文化。
""",
    "strength_weakness": """
请基于用户画像，模拟 {batch_size} 条 "优势 / 劣势 / 失败经历复盘" 类训练样本。

每条样本：
- instruction: 在以下里随机一个：
  * "请讲一个最有成就感的项目"
  * "请讲一段最大的失败 / 挫折"
  * "你最大的优势 / 劣势是什么"
  * "你和最优秀的同学相比差距在哪"
- input: 留空 ""
- output: 用户的真实回答风格。失败 / 劣势要真实，但带反思与改进动作。
""",
    "negotiation": """
请基于用户画像，模拟 {batch_size} 条 "薪资 / package 谈判" 训练样本。

每条样本：
- instruction: 固定 "面对以下 offer 条件，写一段你向 HR 表达谈判诉求的话"
- input: offer 现状 + 用户拿到的对比 offer（可以是"另一家 base 高 4k"）
- output: 一段克制专业的谈判话术，至少包含：
  * 明确想要的目标数字 / 条件
  * 一条"我值得"的理由
  * 保留余地（不要把话说死）
""",
    "priority_tradeoff": """
请基于用户画像，模拟 {batch_size} 条 "多 offer 横向比较选择" 训练样本。

每条样本：
- instruction: 固定 "在以下两个 offer 之间，你倾向选哪一个，为什么"
- input: A offer vs B offer 的对比表（薪资 / 城市 / 行业 / 文化标签）
         设计上保持"两个 offer 各有优势"，迫使输出展现取舍逻辑
- output: 用户的选择 + 至少 2 个权衡点
""",
    "week_reflection": """
请基于用户画像，模拟 {batch_size} 条 "春招某一周末复盘 / 心态" 类训练样本。

每条样本：
- instruction: 固定 "用日记口吻，写一段你某一周春招结束时的心态复盘"
- input: 简单情境描述（例 "投了 5 家挂了 4 家" / "拿到第一个 offer 但不满意"）
- output: 1-3 句日记式心态记录。不要太励志，要真实——焦虑 / 自我怀疑 / 微小喜悦都可以。
""",
}


# ============================================================
# Facts 提炼
# ============================================================


def build_user_facts(material: UserMaterial) -> str:
    """把 UserMaterial 压成一段紧凑文本作为 LLM prompt 的画像 context。
    控制在 ~1500 字以内，避免 prompt 爆炸"""

    parts: list[str] = []
    parts.append(f"用户 ID: {material.user_id}")
    if material.target_roles:
        parts.append("目标岗位: " + ", ".join(material.target_roles))
    if material.target_industries:
        parts.append("目标行业: " + ", ".join(material.target_industries))
    if material.target_cities:
        parts.append("目标城市: " + ", ".join(material.target_cities))
    if material.cv_brief:
        # cv_brief 是 dict，序列化时只保留 top 字段，避免太长
        keep_keys = (
            "name", "highest_degree", "age", "personal_strengths",
            "education_history", "project_history", "work_internship_history",
        )
        brief = {k: material.cv_brief.get(k) for k in keep_keys if material.cv_brief.get(k)}
        parts.append("简历摘要（JSON）:\n" + json.dumps(brief, ensure_ascii=False, indent=2)[:1500])

    if material.resume_text:
        # 简历文本可能很长，截前 1500 字
        snippet = material.resume_text.strip()
        if len(snippet) > 1500:
            snippet = snippet[:1500] + " ...[truncated]"
        parts.append("简历正文片段:\n" + snippet)

    if material.github_url:
        parts.append(f"GitHub 主页: {material.github_url}")
        parts.append(
            "（注: GitHub 真实抓取由上游 service 提供。此处若 URL 存在请基于其用户名风格"
            "和 target_roles 联想该用户可能的开源贡献领域，但不要编造具体仓库名）"
        )
    if material.blog_urls:
        parts.append("Blog URLs:\n" + "\n".join(material.blog_urls[:5]))
        parts.append(
            "（同上：blog 真实抓取由上游 service 提供。若仅有 URL，请基于域名和路径"
            "粗略推测博主关注的技术方向）"
        )

    return "\n\n".join(parts)


# ============================================================
# 生成核心
# ============================================================


SYSTEM_PROMPT = """你是一个 SFT 训练数据生成器。任务：基于"用户画像"，
为该用户的"AI 分身"生成训练样本。生成的样本将用于 LoRA 微调，让 base 模型
学会"以这个用户的口吻和价值观，在春招场景下做决策"。

严格规则：
1. 输出严格 JSON 数组，不要 markdown ``` 包裹，不要任何前后解释文字
2. 每条样本严格三字段: instruction, input, output（input 可以为空字符串）
3. 不要编造和用户画像冲突的事实（如画像说本科，不要让用户自称硕士）
4. 不要出现真实公司名 / 真实学校名，用"某厂"、"某 C9 院校"、"A 厂"、"B 厂"等代号
5. output 字段要鲜活有口吻，不要套话——这是训练数据，套话训出来的模型就是说套话
6. 即使 instruction 看起来一样，output 必须有真实的差异化思考，不要堆同义句

风格约束：
- 用户是真实在春招的应届生，语气不要太正式也不要太网络化
- 拒绝时要婉转但坚定，不要"贵公司很优秀但..."的废话开头
- 谈判 / 自荐时要自信但不傲慢
"""


def _strip_code_fences(text: str) -> str:
    """对齐 collect_personas.py 的处理，LLM 偶尔会用 ``` 包裹"""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _validate_sample(sample: Any) -> dict[str, str] | None:
    """轻校验单条样本，不合格返回 None。
    我们不用 Pydantic（避免引入新 model），手工 check 即可"""
    if not isinstance(sample, dict):
        return None
    instr = sample.get("instruction")
    inp = sample.get("input", "")
    out = sample.get("output")
    # instruction / output 必填
    if not isinstance(instr, str) or not instr.strip():
        return None
    if not isinstance(out, str) or not out.strip():
        return None
    if not isinstance(inp, str):
        # 容忍 LLM 偶尔把 input 写成 dict（罕见），统一序列化
        try:
            inp = json.dumps(inp, ensure_ascii=False)
        except Exception:
            inp = ""
    return {
        "instruction": instr.strip(),
        "input": inp.strip(),
        "output": out.strip(),
    }


async def generate_bucket(
    router: LLMRouter,
    bucket_key: str,
    batch_size: int,
    facts: str,
) -> list[dict[str, str]]:
    """为单个题型 bucket 生成一批样本"""
    template = BUCKET_PROMPTS[bucket_key]
    prompt_body = template.format(batch_size=batch_size)

    full_prompt = f"""【用户画像】
{facts}

【本批任务】
题型 bucket: {bucket_key}
本批样本数: {batch_size}

{prompt_body}

输出格式：
[
  {{"instruction": "...", "input": "...", "output": "..."}},
  ...
]

严格 JSON 数组，长度 = {batch_size}，无 markdown 包裹。"""

    try:
        resp = await router.generate(
            full_prompt,
            system=SYSTEM_PROMPT,
            tier=Tier.BACKGROUND,
            # SFT 单条 output 通常 < 300 token，10 条 batch 留 4096 充足
            max_tokens=4096,
            # 高温保证多样性；SFT 数据集不需要"稳定"，需要"覆盖面广"
            temperature=0.9,
        )
    except Exception as e:
        logger.warning(f"bucket={bucket_key} LLM 调用失败: {e}")
        return []

    cleaned = _strip_code_fences(resp.text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"bucket={bucket_key} JSON 解析失败: {e}")
        return []

    if not isinstance(data, list):
        logger.warning(f"bucket={bucket_key} LLM 返回不是数组")
        return []

    valid: list[dict[str, str]] = []
    for item in data:
        v = _validate_sample(item)
        if v is None:
            continue
        # 加 meta，方便后续分析"哪类决策的训练样本分布够不够"
        v["meta"] = json.dumps({"bucket": bucket_key}, ensure_ascii=False)
        valid.append(v)
    return valid


async def generate_sft_dataset(
    router: LLMRouter,
    material: UserMaterial,
    *,
    out_path: Path,
    max_concurrency: int = 4,
    batch_size: int = 10,
) -> int:
    """主入口：为一个用户生成完整 SFT 数据集，落盘 jsonl。
    返回写入的样本数（用于上游 verify > 200）"""

    facts = build_user_facts(material)

    # 把每个 bucket 拆成多个 batch（batch_size 控制单次 LLM 上下文长度）
    tasks_args: list[tuple[str, int]] = []
    for bucket_key, total in DECISION_BUCKETS:
        remaining = total
        while remaining > 0:
            n = min(batch_size, remaining)
            tasks_args.append((bucket_key, n))
            remaining -= n

    sem = asyncio.Semaphore(max_concurrency)

    async def run_one(bucket_key: str, n: int) -> list[dict[str, str]]:
        async with sem:
            return await generate_bucket(router, bucket_key, n, facts)

    logger.info(
        f"开始为 user_id={material.user_id} 生成 SFT 数据，共 {len(tasks_args)} 批"
    )
    results = await asyncio.gather(*[run_one(*t) for t in tasks_args])

    all_samples: list[dict[str, str]] = []
    for batch in results:
        all_samples.extend(batch)

    # 落盘 jsonl
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    logger.info(
        f"SFT 数据集落盘 -> {out_path} (共 {len(all_samples)} 条)"
    )
    return len(all_samples)


# ============================================================
# Mock 数据生成（CPU 验证不联网时用）
# ============================================================


def generate_mock_sft_dataset(
    material: UserMaterial,
    out_path: Path,
    *,
    sample_count: int = 220,
) -> int:
    """完全离线的占位数据生成。
    为什么需要：
      CPU 端到端验证时，开发者本机可能没有 DeepSeek key，或者懒得花钱跑 320 条；
      mock 数据保证 train.py / serve.py 验证链路不阻塞。
      训练出的 mock adapter 不能在真 sim 中用——仅用于跑通 pipeline。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, str]] = []
    # 按 DECISION_BUCKETS 比例分配 sample_count 条假样本
    total_target = sum(n for _, n in DECISION_BUCKETS)
    for bucket_key, share in DECISION_BUCKETS:
        # 按比例下取，最后一个 bucket 补尾巴避免少了
        bucket_n = max(1, round(sample_count * share / total_target))
        for i in range(bucket_n):
            samples.append({
                "instruction": f"[mock {bucket_key}] 第 {i+1} 题：以 {material.user_id} 的口吻回答",
                "input": f"占位输入 {i+1}",
                "output": f"占位输出：这是用户 {material.user_id} 在 {bucket_key} 场景下的占位回答 #{i+1}",
                "meta": json.dumps({"bucket": bucket_key, "mock": True}, ensure_ascii=False),
            })

    with out_path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return len(samples)


# ============================================================
# CLI（数据生成可独立调用，便于离线 debug）
# ============================================================


async def _main_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="生成单用户 SFT 训练数据")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--resume", default="", help="简历文本/markdown 路径")
    parser.add_argument("--github", default="")
    parser.add_argument("--blog", action="append", default=[])
    parser.add_argument("--out", required=True, help="输出 jsonl 路径")
    parser.add_argument("--mock", action="store_true", help="离线占位模式")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args(argv)

    resume_text = ""
    if args.resume:
        resume_text = Path(args.resume).read_text(encoding="utf-8")

    material = UserMaterial(
        user_id=args.user_id,
        resume_text=resume_text,
        github_url=args.github,
        blog_urls=list(args.blog),
    )

    out_path = Path(args.out)

    if args.mock:
        n = generate_mock_sft_dataset(material, out_path)
        print(f"[mock] 已写入 {n} 条样本 -> {out_path}")
        return

    settings = get_settings()
    router = build_router(settings)
    try:
        n = await generate_sft_dataset(
            router,
            material,
            out_path=out_path,
            max_concurrency=args.max_concurrency,
            batch_size=args.batch_size,
        )
    finally:
        await router.close()
    print(f"已写入 {n} 条样本 -> {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main_cli(sys.argv[1:]))
