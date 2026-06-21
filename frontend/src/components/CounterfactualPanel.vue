<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { runCounterfactual } from '@/api'
import { useSessionStore } from '@/stores/session'
import type { CounterfactualReport, MutationDelta, MutationKey } from '@/types/contracts'

const session = useSessionStore()

/**
 * 反事实滑动条面板（关键 demo 卖点）。
 *
 * 设计：三个滑动条 → 实时调用 mock counterfactual → 显示对比卡片
 * "实时"通过 debounce 实现（150ms 节流），mock 端响应只用 200ms，体验丝滑
 */
interface SliderConfig {
  key: MutationKey
  title: string
  desc: string
  min: number
  max: number
  step: number
  default: number
  unit: string
}

// 反事实分值口径：
// resume_quality / project_strength 是化身的 0-100 内部评分（baseline 由你的资料抽取 + 校准得到），
// 滑动条 delta 直接加减该评分（如 baseline 65，+15 = 假设你打磨到 80 分时的结果）。
// school_tier 是离散档位 {-2..+2} = {四非, 一本/双一流, 211, 985, 985 top}。
// 薪资单位全部为「年薪万元」。
const sliders: SliderConfig[] = [
  {
    key: 'resume_quality',
    title: '简历质量（0-100 内部评分）',
    desc: '排版、措辞、关键词命中率。baseline 由 LLM 简历评估自动校准',
    min: -20, max: 30, step: 1, default: 0, unit: ' 分'
  },
  {
    key: 'project_strength',
    title: '项目含金量（0-100 内部评分）',
    desc: '项目深度、复杂度、面试官能挖掘的细节',
    min: -20, max: 30, step: 1, default: 0, unit: ' 分'
  },
  {
    key: 'school_tier',
    title: '学校等级（档位）',
    desc: '档位变化：-2=降到四非, -1=一本/双一流, 0=不变, +1=211, +2=985',
    min: -2, max: 2, step: 1, default: 0, unit: ' 档'
  }
]

const values = ref<Record<string, number>>(
  Object.fromEntries(sliders.map((s) => [s.key, s.default]))
)

const report = ref<CounterfactualReport | null>(null)
const loading = ref(false)
let debounceTimer = 0

const mutations = computed<MutationDelta[]>(() => {
  return sliders
    .filter((s) => values.value[s.key] !== 0)
    .map((s) => ({
      key: s.key,
      delta: values.value[s.key],
      label: `${s.title} ${values.value[s.key] > 0 ? '+' : ''}${values.value[s.key]}${s.unit}`
    }))
})

async function fetchReport() {
  // 空 mutations 不调 backend：所有 slider 都在 0 时调用没意义，且 backend min_length=1 会 422
  if (mutations.value.length === 0) {
    return
  }
  loading.value = true
  try {
    report.value = await runCounterfactual(session.simSessionId ?? 'mock_sim', mutations.value)
  } finally {
    loading.value = false
  }
}

watch(mutations, () => {
  if (debounceTimer) {
    window.clearTimeout(debounceTimer)
  }
  debounceTimer = window.setTimeout(fetchReport, 150)
}, { deep: true, immediate: true })

function resetSliders() {
  for (const s of sliders) {
    values.value[s.key] = s.default
  }
}

function deltaColor(delta: number): string {
  if (delta > 0.05) {
    return 'text-cyber-cyan'
  }
  if (delta < -0.05) {
    return 'text-cyber-pink'
  }
  return 'text-ink-300'
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

// 当前选中的对比变体（默认显示组合）
const baseVariant = computed(() => report.value?.variants[0])
const compareVariant = computed(() => {
  const v = report.value?.variants ?? []
  if (v.length === 0) {
    return null
  }
  return v[v.length - 1]
})
</script>

<template>
  <div class="panel-glass p-6">
    <div class="flex items-start justify-between mb-5">
      <div>
        <h3 class="text-lg font-bold title-gradient">反事实分析</h3>
        <p class="text-xs text-ink-500 mt-1">
          如果你的简历不一样，1000 个平行宇宙会怎么变？
        </p>
      </div>
      <button class="btn-ghost text-xs" @click="resetSliders">重置</button>
    </div>

    <!-- 滑动条 -->
    <div class="space-y-5 mb-6">
      <div v-for="s in sliders" :key="s.key">
        <div class="flex items-baseline justify-between mb-1.5">
          <div>
            <span class="text-sm text-ink-100 font-semibold">{{ s.title }}</span>
            <span class="text-xs text-ink-500 ml-2">{{ s.desc }}</span>
          </div>
          <span
            class="font-mono text-sm"
            :class="values[s.key] > 0 ? 'text-cyber-cyan' : values[s.key] < 0 ? 'text-cyber-pink' : 'text-ink-500'"
          >
            {{ values[s.key] > 0 ? '+' : '' }}{{ values[s.key] }}{{ s.unit }}
          </span>
        </div>
        <input
          v-model.number="values[s.key]"
          type="range"
          :min="s.min"
          :max="s.max"
          :step="s.step"
          class="w-full cyber-range"
        />
        <div class="flex justify-between text-[10px] text-ink-500 mt-0.5 font-mono">
          <span>{{ s.min }}</span>
          <span>0</span>
          <span>+{{ s.max }}</span>
        </div>
      </div>
    </div>

    <!-- 对比卡片 -->
    <div v-if="baseVariant && compareVariant" class="grid grid-cols-2 gap-3 text-sm">
      <div class="panel-glass p-4 border border-cyber-cyan/20">
        <div class="text-xs text-ink-500 mb-3">{{ baseVariant.label }}</div>
        <div class="space-y-2">
          <div class="flex justify-between">
            <span class="text-ink-300">Offer 率</span>
            <span class="font-mono text-cyber-cyan">{{ fmtPct(baseVariant.offer_rate) }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">平均 offer 数</span>
            <span class="font-mono text-ink-100">{{ baseVariant.mean_offers.toFixed(2) }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">平均年薪</span>
            <span class="font-mono text-cyber-gold">{{ baseVariant.settled_rate > 0 ? baseVariant.mean_salary_when_settled.toFixed(1) + ' 万元/年' : '— （样本不足）' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">签约率</span>
            <span class="font-mono text-ink-100">{{ fmtPct(baseVariant.settled_rate) }}</span>
          </div>
        </div>
      </div>
      <div class="panel-glass p-4 border border-cyber-purple/40">
        <div class="text-xs text-cyber-purple mb-3 truncate">{{ compareVariant.label }}</div>
        <div class="space-y-2">
          <div class="flex justify-between">
            <span class="text-ink-300">Offer 率</span>
            <span class="font-mono">
              <span :class="deltaColor(compareVariant.offer_rate - baseVariant.offer_rate)">
                {{ fmtPct(compareVariant.offer_rate) }}
              </span>
              <span class="text-[10px] ml-1 text-ink-500">
                ({{ compareVariant.offer_rate >= baseVariant.offer_rate ? '+' : '' }}{{ ((compareVariant.offer_rate - baseVariant.offer_rate) * 100).toFixed(1) }}%)
              </span>
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">平均 offer 数</span>
            <span class="font-mono">
              <span :class="deltaColor(compareVariant.mean_offers - baseVariant.mean_offers)">
                {{ compareVariant.mean_offers.toFixed(2) }}
              </span>
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">平均年薪</span>
            <span class="font-mono">
              <span :class="deltaColor(compareVariant.mean_salary_when_settled - baseVariant.mean_salary_when_settled)">
                {{ compareVariant.settled_rate > 0 ? compareVariant.mean_salary_when_settled.toFixed(1) + ' 万元/年' : '—' }}
              </span>
              <span v-if="compareVariant.settled_rate > 0" class="text-[10px] ml-1 text-ink-500">
                ({{ compareVariant.mean_salary_when_settled >= baseVariant.mean_salary_when_settled ? '+' : '' }}{{ (compareVariant.mean_salary_when_settled - baseVariant.mean_salary_when_settled).toFixed(1) }} 万元/年)
              </span>
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-ink-300">签约率</span>
            <span class="font-mono">
              <span :class="deltaColor(compareVariant.settled_rate - baseVariant.settled_rate)">
                {{ fmtPct(compareVariant.settled_rate) }}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 所有变体 -->
    <div v-if="report && report.variants.length > 2" class="mt-5">
      <div class="text-xs text-ink-500 mb-2">所有变体</div>
      <div class="space-y-1.5 text-xs">
        <div
          v-for="v in report.variants.slice(1, -1)"
          :key="v.label"
          class="flex items-center justify-between panel-glass px-3 py-2"
        >
          <span class="text-ink-300 truncate flex-1 mr-3">{{ v.label }}</span>
          <span class="font-mono text-cyber-cyan">{{ fmtPct(v.offer_rate) }}</span>
          <span class="font-mono text-cyber-gold ml-3 w-24 text-right">{{ v.mean_salary_when_settled.toFixed(1) }} 万元/年</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-[10px] text-ink-500 mt-3">computing...</div>
  </div>
</template>

<style scoped>
.cyber-range {
  -webkit-appearance: none;
  height: 4px;
  background: linear-gradient(90deg, #ff4d9d 0%, #5f6786 50%, #00e5ff 100%);
  border-radius: 2px;
  outline: none;
}
.cyber-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e8ecff;
  cursor: pointer;
  box-shadow: 0 0 8px rgba(0, 229, 255, 0.6);
  border: 2px solid #00e5ff;
}
.cyber-range::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e8ecff;
  cursor: pointer;
  border: 2px solid #00e5ff;
}
</style>
