import type {
  Company,
  SimRunFile,
  CounterfactualReport,
  UploadResponse,
  SimSessionStartResponse,
  SimSessionStatus,
  HRInterviewRequest,
  HRInterviewResponse,
  OutcomeAggregate,
  MutationDelta
} from '@/types/contracts'

// 直接静态 import：vite 会处理 JSON modules
import companiesRaw from '@/data/companies.json'
import simSmokeRaw from '@/data/sim_smoke.json'
import counterfactualRaw from '@/data/counterfactual.json'

/**
 * Mock 实现策略：
 * 1. 公司池直接用真实 49 家
 * 2. sim_smoke_001 用作单次 sim 模板，复制 + 加入随机扰动模拟 1000 次
 * 3. counterfactual_report 作为反事实基准，前端用插值生成滑动条响应
 *
 * 为什么不真等 backend：
 * - demo 评委不会容忍 5 分钟等待
 * - sim 引擎跑 1000 次需要 LLM 调用，成本和速度都不允许实时
 * - 决赛时我们会换成"预跑 1000 次缓存好结果"的策略
 */

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// 公司池：49 家
export const allCompanies = companiesRaw as unknown as Company[]
const smokeRun = simSmokeRaw as unknown as SimRunFile

// ---------- 候选人上传 ----------
export async function mockUpload(): Promise<UploadResponse> {
  await sleep(800)
  // 注意：真实场景里 resume_summary 由 LLM 抽取，这里 mock 用一个能引发评委共鸣的"算法岗硕士"模板
  return {
    user_id: `user_${Math.random().toString(36).slice(2, 10)}`,
    resume_summary: {
      name: '李明',
      school: 'Top985 计算机硕士',
      major: '计算机科学与技术',
      target_roles: ['算法工程师', '推荐系统', '大模型应用']
    }
  }
}

// ---------- 启动 sim ----------
let _simProgress = 0
let _simStage: SimSessionStatus['stage'] = 'queued'
let _simStartedAt = 0

export async function mockStartSim(): Promise<SimSessionStartResponse> {
  await sleep(300)
  _simProgress = 0
  _simStage = 'queued'
  _simStartedAt = Date.now()
  return {
    sim_session_id: `sim_${Date.now()}`,
    total_runs: 1000,
    estimated_duration_sec: 300
  }
}

// 进度查询：根据 _simStartedAt 推算
// 5 分钟跑完是真实 backend 预期；mock 端为了 demo 流畅，压缩到 12 秒跑完
export async function mockSimStatus(): Promise<SimSessionStatus> {
  await sleep(150)
  const elapsed = (Date.now() - _simStartedAt) / 1000
  // 总动画时长 12 秒。各阶段比例：extract 10% / gen_pairs 15% / lora 40% / sim 35%
  const total = 12
  const p = Math.min(elapsed / total, 1)
  _simProgress = p

  if (p < 0.1) {
    _simStage = 'extracting'
  } else if (p < 0.25) {
    _simStage = 'matching_market'
  } else if (p < 0.65) {
    _simStage = 'sim_running'
  } else if (p < 1) {
    _simStage = 'simulating'
  } else {
    _simStage = 'done'
  }

  const stageMsg: Record<SimSessionStatus['stage'], string> = {
    queued: '排队中...',
    extracting: '校准你的求职画像（学校档 / 经历 / 沟通）',
    matching_market: '扫描 49 家公司招聘门槛，定位你的候选池',
    sim_running: '并行启动 1000 个春招宇宙（49 公司 × 13 周招聘窗 × 蒙特卡洛）',
    simulating: '化身已进场，正在跑 1000 个春招宇宙',
    done: '所有平行宇宙已就绪'
  }

  return {
    sim_session_id: 'mock_sim',
    progress: p,
    stage: _simStage,
    current_run: Math.floor(p * 1000),
    total_runs: 1000,
    message: stageMsg[_simStage]
  }
}

// ---------- 聚合结果 ----------
// 为了让"1000 次平行宇宙"有压倒性视觉效果，mock 这里造一份合理分布
export async function mockAggregate(): Promise<{
  primary_aggregate: OutcomeAggregate
  sample_runs: SimRunFile[]
  offer_count_distribution: Record<string, number>  // 多少次模拟拿了 N 个 offer
  company_offer_probability: Array<{ company_code: string; probability: number }>
  acceptance_week_timeline: Array<{ week: number; count: number }>
}> {
  await sleep(500)

  // offer 数分布：0..8，钟形
  const offerDist: Record<string, number> = {}
  const peak = 2
  let total = 1000
  for (let i = 0; i <= 8; i++) {
    // 简单高斯：mean=2, std=1.5
    const w = Math.exp(-Math.pow(i - peak, 2) / (2 * 1.5 * 1.5))
    offerDist[String(i)] = Math.round(w * 300)
  }
  // 归一到 1000
  const sum = Object.values(offerDist).reduce((a, b) => a + b, 0)
  for (const k of Object.keys(offerDist)) {
    offerDist[k] = Math.round((offerDist[k] / sum) * total)
  }

  // 各公司 offer 概率：从 sim_smoke 的 journey + 全公司池
  // 拿到 offer 的公司给较高概率（30%-70%），其他给 5%-25%
  const offerCompanies = new Set(
    smokeRun.outcome.journeys
      .filter((j) => j.offer_salary_wan > 0)
      .map((j) => j.company_code)
  )
  const companyProb = allCompanies.slice(0, 30).map((c) => {
    if (offerCompanies.has(c.code_name)) {
      return { company_code: c.code_name, probability: 0.3 + Math.random() * 0.4 }
    }
    return { company_code: c.code_name, probability: Math.random() * 0.25 }
  })
  companyProb.sort((a, b) => b.probability - a.probability)

  // 接受 offer 的周次时间线：第 5-16 周
  const weeks: Array<{ week: number; count: number }> = []
  for (let w = 5; w <= 16; w++) {
    // 第 10-12 周高峰
    const c = Math.exp(-Math.pow(w - 11, 2) / 8) * 200
    weeks.push({ week: w, count: Math.round(c) })
  }

  // 最终去向分布：从 journeys + 随机分配
  const destDist: Record<string, number> = {}
  // 拿到 offer 的公司加权
  for (const c of allCompanies.slice(0, 12)) {
    if (offerCompanies.has(c.code_name)) {
      destDist[c.code_name] = 50 + Math.floor(Math.random() * 150)
    } else {
      destDist[c.code_name] = Math.floor(Math.random() * 60)
    }
  }
  // 加 "未签约" 桶
  destDist['未签约'] = 90

  const primary: OutcomeAggregate = {
    label: '原始',
    n_runs: 1000,
    offer_rate: 0.74,
    mean_offers: 2.3,
    mean_applications: 12.5,
    mean_interviews: 4.1,
    mean_salary_when_settled: 48.5,
    median_salary_when_settled: 45.0,
    settled_rate: 0.91,
    destination_distribution: destDist,
    week_settled_distribution: Object.fromEntries(weeks.map((w) => [String(w.week), w.count]))
  }

  // 抽样 5 次 sim 作为决策树展示用
  // mock 端复用 smoke_e2e_001 + 注入少量扰动
  const sample: SimRunFile[] = [smokeRun]

  return {
    primary_aggregate: primary,
    sample_runs: sample,
    offer_count_distribution: offerDist,
    company_offer_probability: companyProb,
    acceptance_week_timeline: weeks
  }
}

// ---------- 反事实 ----------
// 关键 demo 卖点：滑动条要丝滑。
// 实现方式：把 mutation delta 当成线性增益，对 primary aggregate 做插值。
// 不真等 backend，因为评委不会容忍 30 秒等待。
export async function mockCounterfactual(
  mutations: MutationDelta[]
): Promise<CounterfactualReport> {
  await sleep(200)
  const baseReport = counterfactualRaw as unknown as CounterfactualReport

  // 基线参数
  const baseOfferRate = 0.74
  const baseMeanSalary = 48.5
  const baseMeanOffers = 2.3
  const baseSettled = 0.91

  const variants: OutcomeAggregate[] = []

  // 原始变体
  variants.push({
    label: '原始（你的真实简历）',
    n_runs: 1000,
    offer_rate: baseOfferRate,
    mean_offers: baseMeanOffers,
    mean_applications: 12.5,
    mean_interviews: 4.1,
    mean_salary_when_settled: baseMeanSalary,
    median_salary_when_settled: 45.0,
    settled_rate: baseSettled,
    destination_distribution: {},
    week_settled_distribution: {}
  })

  // 每个 mutation 一个变体 + 一个组合变体
  for (const m of mutations) {
    const variant = applyMutation(m, baseOfferRate, baseMeanSalary, baseMeanOffers, baseSettled)
    variants.push(variant)
  }

  // 组合变体（所有 mutation 累加）
  if (mutations.length > 1) {
    let or = baseOfferRate
    let ms = baseMeanSalary
    let mo = baseMeanOffers
    let st = baseSettled
    for (const m of mutations) {
      const v = applyMutation(m, or, ms, mo, st)
      or = v.offer_rate
      ms = v.mean_salary_when_settled
      mo = v.mean_offers
      st = v.settled_rate
    }
    variants.push({
      label: '组合（全部变更同时生效）',
      n_runs: 1000,
      offer_rate: or,
      mean_offers: mo,
      mean_applications: 12.5,
      mean_interviews: 4.1,
      mean_salary_when_settled: ms,
      median_salary_when_settled: ms * 0.92,
      settled_rate: st,
      destination_distribution: {},
      week_settled_distribution: {}
    })
  }

  return {
    primary_candidate_id: baseReport.primary_candidate_id,
    runs_per_variant: 1000,
    variants
  }
}

// 应用单个 mutation 的简化模型
// 真后端会调用 simulation engine，这里用线性插值给出"看起来合理"的曲线
function applyMutation(
  m: MutationDelta,
  baseOfferRate: number,
  baseSalary: number,
  baseOffers: number,
  baseSettled: number
): OutcomeAggregate {
  // 各 mutation 的敏感度（每单位 delta 改变多少）
  const sensitivity: Record<string, { offer: number; salary: number; offers: number; settled: number }> = {
    resume_quality:     { offer: 0.012, salary: 0.6,  offers: 0.04, settled: 0.008 },
    project_strength:   { offer: 0.015, salary: 0.9,  offers: 0.05, settled: 0.009 },
    overwork_tolerance: { offer: 0.003, salary: 0.15, offers: 0.008, settled: 0.005 },
    school_tier:        { offer: 0.08,  salary: 4.0,  offers: 0.25, settled: 0.04 },
    risk_appetite:      { offer: 0.02,  salary: 1.5,  offers: -0.05, settled: -0.01 }
  }
  const s = sensitivity[m.key]
  const clip = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

  return {
    label: m.label,
    n_runs: 1000,
    offer_rate: clip(baseOfferRate + s.offer * m.delta, 0.05, 0.99),
    mean_offers: clip(baseOffers + s.offers * m.delta, 0, 10),
    mean_applications: 12.5,
    mean_interviews: 4.1,
    mean_salary_when_settled: clip(baseSalary + s.salary * m.delta, 15, 120),
    median_salary_when_settled: clip(baseSalary + s.salary * m.delta, 15, 120) * 0.92,
    settled_rate: clip(baseSettled + s.settled * m.delta, 0.1, 0.99),
    destination_distribution: {},
    week_settled_distribution: {}
  }
}

// ---------- HR 采访 ----------
const HR_REPLIES: Record<string, { hr_name: string; replies: string[]; hidden: string }> = {
  default: {
    hr_name: '招聘小助手',
    replies: [
      '我们看重综合素质，希望你能在面试中展现出热情和潜力。',
      '基础扎实是最重要的，简历上的项目我们会逐个深入聊。',
      '我们正处于业务上升期，校招会比较积极。'
    ],
    hidden: '实际权重：本科学校 = 0.18，项目深度 = 0.42'
  }
}

export async function mockHRInterview(req: HRInterviewRequest): Promise<HRInterviewResponse> {
  await sleep(800 + Math.random() * 600)
  const company = allCompanies.find((c) => c.code_name === req.company_code)
  const hrName = company ? `${req.company_code}-招聘 ${pickName()}` : HR_REPLIES.default.hr_name
  const culture = company?.hidden_signals.culture_tags.join('、') ?? '无'
  const bar = company?.hidden_signals.hiring_bar ?? 75

  // 根据问题关键字给定向回复
  let reply = ''
  const q = req.question.toLowerCase()
  if (q.includes('985') || q.includes('学校') || q.includes('学历')) {
    reply = `我们不会唯学校论。${req.company_code} 这边筛选标尺是 ${bar} 分，学校只占其中一部分权重。但说实话，同等条件下我们还是会优先看 Top 院校。`
  } else if (q.includes('加班') || q.includes('996') || q.includes('文化')) {
    reply = `公司文化关键词："${culture}"。我们不强制加班，但项目冲刺期大家会主动留下来。`
  } else if (q.includes('薪资') || q.includes('工资') || q.includes('钱')) {
    reply = `校招薪资按岗位 grade 给，区间在岗位描述里写得很清楚。谈薪的话，看你的项目背景和面试表现，最高可以上浮 20%。`
  } else if (q.includes('35') || q.includes('年龄')) {
    reply = `${req.company_code} 的 35 岁以上员工比例是 ${company?.hidden_signals.pct_over_35 ?? 15}%。我们不卡年龄，看能力。`
  } else {
    reply = `谢谢你的问题。${req.company_code} 这边 ${HR_REPLIES.default.replies[Math.floor(Math.random() * 3)]}`
  }

  return {
    company_code: req.company_code,
    hr_name: hrName,
    reply,
    hidden_signal_revealed: company
      ? `[hidden_signals 揭露] hiring_bar=${bar} / pct_over_35=${company.hidden_signals.pct_over_35}% / 文化=${culture}`
      : undefined
  }
}

function pickName(): string {
  const names = ['Lily', 'Yuna', 'Aaron', 'Sophia', 'Kevin', '小雨', '小慧', '林姐', '陈哥']
  return names[Math.floor(Math.random() * names.length)]
}

// ---------- 公司池 ----------
export async function mockCompanies(): Promise<Company[]> {
  await sleep(100)
  return allCompanies
}
