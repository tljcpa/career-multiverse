"""
LoRA 微调 pipeline 模块。

三个子模块按依赖顺序：
1. data_gen  从用户原始材料（简历文本 / GitHub URL / blog URL）出发，
             调用 LLMRouter（BACKGROUND tier，最便宜）生成 200-500 个
             SFT (instruction, input, output) 训练对，写入
             backend/data/finetune/sft_<user_id>.jsonl
2. train     用 Unsloth + Qwen2.5-7B-Instruct + LoRA 训练，
             输出 adapter 到 backend/data/finetuned/<user_id>/adapter/。
             --mock 模式不真训练，写假 adapter 元信息，CPU 也能跑通。
3. serve     加载 base 模型 + adapter，提供与 LLMRouter.generate 兼容的
             FinetunedPersonaService.chat()，供 simulation 引擎"无感切换"
             到用户分身决策。--mock 模式返回固定回答以验证调用链路。

设计取舍备忘：
- 为什么不放外部 fine-tune 平台（dashscope）：
  我们要把"反事实分析"留在沙盘里，反事实意味着同一模型权重要被反复加载，
  外部平台调用价格 + 隔离都不划算，反不如本地 7B + LoRA。
- 为什么 SFT 而不是 DPO：
  阶段 M3 需要的是"让模型有用户的口吻和价值观"，SFT 已经够；
  DPO 需要偏好对，22 天周期内没空收集。
- 为什么是 Qwen2.5-7B-Instruct：
  中文好、Apache 2.0 友好、Unsloth 官方一档支持、显存友好（A10 24G 够）。
- 训练失败兜底：
  serve.py 加载 adapter 异常时降级到"RAG 风格"——把用户原始材料注入 system prompt，
  让 base 模型扮演用户，避免整个 M3 崩盘连累 M4 sim。
"""
