# finetune/ —— LoRA 训练代码（v1 未启用）

本目录包含 Qwen2.5-7B + LoRA r=16 的完整训练 pipeline（data_gen.py / train.py / serve.py）。

**v1 演示版本未启用**。原因：

1. **动态市场不适配 LoRA**：沙盘里 49 家公司 + 200 名竞争者可被评委通过 admin CRUD 实时增删，每次扰动都失效一个针对静态市场训练的 LoRA。
2. **简历内容不足以喂训练数据**：单份简历切片成 200 对训练样本，对 LLM 拟人化贡献边际，远不如 RAG / LLM 一次性多任务评估（当前 v1 方案）有效。
3. **22 天时间窗**：决赛后再做 LoRA 路线（含 reward model 与 PPO 后训），让分身真正"用自己的语气"决策。

v1 演示走的是 **LLM 一次性多任务评估**：把简历喂给 LLM 同时输出
- 基本字段（姓名 / 学校 / 专业 / 目标岗位）
- 5 维内部画像评分（项目 / 实习 / 成就 / 沟通 / GPA 分位）
- 每维评分理由（透明可追溯，评委可点击展开看）
- 学校档判定（top / 985_top / 985 / 211 / double_non / lower / overseas_*）

详见 backend/app/api/routes.py 的 `_extract_resume_summary` + `_bootstrap_candidate_from_summary`。

—— 决赛阶段如需展示 LoRA 训练 demo，跑 `python -m app.finetune.train --mock` 即可。
