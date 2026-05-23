"""
公司画像 + JD 种子数据生成器（LLM 驱动，零手写）。

设计原则：
1. 不在代码里硬编码任何"具体的公司"——脑补出来的数据质量未必比 LLM 好
2. 参数化覆盖：行业、规模、招聘风格的分布在参数里写，LLM 按分布生成
3. 严格 schema：LLM 输出 JSON → Pydantic 校验 → 校验失败则重试或丢弃
4. 可复用：换数据集 = 改参数，不动代码
5. token 在 LLM 端，不在我的"创作"端

字段对齐：
- 第一层 OfficialJD 字段严格按答疑文档 Q2 推荐格式（11 字段）
- 第二层 CompanyHiddenSignals 是产品差异化（应届生关心但 JD 不写）

合规：全部 synthetic 合成（data_source 字段已标记），demo 用代号公司，挂"基于公开数据建模"水印。

D1（无 key 时）：本脚本通过 --dry-run 打印示例 prompt，验证流程
D2（有 key 时）：去掉 --dry-run 真跑 LLM
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
from app.models.company import CompanyProfile, HiringStyle  # noqa: E402
from app.services.llm import Tier, build_router  # noqa: E402

# ============================================================
# 生成参数（按需调整覆盖度）
# ============================================================

# 行业分布。LLM 会按数量生成对应行业的公司
# 细分到具体赛道，避免"互联网大厂"这种宽泛 prompt 导致 LLM 重复套同一模板
INDUSTRY_PLAN: list[tuple[str, int]] = [
    # === 互联网细分（12 家） ===
    ("互联网-短视频/直播", 2),
    ("互联网-电商/电商平台", 2),
    ("互联网-本地生活/外卖", 2),
    ("互联网-社交/内容社区", 2),
    ("互联网-搜索/工具/SaaS", 2),
    ("互联网-在线音乐/长视频", 2),
    # === AI（9 家） ===
    ("AI-基础模型创业（头部大模型）", 3),
    ("AI-具身智能/机器人", 2),
    ("AI-医疗影像/制药", 2),
    ("AI-应用层（Agent/RAG/垂直工具）", 2),
    # === 金融（6 家） ===
    ("金融-头部券商", 1),
    ("金融-头部公募基金", 1),
    ("金融-头部量化私募", 2),
    ("金融-银行/保险科技", 2),
    # === 硬件（5 家） ===
    ("硬件-通信/网络设备", 1),
    ("硬件-半导体设计/EDA", 2),
    ("硬件-消费电子/品牌", 1),
    ("硬件-工业软件/精密仪器", 1),
    # === 国央企/体制（4 家） ===
    ("国央企-能源/电网", 1),
    ("国央企-航空航天/军工", 1),
    ("国央企-基建/三大运营商", 1),
    ("政府/事业单位（数字政务方向）", 1),
    # === 新能源 / 智能制造（3 家） ===
    ("新能源车-头部", 2),
    ("新能源-储能/光伏/动力电池", 1),
    # === 外企（3 家） ===
    ("外企-科技/中国研发中心", 2),
    ("外企-传统制造/快消", 1),
    # === 游戏（3 家） ===
    ("游戏-头部（二次元/3A 级）", 2),
    ("游戏-中小厂/独立工作室", 1),
    # === 咨询（2 家） ===
    ("咨询-MBB 级", 1),
    ("咨询-本土头部", 1),
    # === 其他（3 家） ===
    ("教育科技/在线教育", 1),
    ("生物医药/CRO", 1),
    ("跨境电商/出海品牌", 1),
]

# 规模标签（让 LLM 在每条公司画像里选一个）
SIZE_LABELS = [
    "STARTUP（< 100 人）",
    "SMALL（100-500 人）",
    "MEDIUM（500-5000 人）",
    "LARGE（5000-50000 人）",
    "MEGA（> 50000 人）",
]


# ============================================================
# Prompt 构造
# ============================================================


SYSTEM_PROMPT = """你是一个虚构数据生成器，为"AI 校招沙盘模拟"系统生成代表性的虚构公司画像。

绝对规则：
1. 全部 synthetic 数据。公司必须用代号（"A 厂" "AI-α" "金-2" 等）
2. **任何字段都不准直接出现真实公司名**（包括 inspired_by_hint）。
   inspired_by_hint 用泛指表达：
   - 例如 "某头部短视频平台量级" 而不是 "字节量级"
   - 例如 "某 TOP3 综合互联网厂量级" 而不是 "腾讯/阿里量级"
   - 例如 "某头部量化私募量级" 而不是写出具体私募名
3. 输出严格的 JSON，不要 markdown 代码块，不要 ``` 包裹，不要任何解释文字
4. JSON 必须能被 Pydantic 直接解析为 CompanyProfile

输出规范：根 JSON 是一个对象数组，每个对象对应一家公司，结构如下：

{
  "code_name": "代号，如 'A 厂' / 'AI-α' / '金-2'（不准用真公司名）",
  "inspired_by_hint": "",
  "industry": "行业大类，如 '互联网'",
  "size_label": "规模标签，从给定枚举里选",
  "headquarters_city": "总部城市",
  "job_postings": [
    {
      "job_title": "职位名称，如 '后端工程师-校招'",
      "job_category": "职类，如 '技术' / '产品' / '运营' / '咨询'",
      "salary": "薪资文本，如 '25-35k·15薪' 或 '60-150k·14薪'",
      "years_required": "年限要求，如 '应届' / '应届+实习经验'",
      "degree_required": "学历要求，如 '本科及以上' / '硕士及以上'",
      "city_required": "城市，如 '北京'",
      "keywords": ["技能关键词列表，5-8 个"],
      "description": "职位描述长文本，80-150 字，HR 用语风格",
      "company_name": "和外层 code_name 一致",
      "work_address": "具体地址",
      "publish_date": "YYYY-MM-DD 格式，今天日期"
    }
  ],
  "hidden_signals": {
    "hiring_bar": 0-100 整数,
    "hiring_style": "枚举值，从 pedigree_first/project_heavy/leetcode_heavy/culture_fit/case_based 五个里选一个",
    "culture_tags": ["3-6 个文化关键词，如 '996' '扁平' 'P 级森严' 等"],
    "business_growth": 0-100 整数,
    "pct_over_35": 0-100 整数,
    "hidden_filters": ["2-4 条 JD 字面不写但实际筛简历会用的隐性门槛"]
  },
  "data_source": "synthetic",
  "generated_at": "今天日期"
}

每家公司至少 1 个 JD，互联网大厂/AI 公司至少 2 个 JD（覆盖技术 + 产品/算法）。
hiring_bar 与公司档次匹配：顶尖大模型公司 90+，大厂 80-90，国企 70 左右。
"""


def build_user_prompt(industry: str, count: int, today: str) -> str:
    """单个行业一次性生成 N 家公司"""
    # 强制 hiring_style 多样化（避免 LLM 默认偏向 project_heavy）
    if count >= 3:
        style_constraint = (
            f"hiring_style 多样化硬约束：本批 {count} 家公司必须至少覆盖 3 种不同的 hiring_style，"
            f"不允许出现『多家同 style』的偷懒。"
        )
    elif count == 2:
        style_constraint = "hiring_style 多样化硬约束：2 家公司的 hiring_style 必须不同。"
    else:
        # 只有 1 家时无法约束，但要求 hiring_style 与行业默认认知一致即可
        style_constraint = ""

    return f"""请生成 {count} 家"{industry}"细分赛道的虚构公司画像。

【多样性要求】
- 同一赛道里不同公司在 hiring_bar、薪资带、文化标签、隐性门槛上要有显著差异
- 不要每家都"996/扁平/重技术/数据驱动"这种 LLM 默认套娃
- {style_constraint}
- size_label 从 {SIZE_LABELS} 中按行业实际情况合理选择
- 公司代号要有创意（"A 厂" "AI-α" "金-2" 只是举例，可以自由发挥成 "短-1" "电-α" "智云" "蓝盾" 等）
- 文化标签里可以加些"具体而非套话"的描述，例如 "晨会 9:30 半小时" "PPT 文化" "技术评审制" "扁平但派系" 等

【真公司名禁令】
所有字段（包括 inspired_by_hint）不准出现任何真实公司名。用"某头部短视频平台" "某 TOP 综合互联网厂" "某新势力车企量级" 这类泛指。

【输出格式】
今天日期：{today}（用作 generated_at 和 publish_date 字段）
严格的 JSON 数组（长度 = {count}），不要 markdown 包裹或解释文字。"""


# ============================================================
# 生成器：调用 LLM 并解析
# ============================================================


def _strip_code_fences(text: str) -> str:
    """LLM 偶尔会用 ``` 包裹 JSON，去掉"""
    t = text.strip()
    if t.startswith("```"):
        # 去掉 ```json 或 ``` 开头
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1 :]
        # 去掉末尾 ```
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


# 真公司名 → 泛指代号的兜底替换表。
# prompt 已经禁止真名但 LLM 偶发会漏（约 5% 概率），落盘前自动 sanitize。
# 替换原则：保留行业属性 + 模糊化具体身份
_REAL_NAME_REPLACEMENTS: dict[str, str] = {
    # 互联网大厂
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
    # 硬件 / 通信
    "华为": "某通信设备巨头",
    "中兴": "某通信设备厂",
    "联想": "某 PC+服务器厂",
    "海康威视": "某安防视觉厂",
    "海康": "某安防视觉厂",
    # 新能源 / 制造
    "蔚来": "某新势力车企",
    "理想": "某新势力车企",
    "小鹏": "某新势力车企",
    "比亚迪": "某头部新能源车企",
    "宁德时代": "某动力电池巨头",
    "宁德": "某动力电池巨头",
    # 金融
    "华泰证券": "某头部券商",
    "华泰": "某头部券商",
    "中信证券": "某头部券商",
    "中信": "某头部券商",
    "高盛": "某顶级外资投行",
    "摩根士丹利": "某顶级外资投行",
    "摩根": "某顶级外资投行",
    "汇丰": "某外资银行",
    "工行": "某国有大行",
    "建行": "某国有大行",
    "农行": "某国有大行",
    # 咨询
    "麦肯锡": "某 MBB 级咨询",
    "贝恩": "某 MBB 级咨询",
    "BCG": "某 MBB 级咨询",
    "波士顿咨询": "某 MBB 级咨询",
    # 游戏
    "米哈游": "某二次元头部游戏厂",
    "莉莉丝": "某出海游戏厂",
    # 校名缩写（LLM 偶尔在 description 里提学校）
    "南大": "某 C9 院校",
    "北大": "某 C9 院校",
    "清华": "某 C9 院校",
    "复旦": "某 C9 院校",
    "浙大": "某 C9 院校",
    "交大": "某 C9 院校",
}


def _sanitize_real_names(payload: list[dict]) -> tuple[list[dict], list[str]]:
    """递归遍历 dict/list/str，把已知真公司名替换成泛指代号。
    返回 (清洗后数据, 触发替换的 path 列表)"""
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
                    triggers.append(f"{path}: '{real}' -> '{alias}'")
            return new
        return node

    cleaned = walk(payload, "$")
    return cleaned, triggers


async def generate_companies_for_industry(
    router: Any, industry: str, count: int, today: str
) -> list[CompanyProfile]:
    """单个行业批量生成。失败时返回空列表，由上层决定是否重试"""

    prompt = build_user_prompt(industry, count, today)
    resp = await router.generate(
        prompt,
        system=SYSTEM_PROMPT,
        tier=Tier.SECONDARY,  # 数据生成用配角档够了，不用最贵的
        max_tokens=8192,
        temperature=0.85,  # 高 temperature 保证多样性
    )

    try:
        raw = _strip_code_fences(resp.text)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] {industry}: JSON 解析失败 ({e})，跳过")
        return []

    if not isinstance(data, list):
        print(f"  [WARN] {industry}: LLM 返回不是数组，跳过")
        return []

    valid: list[CompanyProfile] = []
    for i, item in enumerate(data):
        try:
            valid.append(CompanyProfile.model_validate(item))
        except Exception as e:
            print(f"  [WARN] {industry}#{i}: Pydantic 校验失败 ({e})，丢弃")
    print(f"  {industry}: 请求 {count}，LLM 返回 {len(data)}，通过校验 {len(valid)}")
    return valid


# ============================================================
# 主流程
# ============================================================


async def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "backend" / "data" / "companies" / "companies_v1.json"),
        help="输出 JSON 路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 prompt 不调用 LLM。用于验证 prompt 内容",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="并行调用的行业批数，控制 API 速率",
    )
    args = parser.parse_args(argv)

    today = "2026-05-23"

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(SYSTEM_PROMPT[:1500])
        print("...")
        print()
        print("=== 示例 USER PROMPT（互联网大厂 4 家） ===")
        print(build_user_prompt("互联网大厂", 4, today))
        return

    # 真跑：构建 router 并并发生成
    settings = get_settings()
    router = build_router(settings)
    print("=== LLM 路由 ===")
    for t, target in router.describe_routing().items():
        print(f"  {t:11} -> {target}")
    print()

    # 信号量限制并发
    sem = asyncio.Semaphore(args.max_concurrency)

    async def run_one(industry: str, count: int) -> list[CompanyProfile]:
        async with sem:
            return await generate_companies_for_industry(router, industry, count, today)

    print(f"开始生成 {len(INDUSTRY_PLAN)} 个行业批次...")
    results = await asyncio.gather(*[run_one(ind, n) for ind, n in INDUSTRY_PLAN])
    await router.close()

    # 扁平化
    companies: list[CompanyProfile] = []
    for batch in results:
        companies.extend(batch)

    # 落盘前 sanitize：把 LLM 漏过 prompt 约束的真公司名替换成泛指代号
    payload_raw = [c.model_dump(mode="json") for c in companies]
    payload, triggers = _sanitize_real_names(payload_raw)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    total_jds = sum(len(c.get("job_postings", [])) for c in payload)
    industries = {c["industry"] for c in payload}
    print()
    print(f"已生成 {len(payload)} 家公司 / {total_jds} 个 JD -> {out_path}")
    print(f"覆盖行业 {len(industries)} 个")
    if triggers:
        print(f"sanitizer 触发 {len(triggers)} 处替换:")
        for t in triggers[:10]:
            print(f"  {t}")
        if len(triggers) > 10:
            print(f"  ... 共 {len(triggers)} 处")
    else:
        print("sanitizer 未触发（全部合规）")


if __name__ == "__main__":
    random.seed()
    asyncio.run(main(sys.argv[1:]))
