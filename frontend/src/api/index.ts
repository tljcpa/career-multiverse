import { USE_MOCK, httpClient } from './client'
import * as mock from './mock'
import type {
  Company,
  CounterfactualReport,
  UploadResponse,
  SimSessionStartResponse,
  SimSessionStatus,
  HRInterviewRequest,
  HRInterviewResponse,
  MutationDelta
} from '@/types/contracts'

/**
 * API 统一入口。
 *
 * 用 USE_MOCK 切换分支：M4 阶段全走 mock，M5 集成时切到真接口。
 * 调用层（store / view）只 import 这个 index，看不到 mock 实现细节。
 */

export async function uploadCandidate(form: FormData): Promise<UploadResponse> {
  if (USE_MOCK) {
    return mock.mockUpload()
  }
  const { data } = await httpClient.post<UploadResponse>('/candidate/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return data
}

export async function startSimulation(userId: string, nRuns = 1000): Promise<SimSessionStartResponse> {
  if (USE_MOCK) {
    return mock.mockStartSim()
  }
  const { data } = await httpClient.post<SimSessionStartResponse>('/simulation/start', {
    user_id: userId,
    n_runs: nRuns
  })
  return data
}

export async function getSimulationStatus(sessionId: string): Promise<SimSessionStatus> {
  if (USE_MOCK) {
    return mock.mockSimStatus()
  }
  const { data } = await httpClient.get<SimSessionStatus>(`/simulation/status/${sessionId}`)
  return data
}

export async function getAggregate(sessionId: string) {
  if (USE_MOCK) {
    return mock.mockAggregate()
  }
  const { data } = await httpClient.get(`/simulation/aggregate/${sessionId}`)
  return data
}

export async function runCounterfactual(
  sessionId: string,
  mutations: MutationDelta[]
): Promise<CounterfactualReport> {
  if (USE_MOCK) {
    return mock.mockCounterfactual(mutations)
  }
  const { data } = await httpClient.post<CounterfactualReport>('/counterfactual/run', {
    sim_session_id: sessionId,
    mutations,
    runs_per_variant: 200
  })
  return data
}

export async function interviewHR(req: HRInterviewRequest): Promise<HRInterviewResponse> {
  if (USE_MOCK) {
    return mock.mockHRInterview(req)
  }
  const { data } = await httpClient.post<HRInterviewResponse>('/hr/interview', req)
  return data
}

export async function listCompanies(): Promise<Company[]> {
  if (USE_MOCK) {
    return mock.mockCompanies()
  }
  const { data } = await httpClient.get<Company[]>('/companies')
  return data
}

// ============ Admin CRUD ============
// 注：admin endpoints 都要 X-Admin-Token header（在 client 拦截器里注入）

const ADMIN_TOKEN = (import.meta.env.VITE_ADMIN_TOKEN as string) || 'multiverse-demo-2026'
const adminHeaders = { 'X-Admin-Token': ADMIN_TOKEN }

export async function adminListCompanies(): Promise<Company[]> {
  const { data } = await httpClient.get<Company[]>('/admin/companies', { headers: adminHeaders })
  return data
}

export async function adminAddCompany(payload: Company): Promise<{ status: string; total: number }> {
  const { data } = await httpClient.post('/admin/companies', payload, { headers: adminHeaders })
  return data
}

export async function adminDeleteCompany(codeName: string): Promise<{ remaining: number }> {
  const { data } = await httpClient.delete(`/admin/companies/${encodeURIComponent(codeName)}`, {
    headers: adminHeaders
  })
  return data
}

export async function adminListPersonas(): Promise<Array<Record<string, unknown>>> {
  const { data } = await httpClient.get<Array<Record<string, unknown>>>('/admin/personas', {
    headers: adminHeaders
  })
  return data
}

export async function adminAddPersona(payload: Record<string, unknown>): Promise<{ status: string; total: number }> {
  const { data } = await httpClient.post('/admin/personas', payload, { headers: adminHeaders })
  return data
}

export async function adminDeletePersona(candidateId: string): Promise<{ remaining: number }> {
  const { data } = await httpClient.delete(`/admin/personas/${encodeURIComponent(candidateId)}`, {
    headers: adminHeaders
  })
  return data
}
