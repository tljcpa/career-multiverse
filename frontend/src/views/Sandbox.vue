<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import Sandbox3D from '@/components/Sandbox3D.vue'
import HRInterview from '@/components/HRInterview.vue'
import { listCompanies } from '@/api'
import { useSessionStore } from '@/stores/session'
import simSmoke from '@/data/sim_smoke.json'
import type { Company, SimRunFile } from '@/types/contracts'

/**
 * 沙盘页：用户旅程第三步，主视觉冲击点。
 *
 * 左侧 3D 沙盘 + 右侧时间轴 + 下方事件流。
 * 时间轴可"播放"——模拟 12 周春招在沙盘上推进，每周向当前周次内的投递目标公司发射粒子。
 *
 * 这是从 sim_smoke 真实事件流驱动的，给评委"真的在跑模拟"的实感。
 */
const router = useRouter()
const session = useSessionStore()

const companies = ref<Company[]>([])
const currentWeek = ref(0)
const isPlaying = ref(false)
const selectedCompany = ref<Company | null>(null)
const hoveredCompany = ref<Company | null>(null)
const appliedCompanies = ref<string[]>([])
const eventLog = ref<Array<{ week: number; text: string; type: string }>>([])
let playTimer = 0

const sim = simSmoke as unknown as SimRunFile

// 总周数
const totalWeeks = 12

// 当前周次的事件（仅 user_primary）
const eventsThisWeek = computed(() => {
  return sim.events.filter(
    (e) => e.candidate_id === 'user_primary' && e.week === currentWeek.value
  )
})

// 用户的 journey 列表（用来展示已投递）
const journeys = sim.outcome.journeys

onMounted(async () => {
  companies.value = await listCompanies()
  session.setCompanies(companies.value)
})

function play() {
  if (isPlaying.value) {
    return
  }
  isPlaying.value = true
  if (currentWeek.value >= totalWeeks) {
    currentWeek.value = 0
    appliedCompanies.value = []
    eventLog.value = []
  }
  playTimer = window.setInterval(() => {
    advanceWeek()
    if (currentWeek.value >= totalWeeks) {
      pause()
    }
  }, 1500)
}

function pause() {
  isPlaying.value = false
  if (playTimer) {
    window.clearInterval(playTimer)
    playTimer = 0
  }
}

function advanceWeek() {
  if (currentWeek.value >= totalWeeks) {
    return
  }
  currentWeek.value++
  // 把这一周 user_primary 投递的公司加入列表（触发粒子动画）
  const newApplies = sim.events
    .filter(
      (e) =>
        e.candidate_id === 'user_primary' &&
        e.week === currentWeek.value &&
        e.event_type === 'application'
    )
    .map((e) => e.company_code)
  for (const code of newApplies) {
    if (!appliedCompanies.value.includes(code)) {
      appliedCompanies.value = [...appliedCompanies.value, code]
    }
  }
  // 累积事件流（最多 15 条，倒序显示最新）
  const weekEvents = sim.events.filter(
    (e) => e.candidate_id === 'user_primary' && e.week === currentWeek.value
  )
  for (const e of weekEvents) {
    eventLog.value.unshift({
      week: e.week,
      type: e.event_type,
      text: formatEvent(e)
    })
  }
  if (eventLog.value.length > 30) {
    eventLog.value = eventLog.value.slice(0, 30)
  }
}

function formatEvent(e: typeof sim.events[0]): string {
  switch (e.event_type) {
    case 'application':
      return `投递 ${e.company_code} · ${e.job_title}`
    case 'screening_pass':
      return `${e.company_code} 简历通过（评分 ${e.score ?? '-'}）`
    case 'screening_fail':
      return `${e.company_code} 简历未通过`
    case 'interview_pass':
      return `${e.company_code} 第 ${e.score ?? '-'} 轮面试通过`
    case 'interview_fail':
      return `${e.company_code} 面试未通过`
    case 'offer':
      return `${e.company_code} 发出 offer`
    case 'accept':
      return `接受 ${e.company_code} 的 offer (最终去向)`
    case 'reject_offer':
      return `拒绝 ${e.company_code} 的 offer`
    default:
      return `${e.company_code} · ${e.event_type}`
  }
}

function eventColor(type: string): string {
  if (type === 'application') {
    return 'text-cyber-cyan'
  }
  if (type === 'screening_pass' || type === 'interview_pass') {
    return 'text-cyber-gold'
  }
  if (type === 'offer' || type === 'accept') {
    return 'text-cyber-purple'
  }
  if (type.includes('fail') || type === 'reject_offer') {
    return 'text-cyber-pink'
  }
  return 'text-ink-300'
}

function goToReport() {
  router.push('/report')
}

function onCompanyClick(c: Company) {
  selectedCompany.value = c
}
</script>

<template>
  <main class="w-full h-screen pt-16 flex relative overflow-hidden">
    <!-- 3D 沙盘容器（占主体） -->
    <div class="flex-1 relative">
      <Sandbox3D
        v-if="companies.length > 0"
        :companies="companies"
        :current-week="currentWeek"
        :applied-companies="appliedCompanies"
        @company-click="onCompanyClick"
        @company-hover="hoveredCompany = $event"
      />

      <!-- 加载占位 -->
      <div v-else class="absolute inset-0 flex items-center justify-center text-cyber-cyan">
        正在装配 49 家虚拟公司...
      </div>

      <!-- 顶部时间标尺 -->
      <div class="absolute top-4 left-1/2 -translate-x-1/2 panel-glass px-6 py-3 flex items-center gap-4">
        <span class="text-xs text-ink-500">春招进程</span>
        <div class="flex items-center gap-1">
          <div
            v-for="w in totalWeeks"
            :key="w"
            class="w-3 h-1.5 rounded-full transition-all"
            :class="w <= currentWeek ? 'bg-cyber-cyan' : 'bg-white/10'"
          />
        </div>
        <span class="text-cyber-cyan font-mono text-sm">第 {{ currentWeek }} / {{ totalWeeks }} 周</span>
      </div>

      <!-- Hover tooltip -->
      <div
        v-if="hoveredCompany"
        class="absolute bottom-32 left-6 panel-glass px-4 py-3 max-w-xs pointer-events-none"
      >
        <div class="text-sm font-semibold text-ink-100">{{ hoveredCompany.code_name }}</div>
        <div class="text-xs text-cyber-cyan mt-1">{{ hoveredCompany.industry }}</div>
        <div class="text-xs text-ink-500 mt-1">
          标尺 {{ hoveredCompany.hidden_signals.hiring_bar }} ·
          {{ hoveredCompany.size_label.split('（')[0] }}
        </div>
        <div class="text-xs text-cyber-gold mt-1">点击采访 HR →</div>
      </div>

      <!-- 控制条 -->
      <div class="absolute bottom-6 left-1/2 -translate-x-1/2 panel-glass px-6 py-4 flex items-center gap-4">
        <button
          v-if="!isPlaying"
          class="w-12 h-12 rounded-full bg-cyber-cyan text-black font-bold flex items-center justify-center hover:scale-110 transition"
          @click="play"
        >▶</button>
        <button
          v-else
          class="w-12 h-12 rounded-full bg-cyber-pink text-black font-bold flex items-center justify-center hover:scale-110 transition"
          @click="pause"
        >||</button>
        <button class="btn-ghost text-xs" @click="advanceWeek" :disabled="isPlaying">单步推进 →</button>
        <div class="text-xs text-ink-500 mx-2">
          {{ appliedCompanies.length }} 次投递 · {{ eventsThisWeek.length }} 个本周事件
        </div>
        <button class="btn-primary text-sm" @click="goToReport">
          查看 1000 次平行宇宙报告 →
        </button>
      </div>
    </div>

    <!-- 右侧事件流 -->
    <aside class="w-96 border-l border-white/5 bg-space-bg/70 backdrop-blur p-5 overflow-y-auto">
      <div class="mb-4">
        <h3 class="text-lg font-semibold text-ink-100">实时事件流</h3>
        <p class="text-xs text-ink-500 mt-1">化身在沙盘中的每一步</p>
      </div>

      <!-- 累计 stats -->
      <div class="grid grid-cols-3 gap-2 mb-5">
        <div class="panel-glass p-3 text-center">
          <div class="text-xs text-ink-500">投递</div>
          <div class="text-2xl font-mono text-cyber-cyan">{{ appliedCompanies.length }}</div>
        </div>
        <div class="panel-glass p-3 text-center">
          <div class="text-xs text-ink-500">面试</div>
          <div class="text-2xl font-mono text-cyber-purple">
            {{ eventLog.filter((e) => e.type === 'screening_pass' || e.type === 'interview_pass').length }}
          </div>
        </div>
        <div class="panel-glass p-3 text-center">
          <div class="text-xs text-ink-500">Offer</div>
          <div class="text-2xl font-mono text-cyber-gold">
            {{ eventLog.filter((e) => e.type === 'offer' || e.type === 'accept').length }}
          </div>
        </div>
      </div>

      <div class="space-y-2 text-sm">
        <div
          v-for="(e, i) in eventLog"
          :key="i"
          class="panel-glass p-3 transition-all"
        >
          <div class="flex items-center gap-2 text-xs text-ink-500">
            <span class="font-mono">W{{ e.week }}</span>
            <span :class="eventColor(e.type)" class="font-semibold uppercase tracking-wider text-[10px]">
              {{ e.type }}
            </span>
          </div>
          <div :class="eventColor(e.type)" class="mt-1">{{ e.text }}</div>
        </div>
        <div v-if="eventLog.length === 0" class="text-ink-500 text-xs text-center py-10">
          点击"播放"按钮，观察化身在沙盘中的春招轨迹
        </div>
      </div>

      <!-- 已投递公司 -->
      <div v-if="journeys.length > 0 && currentWeek >= totalWeeks" class="mt-6">
        <h4 class="text-sm font-semibold text-ink-100 mb-2">这一次的最终落点</h4>
        <div class="panel-glass p-4">
          <div class="text-xs text-ink-500">最终去向</div>
          <div class="text-xl font-bold text-cyber-gold mt-1">
            {{ sim.outcome.final_destination_company }}
          </div>
          <div class="text-xs text-ink-300 mt-1">{{ sim.outcome.final_destination_role }}</div>
          <div class="text-xs text-ink-500 mt-2">
            薪资 <span class="text-cyber-cyan font-mono">{{ sim.outcome.final_salary_wan }} 万</span> ·
            第 {{ sim.outcome.final_week_when_settled }} 周确定
          </div>
        </div>
      </div>
    </aside>

    <!-- HR 采访弹层 -->
    <HRInterview
      v-if="selectedCompany"
      :company="selectedCompany"
      @close="selectedCompany = null"
    />
  </main>
</template>
