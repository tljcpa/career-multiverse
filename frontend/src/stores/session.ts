import { defineStore } from 'pinia'
import type { Company, UploadResponse, OutcomeAggregate, MutationDelta } from '@/types/contracts'

/**
 * 会话状态：贯穿 Upload → Profile → Sandbox → Report 全流程
 *
 * 持久化策略：sessionStorage（同标签页关闭即清，F5 / 跳页内保留）。
 * 之前完全 in-memory，评委误触 F5 = 演示崩流（cycle 4 audit 抓出）。
 * 选 sessionStorage 不选 localStorage：每个评委 demo 是新会话，不要跨标签页污染。
 */
const STORAGE_KEY = 'multiverse_session_v1'

function loadFromStorage(): Partial<SessionState> {
  if (typeof sessionStorage === 'undefined') {
    return {}
  }
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return {}
    }
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

function saveToStorage(state: SessionState) {
  if (typeof sessionStorage === 'undefined') {
    return
  }
  try {
    // 只持久化关键身份 + 流程标记字段，不持久化 companies / aggregate（数据大，可重拉）
    const slim = {
      userId: state.userId,
      simSessionId: state.simSessionId,
      hasUploaded: state.hasUploaded,
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch {
    // 静默
  }
}
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
  state: (): SessionState => {
    const stored = loadFromStorage()
    return {
      userId: stored.userId ?? null,
      resumeSummary: null,
      simSessionId: stored.simSessionId ?? null,
      companies: [],
      primaryAggregate: null,
      activeMutations: [],
      hasUploaded: stored.hasUploaded ?? false,
    }
  },
  actions: {
    setUser(payload: UploadResponse) {
      this.userId = payload.user_id
      this.resumeSummary = payload.resume_summary
      this.hasUploaded = true
      saveToStorage(this.$state)
    },
    setSimSession(sessionId: string) {
      this.simSessionId = sessionId
      saveToStorage(this.$state)
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
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem(STORAGE_KEY)
      }
    }
  }
})
