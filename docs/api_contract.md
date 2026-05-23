# 春招平行宇宙 · 前后端 API Contract

> 版本：v1（M4 起草，M5 实现）
> 所有路径基于 `VITE_API_BASE`（默认 `/api`）
> 字段命名：snake_case（与 backend dataclass 一致）

## 0. 协议约定

- 全部 JSON over HTTP
- 错误格式：`{ "detail": "<error message>" }` HTTP 4xx/5xx
- 时间字段：ISO8601，UTC
- 金额字段：单位"万元"，类型 number（保留 1 位小数）

---

## 1. 候选人上传

### `POST /api/candidate/upload`

multipart/form-data：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| resume_file | File | 是 | PDF 或 Markdown，<= 5MB |
| github_url | string | 否 | https://github.com/xxx |
| blog_url | string | 否 | 个人博客 |
| extra_links | string[] | 否 | 任意附加链接 |

**响应**：

```json
{
  "user_id": "user_abc123",
  "resume_summary": {
    "name": "李明",
    "school": "Top985 硕士",
    "major": "计算机",
    "target_roles": ["算法工程师", "推荐系统"]
  }
}
```

---

## 2. 启动 1000 次模拟

### `POST /api/simulation/start`

```json
{
  "user_id": "user_abc123",
  "n_runs": 1000,
  "seed": 42
}
```

**响应**：

```json
{
  "sim_session_id": "sim_xyz789",
  "total_runs": 1000,
  "estimated_duration_sec": 300
}
```

---

## 3. 模拟进度查询

### `GET /api/simulation/status/{sim_session_id}`

**响应**：

```json
{
  "sim_session_id": "sim_xyz789",
  "progress": 0.42,
  "stage": "simulating",
  "current_run": 420,
  "total_runs": 1000,
  "message": "正在模拟第 420 个宇宙..."
}
```

stage 取值：`queued | extracting | generating_pairs | lora_training | simulating | done`

---

## 4. 聚合结果

### `GET /api/simulation/aggregate/{sim_session_id}`

**响应**：

```json
{
  "sim_session_id": "sim_xyz789",
  "primary_aggregate": {
    "label": "原始",
    "n_runs": 1000,
    "offer_rate": 0.74,
    "mean_offers": 2.3,
    "mean_applications": 12.5,
    "mean_interviews": 4.1,
    "mean_salary_when_settled": 48.5,
    "median_salary_when_settled": 45.0,
    "settled_rate": 0.91,
    "destination_distribution": { "焰火": 230, "深原": 187, "...": 0 },
    "week_settled_distribution": { "8": 50, "10": 200, "12": 350 }
  },
  "sample_runs": [ /* SimRunFile[] 抽样 5 次 */ ]
}
```

---

## 5. 反事实运行

### `POST /api/counterfactual/run`

```json
{
  "sim_session_id": "sim_xyz789",
  "mutations": [
    { "key": "resume_quality", "delta": 10, "label": "简历质量 +10" },
    { "key": "project_strength", "delta": 15, "label": "项目含金量 +15" }
  ],
  "runs_per_variant": 200
}
```

mutation key 取值：
- `resume_quality` (-30..+30)
- `project_strength` (-30..+30)
- `overwork_tolerance` (0..100)
- `school_tier` (-2..+2)
- `risk_appetite` (-1..+1)

**响应**：CounterfactualReport（见 contracts.ts）

---

## 6. HR 采访

### `POST /api/hr/interview`

```json
{
  "company_code": "焰火",
  "user_id": "user_abc123",
  "question": "你们的 985 偏好真实存在吗？"
}
```

**响应**：

```json
{
  "company_code": "焰火",
  "hr_name": "焰火-招聘 Lily",
  "reply": "我们看重项目含金量，985 标签只是参考，不是硬门槛。",
  "hidden_signal_revealed": "实际权重：985 = 0.15"
}
```

---

## 7. 公司池

### `GET /api/companies`

**响应**：`Company[]`（见 contracts.ts）

---

## Mock 实现说明

当前 M4 阶段：

- `frontend/src/api/mock.ts` 用 `setTimeout` 模拟网络延迟
- 数据来源：`frontend/src/data/{companies.json, sim_smoke.json, counterfactual.json}`，复制自 `backend/data/`
- 通过 `VITE_USE_MOCK=true` 切换

M5 集成时：

- 切 `VITE_USE_MOCK=false`
- backend 实现以上 7 个端点
- mock.ts 保留作为离线 demo fallback
