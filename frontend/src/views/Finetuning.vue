<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { startSimulation, getSimulationStatus } from '@/api'
import { useSessionStore } from '@/stores/session'
import type { SimSessionStatus } from '@/types/contracts'

/**
 * 微调进度页：用户旅程第二步。
 *
 * 视觉冲击点：
 * 1. 中央 LoRA 训练动画（伪 loss 曲线 + 旋转的 weight matrix）
 * 2. 阶段切换流畅，每个阶段给"评委能瞬间 get"的一句话解释
 * 3. 完成后 1.5 秒自动跳转，不让评委等
 */
const router = useRouter()
const session = useSessionStore()

const status = ref<SimSessionStatus | null>(null)
const errorMsg = ref('')
let pollTimer = 0
let lossPoints = ref<number[]>([])
let lossTimer = 0

const stages: Array<{ key: SimSessionStatus['stage']; title: string; detail: string }> = [
  {
    key: 'extracting',
    title: '抽取个人信息',
    detail: '从你的简历 / GitHub / 博客中抽取关键信号：学校、专业、项目、实习、技能栈'
  },
  {
    key: 'generating_pairs',
    title: '生成训练数据 200 对',
    detail: '为 LoRA 微调生成"你会怎么回答 HR"的样本对（拒 offer、谈薪、问加班等）'
  },
  {
    key: 'lora_training',
    title: 'LoRA 微调中',
    detail: 'rank=16, 2 epochs，让基座模型有你的"语气"。这一步是数字分身的灵魂'
  },
  {
    key: 'simulating',
    title: '化身就位 · 模拟 1000 个宇宙',
    detail: '49 家公司 × 12 周招聘窗 × 1000 次蒙特卡洛。每次的随机性来自 HR 的主观偏好'
  }
]

const currentStageIndex = computed(() => {
  if (!status.value) {
    return 0
  }
  return stages.findIndex((s) => s.key === status.value!.stage)
})

const progressPct = computed(() => Math.round((status.value?.progress ?? 0) * 100))

async function bootstrap() {
  // 如果没有 user_id（直接跳转过来），创建一个 mock user
  if (!session.userId) {
    session.setUser({
      user_id: `user_demo_${Date.now()}`,
      resume_summary: {
        name: '李明',
        school: 'Top985 计算机硕士',
        major: '计算机科学与技术',
        target_roles: ['算法工程师', '推荐系统']
      }
    })
  }
  try {
    const resp = await startSimulation(session.userId!, 1000)
    session.setSimSession(resp.sim_session_id)
    pollTimer = window.setInterval(poll, 400)
    // 启动伪 loss 曲线
    startLossCurve()
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : '启动失败'
  }
}

async function poll() {
  if (!session.simSessionId) {
    return
  }
  try {
    const s = await getSimulationStatus(session.simSessionId)
    status.value = s
    if (s.stage === 'done') {
      window.clearInterval(pollTimer)
      // 完成后停留 1.5s 让评委看到 100%
      setTimeout(() => {
        router.push('/sandbox')
      }, 1500)
    }
  } catch {
    // 静默吞掉单次 poll 错误
  }
}

// 伪 loss 曲线：在 lora_training 阶段生成下降数据
function startLossCurve() {
  let step = 0
  lossTimer = window.setInterval(() => {
    if (!status.value || status.value.stage !== 'lora_training') {
      return
    }
    // loss 从 2.5 衰减到 0.4
    const base = 0.4 + 2.1 * Math.exp(-step / 25)
    const noise = (Math.random() - 0.5) * 0.15
    lossPoints.value.push(Math.max(0.3, base + noise))
    if (lossPoints.value.length > 60) {
      lossPoints.value.shift()
    }
    step++
  }, 200)
}

// 简单 SVG path：把 loss 数组转成 polyline points
const lossPath = computed(() => {
  if (lossPoints.value.length < 2) {
    return ''
  }
  const w = 300
  const h = 80
  const max = Math.max(...lossPoints.value)
  const min = Math.min(...lossPoints.value)
  const range = max - min || 1
  return lossPoints.value
    .map((v, i) => {
      const x = (i / (lossPoints.value.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

onMounted(() => {
  bootstrap()
})

onBeforeUnmount(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
  }
  if (lossTimer) {
    window.clearInterval(lossTimer)
  }
})
</script>

<template>
  <main class="w-full min-h-screen flex items-center justify-center px-6 pt-20 pb-12">
    <div class="w-full max-w-4xl">
      <!-- 顶部 -->
      <div class="text-center mb-8">
        <h2 class="text-4xl font-bold title-gradient mb-3">AI 正在变成你</h2>
        <p class="text-ink-300 text-base">
          我们用你的资料训练一个 LoRA 适配器，让基座模型在面试场景下"像你一样思考"
        </p>
      </div>

      <!-- 主进度卡片 -->
      <div class="panel-glass p-8">
        <!-- 顶部状态 -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <div class="text-cyber-cyan text-xs tracking-widest mb-1">CURRENT STAGE</div>
            <div class="text-2xl font-semibold text-ink-100">
              {{ stages[Math.max(0, currentStageIndex)]?.title ?? '初始化中' }}
            </div>
          </div>
          <div class="text-right">
            <div class="text-cyber-cyan text-5xl font-mono font-bold animate-flicker">
              {{ progressPct }}<span class="text-2xl">%</span>
            </div>
            <div class="text-xs text-ink-500">{{ status?.current_run ?? 0 }} / 1000</div>
          </div>
        </div>

        <!-- 进度条 -->
        <div class="h-2 bg-space-deep rounded-full overflow-hidden mb-8">
          <div
            class="h-full bg-gradient-to-r from-cyber-cyan via-cyber-purple to-cyber-pink transition-all duration-300"
            :style="{ width: progressPct + '%' }"
          />
        </div>

        <!-- 阶段列表 -->
        <div class="space-y-3">
          <div
            v-for="(s, i) in stages"
            :key="s.key"
            class="flex items-start gap-4 p-4 rounded transition-all"
            :class="[
              i < currentStageIndex
                ? 'bg-space-deep/40 opacity-60'
                : i === currentStageIndex
                  ? 'bg-cyber-cyan/5 border border-cyber-cyan/30'
                  : 'opacity-30'
            ]"
          >
            <div
              class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-mono flex-shrink-0"
              :class="[
                i < currentStageIndex
                  ? 'bg-cyber-cyan text-black'
                  : i === currentStageIndex
                    ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan animate-pulse'
                    : 'bg-white/5 text-ink-500'
              ]"
            >
              <span v-if="i < currentStageIndex" class="checkmark-inline"></span>
              <span v-else>{{ i + 1 }}</span>
            </div>
            <div class="flex-1">
              <div class="text-sm font-semibold text-ink-100">{{ s.title }}</div>
              <div class="text-xs text-ink-300 mt-1">{{ s.detail }}</div>
              <!-- LoRA 阶段专属：loss 曲线 -->
              <div
                v-if="s.key === 'lora_training' && i === currentStageIndex"
                class="mt-3 panel-glass p-3"
              >
                <div class="flex items-center justify-between text-xs text-ink-500 mb-2">
                  <span>training loss</span>
                  <span class="text-cyber-cyan font-mono">
                    {{ lossPoints[lossPoints.length - 1]?.toFixed(3) ?? '—' }}
                  </span>
                </div>
                <svg viewBox="0 0 300 80" class="w-full h-20">
                  <!-- lossPoints < 2 时 lossPath 为空，整个 SVG path 都不渲染避免 'L...' 缺 M 报错 -->
                  <template v-if="lossPath">
                    <path :d="lossPath" stroke="#00e5ff" stroke-width="1.5" fill="none" />
                    <path
                      :d="lossPath + ` L300,80 L0,80 Z`"
                      fill="url(#lossGrad)"
                      opacity="0.3"
                    />
                  </template>
                  <defs>
                    <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#00e5ff" stop-opacity="0.5" />
                      <stop offset="100%" stop-color="#00e5ff" stop-opacity="0" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>
          </div>
        </div>

        <!-- Status footer -->
        <div class="mt-6 text-center text-xs text-ink-500">
          {{ status?.message ?? '正在初始化训练管道...' }}
        </div>

        <div v-if="errorMsg" class="mt-4 text-sm text-cyber-pink text-center">
          {{ errorMsg }}
        </div>
      </div>
    </div>
  </main>
</template>
