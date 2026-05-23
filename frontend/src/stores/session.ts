import { defineStore } from 'pinia'
import type { Company, UploadResponse, OutcomeAggregate, MutationDelta } from '@/types/contracts'

/**
 * 会话状态：贯穿 Upload → Finetuning → Sandbox → Report 全流程
 *
 * 设计哲学：不持久化到 localStorage。
 * 理由：每次 demo 都是全新一遍跑通；持久化反而会让 dev 阶段干扰频出。
 */
interface SessionState {
  userId: string | null
  resumeSummary: UploadResponse['resume_summary'] | null
  simSessionId: string | null
  companies: Company[]
  primaryAggregate: OutcomeAggregate | null
  // 反事实当前激活的 mutations
  activeMutations: MutationDelta[]
  // mock fallback：是否已上传过简历（路由守卫用，简化处理）
  hasUploaded: boolean
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    userId: null,
    resumeSummary: null,
    simSessionId: null,
    companies: [],
    primaryAggregate: null,
    activeMutations: [],
    hasUploaded: false
  }),
  actions: {
    setUser(payload: UploadResponse) {
      this.userId = payload.user_id
      this.resumeSummary = payload.resume_summary
      this.hasUploaded = true
    },
    setSimSession(sessionId: string) {
      this.simSessionId = sessionId
    },
    setCompanies(companies: Company[]) {
      this.companies = companies
    },
    setAggregate(agg: OutcomeAggregate) {
      this.primaryAggregate = agg
    },
    setMutations(m: MutationDelta[]) {
      this.activeMutations = m
    },
    reset() {
      this.userId = null
      this.resumeSummary = null
      this.simSessionId = null
      this.companies = []
      this.primaryAggregate = null
      this.activeMutations = []
      this.hasUploaded = false
    }
  }
})
