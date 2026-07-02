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
import time
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
#
# 扩容说明（v2）：
# 单批 count 保持 <= 5（LLM 单批太大会套娃雷同）。要堆到 ~300 家，靠两条腿：
#   1. 更多细分赛道（下方 plan 已扩到 ~55 个赛道）
#   2. 同一赛道跑多批，每批带不同 variant（地域×规模×档次约束），见 BATCH_VARIANTS
# 每个 (industry, count) 会被下面的 expand_plan() 按 repeat 次数展开成多个带 variant 的批次。
# 元组格式：(赛道名, 每批家数, 重复批数)
INDUSTRY_PLAN: list[tuple[str, int, int]] = [
    # === 互联网细分 ===
    ("互联网-短视频/直播", 4, 3),
    ("互联网-电商/电商平台", 4, 2),
    ("互联网-本地生活/外卖/O2O", 4, 2),
    ("互联网-社交/内容社区", 4, 2),
    ("互联网-搜索/工具/效率SaaS", 4, 2),
    ("互联网-在线音乐/长视频/内容", 4, 1),
    ("互联网-企业服务/云计算/PaaS", 4, 3),
    ("互联网-金融科技/支付", 4, 1),
    ("互联网-在线旅游/出行平台", 4, 1),
    ("互联网-招聘/教育/工具类平台", 4, 1),
    # === AI ===
    ("AI-基础模型创业（头部大模型）", 4, 3),
    ("AI-具身智能/机器人", 4, 2),
    ("AI-医疗影像/AI制药", 4, 1),
    ("AI-应用层（Agent/RAG/垂直工具）", 4, 3),
    ("AI-自动驾驶/智能驾驶", 4, 1),
    ("AI-芯片/算力基础设施", 4, 1),
    ("AI-AIGC/多模态内容生成", 4, 1),
    # === 金融 ===
    ("金融-头部券商/投行", 4, 1),
    ("金融-头部公募基金/资管", 4, 1),
    ("金融-头部量化私募", 4, 3),
    ("金融-银行/保险科技", 4, 2),
    ("金融-互联网消费金融", 4, 1),
    # === 硬件 / 半导体 ===
    ("硬件-通信/网络设备", 4, 1),
    ("硬件-半导体设计/EDA", 4, 3),
    ("硬件-消费电子/品牌", 4, 1),
    ("硬件-工业软件/精密仪器", 4, 1),
    ("硬件-显示/面板/光学", 4, 1),
    # === 国央企/体制 ===
    ("国央企-能源/电网", 4, 1),
    ("国央企-航空航天/军工", 4, 1),
    ("国央企-基建/三大运营商", 4, 1),
    ("国央企-金融/大型银行总行", 4, 1),
    ("政府/事业单位（数字政务方向）", 2, 1),
    # === 新能源 / 智能制造 ===
    ("新能源车-头部整车厂", 4, 3),
    ("新能源-储能/光伏/动力电池", 4, 1),
    ("智能制造-工业机器人/自动化", 4, 1),
    # === 外企 ===
    ("外企-科技/中国研发中心", 4, 3),
    ("外企-传统制造/快消", 4, 1),
    ("外企-医药/器械跨国公司", 4, 1),
    # === 游戏 ===
    ("游戏-头部（二次元/3A 级）", 4, 2),
    ("游戏-中小厂/独立工作室", 4, 1),
    ("游戏-出海/发行/买量", 4, 1),
    # === 咨询 ===
    ("咨询-MBB 级战略咨询", 2, 1),
    ("咨询-本土头部/四大", 4, 2),
    # === 医药 / 生命科学 ===
    ("生物医药/创新药研发", 4, 2),
    ("医药-CRO/CDMO", 4, 1),
    ("医疗器械/IVD", 4, 1),
    # === 跨境 / 消费 ===
    ("跨境电商/出海品牌", 4, 1),
    ("新消费/连锁餐饮零售", 4, 1),
    # === 教育 / 内容 ===
    ("教育科技/在线教育", 4, 1),
    ("文娱/传媒/影视", 4, 1),
    # === 其他实体 ===
    ("房地产/物业科技", 2, 1),
    ("物流/供应链科技", 4, 2),
    ("Web3/区块链（合规向）", 2, 1),
]

# 规模标签（让 LLM 在每条公司画像里选一个）
SIZE_LABELS = [
    "STARTUP（< 100 人）",
    "SMALL（100-500 人）",
    "MEDIUM（500-5000 人）",
    "LARGE（5000-50000 人）",
    "MEGA（> 50000 人）",
]

# 批次 variant：同一赛道跑多批时，给每批注入不同的"地域×规模×档次"侧重，
# 让重复批次不撞车（否则 LLM 会把同赛道的多批生成得高度雷同）。
# 每个 variant 是一句加进 user_prompt 的软约束。
BATCH_VARIANTS: list[str] = [
    "本批侧重：华北/北京-天津，规模偏 LARGE/MEGA，档次偏头部大厂，hiring_bar 偏高（80+）。",
    "本批侧重：华东/上海-杭州-苏州，规模偏 MEDIUM，档次偏腰部成长型公司，hiring_bar 中等（70-82）。",
    "本批侧重：华南/深圳-广州，规模偏 SMALL/STARTUP，档次偏创业公司，hiring_bar 分散（60-85），薪资带宽。",
    "本批侧重：中西部/成都-武汉-西安/新一线，规模偏 MEDIUM/LARGE，档次偏区域龙头，hiring_bar 中等偏下（65-78）。",
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


def build_user_prompt(industry: str, count: int, today: str, variant: str = "") -> str:
    """单个行业一次性生成 N 家公司。variant 是本批的地域×规模×档次侧重软约束。"""
    # 强制 hiring_style 多样化（避免 LLM 默认偏向 project_heavy）
    if count >= 3:
        style_constraint = (
            f"hiring_style 多样化硬约束：本批 {count} 家公司必须至少覆盖 3 种不同的 hiring_style，"
            f"且整体上 5 种 style（pedigree_first/project_heavy/leetcode_heavy/culture_fit/case_based）都应有机会出现；"
            f"不允许出现『多家同 style』的偷懒。算法/工程密集赛道优先考虑 leetcode_heavy。"
        )
    elif count == 2:
        style_constraint = "hiring_style 多样化硬约束：2 家公司的 hiring_style 必须不同。"
    else:
        # 只有 1 家时无法约束，但要求 hiring_style 与行业默认认知一致即可
        style_constraint = ""

    variant_block = ""
    if variant:
        variant_block = f"\n【本批侧重（务必遵守，让本批和同赛道其它批次区分开）】\n- {variant}\n"

    return f"""请生成 {count} 家"{industry}"细分赛道的虚构公司画像。
{variant_block}
【多样性要求】
- 同一赛道里不同公司在 hiring_bar、薪资带、文化标签、隐性门槛上要有显著差异
- 不要每家都"996/扁平/重技术/数据驱动"这种 LLM 默认套娃
- {style_constraint}
- hiring_bar 不要扎堆在 85，按公司实际档次在 55-98 之间分散取值
- size_label 从 {SIZE_LABELS} 中按行业实际情况合理选择（严格照抄括号里的写法，不要改动空格）
- 公司代号要有创意（"A 厂" "AI-α" "金-2" 只是举例，可以自由发挥成 "短-1" "电-α" "智云" "蓝盾" 等），且不要和常见批次重名
- 文化标签里可以加些"具体而非套话"的描述，例如 "晨会 9:30 半小时" "PPT 文化" "技术评审制" "扁平但派系" 等

【真公司名禁令】
所有字段（包括 inspired_by_hint）不准出现任何真实公司名。用"某头部短视频平台" "某 TOP 综合互联网厂" "某新势力车企量级" 这类泛指。

【输出格式】
今天日期：{today}（用作 generated_at 和 publish_date 字段）
严格的 JSON 数组（长度 = {count}），不要 markdown 包裹或解释文字。"""


def expand_plan(
    plan: list[tuple[str, int, int]],
) -> list[tuple[str, int, str]]:
    """把 (industry, count, repeat) 展开成 repeat 个 (industry, count, variant) 批次。
    每个重复批次轮流套用不同的 BATCH_VARIANTS，避免同赛道多批雷同。"""
    batches: list[tuple[str, int, str]] = []
    for industry, count, repeat in plan:
        for r in range(repeat):
            if repeat <= 1:
                variant = ""
            else:
                variant = BATCH_VARIANTS[r % len(BATCH_VARIANTS)]
            batches.append((industry, count, variant))
    return batches


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
    "理想汽车": "某新势力车企",
    "小鹏汽车": "某新势力车企",
    "比亚迪": "某头部新能源车企",
    "宁德时代": "某动力电池巨头",
    # 注意：不放裸"宁德"/"理想"——宁德是福建地级市（宁德市蕉城区），
    # 理想是常用词，裸匹配会误伤 city/work_address。只匹配完整公司名。
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
    # 注意：不放裸"南大"——"南大街"是常见路名，会误伤 work_address。
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
    router: Any, industry: str, count: int, today: str, variant: str = ""
) -> list[CompanyProfile]:
    """单个行业批量生成。失败时返回空列表，由上层决定是否重试"""

    prompt = build_user_prompt(industry, count, today, variant)
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
    parser.add_argument(
        "--limit-batches",
        type=int,
        default=0,
        help="仅跑前 N 个批次（小批验证用），0 表示全跑",
    )
    parser.add_argument(
        "--gen-provider",
        default="",
        help="覆盖 SECONDARY 档的 provider:model（如 deepseek:deepseek-chat）。"
        "某国际AI芯片大厂 70B 若被限流，用它切到 deepseek。留空则用 .env 默认路由。",
    )
    args = parser.parse_args(argv)

    today = "2026-05-23"

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(SYSTEM_PROMPT[:1500])
        print("...")
        print()
        print("=== 示例 USER PROMPT（互联网大厂 4 家） ===")
        print(build_user_prompt("互联网大厂", 4, today, BATCH_VARIANTS[0]))
        return

    # 真跑：构建 router 并并发生成
    settings = get_settings()
    router = build_router(settings)

    # 可选：把生成用的 SECONDARY 档重路由到别的 provider（不改 .env）。
    # 场景：某国际AI芯片大厂 70B 被限流到不可用时，切到 deepseek。
    if args.gen_provider:
        prov_name, _, model = args.gen_provider.partition(":")
        if prov_name not in router._providers:
            raise SystemExit(
                f"--gen-provider 引用了未注册 provider={prov_name}，"
                f"已注册: {list(router._providers.keys())}"
            )
        router._routing[Tier.SECONDARY] = (router._providers[prov_name], model)
        print(f"[override] SECONDARY 档重路由到 {prov_name}:{model}")

    print("=== LLM 路由 ===")
    for t, target in router.describe_routing().items():
        print(f"  {t:11} -> {target}")
    print()

    # 把 plan 展开成带 variant 的批次
    batches = expand_plan(INDUSTRY_PLAN)
    if args.limit_batches > 0:
        batches = batches[: args.limit_batches]

    # 信号量限制并发
    sem = asyncio.Semaphore(args.max_concurrency)

    # 单批最多尝试次数（429 环境下多给几次机会）
    max_attempts = 5

    async def run_one(industry: str, count: int, variant: str) -> list[CompanyProfile]:
        async with sem:
            # 进入临界区先加一点随机抖动，把并发请求在时间轴上错开，缓解 429 撞墙
            await asyncio.sleep(random.uniform(0, 1.5))
            # 单批带最多 max_attempts 次尝试：JSON 解析失败/429/超时抛异常或返回空时补发。
            # 关键：catch 异常，绝不让单批失败炸掉整个 gather（否则几百次调用里
            # 只要有一次 provider 3 次重试仍失败，全部结果丢失）。
            for attempt in range(max_attempts):
                try:
                    out = await generate_companies_for_industry(
                        router, industry, count, today, variant
                    )
                    if out:
                        return out
                except Exception as e:
                    short = str(e).splitlines()[0][:100]
                    print(f"  [ERR] {industry} 第 {attempt + 1} 次: {short}")
                if attempt < max_attempts - 1:
                    # 429 是限流，退避要够长；指数退避 + 抖动，避免所有失败批同时重发
                    backoff = min(20.0, 4.0 * (2**attempt)) + random.uniform(0, 3)
                    print(
                        f"  [RETRY] {industry}: {backoff:.0f}s 后补发（第 {attempt + 2} 次）"
                    )
                    await asyncio.sleep(backoff)
            print(f"  [GIVEUP] {industry}: {max_attempts} 次仍失败，本批放弃")
            return []

    total_target = sum(n for _, n, _ in batches)
    print(f"开始生成 {len(batches)} 个批次（目标 ~{total_target} 家）...")
    results = await asyncio.gather(*[run_one(*b) for b in batches])
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
