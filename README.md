# 春招平行宇宙 · Career Multiverse

> **让 AI 替你跑完 1000 次春招**
>
> 智联招聘首届全国 AI 创新大赛 · AI + 求职赛道作品（2026）

---

## 一句话定位

不是 AI 求职工具，是 AI 时代的**人才匹配市场**。

用户上传简历 → 数字分身进入沙盘 → 约 300 家虚构公司 + 约 2000 个竞争者 → simulate 完整春招 → 输出统计结论 + **反事实预演**（"如果你改一处，结果如何变化"）。

---

## 在线 demo

| 入口 | URL |
|---|---|
| 主用户旅程 | http://multiverse.zdwktlj.top/ |
| 市场看板 | http://multiverse.zdwktlj.top/#/dashboard |
| 市场治理 | http://multiverse.zdwktlj.top/#/admin |
| API 文档 | http://multiverse.zdwktlj.top/api/health |

部署在 Azure D2s_v3 (eastus2)，nginx + FastAPI + Vue3。

---

## 产品的三个反转

1. **结构反转**：从"投递→筛选"单向，变成"沙盘撮合 + 决策预演"
2. **载体反转**：从一份 PDF 简历，变成可动态采访的 AI 化身
3. **建议→预演**：从"AI 给建议"，变成"AI 给统计结论 + 反事实分析"

---

## 用户旅程截图

| 步骤 | 截图 |
|---|---|
| 01 上传 | 拖拽简历 + GitHub + Blog |
| 02 画像 | "AI 是怎么认识你的"——LLM 五维评分 + 每维评分理由 + 学校档判定 + Top 5 候选公司 |
| 03 沙盘 | 49 家公司按行业聚成"星团"，化身八面体 + 投递粒子流，支持点击"采访 HR" |
| 04 报告 | 1000 次平行春招的 KPI / 4 数据图表 + 决策树 / 反事实滑动条 / 关键结论 |

附加页面：
- `/dashboard` 市场看板（KPI + 行业 + 招聘门槛 + 学校 tier 分布）
- `/admin` 市场治理（公司池 + 求职者池 CRUD，**评委可现场加一家公司**）

---

## 技术架构

```
[浏览器]
   ↓
nginx (80)
   ├─ /              → Vue3 SPA (Three.js 沙盘 + D3 数据可视化)
   └─ /api/*         → FastAPI (uvicorn :8000)
                          ↓
              ┌────────────┼────────────────┐
              ↓            ↓                ↓
        SimulationEngine  LLM 五维评估     Admin CRUD
              ↓           + reasoning        ↓
   ┌──────────┼──────────┐                  ↓
   ↓          ↓          ↓             companies_v1.json
CandidateAgent  CompanyHRAgent  InterviewerAgent  competitors_v1.json
   ↓          ↓          ↓
   └──────────┴──────────┘
              ↓
        LLMRouter（tier 路由 + OpenAI 兼容协议）
              ↓
        DeepSeek / Qwen / Kimi / GLM ... 可切换
```

### 关键技术点

| 模块 | 实现 |
|---|---|
| **LLM 抽象层** | tier 路由（PRIMARY/SECONDARY/BACKGROUND），OpenAI 兼容协议适配所有大陆主流模型，切换模型 0 代码改动 |
| **Multi-Agent 沙盘** | 3 类 LLM Agent + 1 规则模拟器：CandidateAgent（求职者分身）/ CompanyHRAgent（注入 hidden_signals）/ InterviewerAgent（分轮考评）/ CompetitorSimulator（200 人竞争者池，纯规则） |
| **反事实分析** | baseline + N 个 mutation 变体，monotonic 单调插值（避免 baseline 接近 100% 时 mutation 反向） |
| **持久化** | JSON 文件 + threading.Lock + 原子写（tempfile → rename），49 公司 + 200 persona 规模够用 |
| **热更新** | admin CRUD endpoints，公司/求职者随时加入退出，下次 sim 启动 snapshot 最新数据 |
| **合规** | sanitizer 双层（prompt 约束 + 落盘前扫描），全部虚构数据 + 代号公司，零 PII |

---

## 设计决策

我们刻意**不**做的事，每个都有理由：

| 不做 | 理由 |
|---|---|
| **不做 LoRA 微调** | 动态市场场景下 LoRA 是反模式——训完就过期，无法跟随公司/求职者池变化。改用 LLM 一次性多任务评估（5 维评分 + 每维理由 + 学校档判定，全部对评委透明可追溯） |
| **不做真公司数据** | 合规 0 风险优先。全代号 + sanitizer 双层 |
| **不做 LangGraph 编排** | 13 周固定 tick 循环不需要"路径不确定的协作"，asyncio + 自研编排更轻 |
| **不做声音克隆** | 与求职决策无关，炫技抢戏 |
| **不堆 buzzword**（区块链/Web3） | 评委一看就识破 |

---

## 跑起来

### 后端

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 配置 LLM key
cp ../.env.example ../.env
# 编辑 .env，至少填一个 provider（DEEPSEEK_API_KEY 等）

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev  # dev server
# 或者 npm run build && nginx 静态托管
```

### 一键 demo 数据生成

```bash
python3 scripts/collect_companies.py    # 生成 49 家虚构公司
python3 scripts/collect_personas.py     # 生成 200 个竞争者 persona
```

---

## 目录结构

```
backend/
├── app/
│   ├── api/             # FastAPI 路由（公开 + admin CRUD）
│   ├── agents/          # 3 类 LLM Agent + 1 规则模拟器
│   ├── simulation/      # 沙盘引擎 + 反事实分析
│   ├── models/          # Pydantic schema（严格对齐答疑文档 Q2）
│   ├── services/        # LLM 抽象层
│   ├── core/            # 配置
│   └── finetune/        # LoRA pipeline（v1 未启用，决赛后扩展用，详见 finetune/README.md）
├── data/                # 种子数据（公司/persona）
└── tests/               # smoke test

frontend/
├── src/
│   ├── views/           # Upload / Profile / Sandbox / Report / Admin / Dashboard
│   ├── components/      # Sandbox3D / 5 个 D3 charts / HRInterview / CounterfactualPanel
│   ├── api/             # 统一 API 入口（mock + real 切换）
│   ├── stores/          # Pinia
│   └── router/          # Vue Router
└── dist/                # build 产物

docs/
├── api_contract.md      # 前后端接口契约
└── submission/          # 比赛提交材料（BP / PPT / 视频脚本）

scripts/                 # 一次性数据生成脚本
```

---

## 合规声明

- 所有公司画像 = 合成数据，代号化（A 厂 / AI-α 等），不挂任何真实公司名
- 所有求职者 = 化名（"张同学"等），零 PII
- sanitizer 双层兜底（prompt 约束 + 落盘前扫描真名）
- 用户上传材料仅 session 内存使用，不入数据库

---

## 比赛信息

| 项 | 值 |
|---|---|
| 主办方 | 智联招聘 |
| 赛事 | 智聘未来·首届全国 AI 创新大赛 |
| 赛道 | AI + 求职 |
| 作品名 | 春招平行宇宙 / Career Multiverse |
| 提交截止 | 2026-06-14 17:00 |

---

## 许可证 / License

**Copyright © 2026 tljcpa. 保留所有权利 / All rights reserved.**

本项目以 **GNU AGPL-3.0** 开源（见 [LICENSE](./LICENSE)），用于开源共享、学习研究与赛事评审：

- 你可以自由查看、运行、修改本代码；
- 但**任何基于本项目的衍生作品——包括通过网络对外提供的服务 / SaaS——都必须同样以 AGPL-3.0 开放其完整源代码。**

> **商业授权（Commercial License）**：若希望在**闭源产品或商业场景**中使用本项目、而不受 AGPL-3.0 开源义务约束，须事先获得作者的**单独商业授权**。请通过本仓库 Issues 或作者主页 [github.com/tljcpa](https://github.com/tljcpa) 联系洽谈。

核心创意、Multi-Agent 模拟引擎、聚合统计与反事实分析等均为作者原创，**git 提交历史完整可追溯**，可作为原创与时间先后的证明。

---

最终解释权归参赛者 + 智联招聘官方。
