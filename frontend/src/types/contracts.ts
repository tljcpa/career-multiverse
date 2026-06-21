/**
 * 前后端契约类型定义
 *
 * 这些类型对应 docs/api_contract.md 的接口定义。
 * 字段命名与 backend/app/simulation 的 dataclass 保持一致（snake_case），
 * 这样 mock 数据可以直接复用 backend/data/sim_runs 下的真实 JSON。
 */

// ---------- 公司池 ----------
export interface CompanyHiddenSignals {
  hiring_bar: number
  hiring_style: string
  culture_tags: string[]
  business_growth: number
  pct_over_35: number
  hidden_filters: string[]
}

export interface CompanyJobPosting {
  job_title: string
  job_category: string
  salary: string
  years_required: string
  degree_required: string
  city_required: string
  keywords: string[]
  description: string
  company_name: string
  work_address: string
  publish_date: string
}

export interface Company {
  code_name: string
  inspired_by_hint: string
  industry: string
  size_label: string
  headquarters_city: string
  job_postings: CompanyJobPosting[]
  hidden_signals: CompanyHiddenSignals
}

// ---------- 候选人画像（profile 页用） ----------
export interface CompositeBreakdown {
  base_avg: number
  school_bonus: number
  school_tier_label: string
  degree_bonus: number
  degree_label: string
  comm_adjust: number
  raw_total: number
  final: number
}

export interface CandidateSignalsBrief {
  school_tier: string
  school_tier_label: string
  gpa_percentile: number
  project_strength: number
  internship_strength: number
  achievements_strength: number
  communication_score: number
  composite_score: number
  composite_breakdown: CompositeBreakdown
}

export interface CompanyMatchItem {
  code_name: string
  industry: string
  hiring_bar: number
  gap: number
  label: '挑战' | '够格' | '保底' | '顶尖优选'
}

export interface CandidateProfileResponse {
  user_id: string
  resume_summary: {
    name: string
    school: string
    major: string
    target_roles: string[]
  }
  signals: CandidateSignalsBrief
  top_companies: CompanyMatchItem[]
  market_summary: string
  reasoning: Record<string, string>
}

// ---------- LLM 个性化建议（Report 页关键结论用） ----------
export interface CoachingResponse {
  summary: string
  advices: string[]
  biggest_gap: string
  top_strength: string
}

// ---------- Sim 输出（与 SimOutcome 对齐） ----------
export interface Journey {
  company_code: string
  job_title: string
  final_stage: 'applied' | 'screened_in' | 'interviewing' | 'offered' | 'accepted' | 'rejected' | 'withdrawn'
  applied_week: number
  final_round: number
  interview_scores: number[]
  offer_salary_wan: number
  is_final_destination: boolean
}

export interface SimEvent {
  event_type: string
  week: number
  candidate_id: string
  company_code: string
  job_title?: string
  motivation?: string
  reasoning?: string
  score?: number
}

export interface SimOutcome {
  sim_id: string
  counterfactual_diff: string
  total_applications: number
  total_interviews: number
  total_offers: number
  final_destination_company: string
  final_destination_role: string
  final_salary_wan: number
  final_week_when_settled: number
  journeys: Journey[]
}

export interface SimRunFile {
  sim_id: string
  outcome: SimOutcome
  events: SimEvent[]
}

// ---------- 聚合统计 ----------
export interface OutcomeAggregate {
  label: string
  n_runs: number
  offer_rate: number
  mean_offers: number
  mean_applications: number
  mean_interviews: number
  mean_salary_when_settled: number
  median_salary_when_settled: number
  settled_rate: number
  destination_distribution: Record<string, number>
  week_settled_distribution: Record<string, number>
}

export interface CounterfactualReport {
  primary_candidate_id: string
  runs_per_variant: number
  variants: OutcomeAggregate[]
}

// ---------- Mutation 维度（反事实滑动条用） ----------
export type MutationKey =
  | 'resume_quality'
  | 'project_strength'
  | 'overwork_tolerance'
  | 'school_tier'
  | 'risk_appetite'

export interface MutationDelta {
  key: MutationKey
  delta: number
  label: string
}

// ---------- 上传 / Session ----------
export interface UploadResponse {
  user_id: string
  resume_summary: {
    name: string
    school: string
    major: string
    target_roles: string[]
  }
}

export interface SimSessionStartResponse {
  sim_session_id: string
  total_runs: number
  estimated_duration_sec: number
}

export interface SimSessionStatus {
  sim_session_id: string
  progress: number   // 0..1
  stage: 'queued' | 'extracting' | 'matching_market' | 'sim_running' | 'simulating' | 'done'
  current_run: number
  total_runs: number
  message: string
}

// ---------- HR 采访 ----------
export interface HRInterviewRequest {
  company_code: string
  user_id: string
  question: string
}

export interface HRInterviewResponse {
  company_code: string
  hr_name: string
  reply: string
  hidden_signal_revealed?: string
}
