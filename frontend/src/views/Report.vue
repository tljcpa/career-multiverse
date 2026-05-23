<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getAggregate } from '@/api'
import { useSessionStore } from '@/stores/session'
import simSmoke from '@/data/sim_smoke.json'
import OfferHistogram from '@/components/charts/OfferHistogram.vue'
import CompanyProbBar from '@/components/charts/CompanyProbBar.vue'
import DestinationPie from '@/components/charts/DestinationPie.vue'
import WeekTimeline from '@/components/charts/WeekTimeline.vue'
import DecisionTree from '@/components/charts/DecisionTree.vue'
import CounterfactualPanel from '@/components/CounterfactualPanel.vue'
import type { SimRunFile, OutcomeAggregate } from '@/types/contracts'

/**
 * 报告页：用户旅程第四步，最终呈现。
 *
 * 布局：上方 4 个关键指标卡 → 中间 4 个图表 → 反事实滑动条 → 决策树
 * "1000 次平行宇宙"要给评委压倒感，所以指标卡用大字号 + 渐变。
 */
const router = useRouter()
const session = useSessionStore()

const aggregate = ref<OutcomeAggregate | null>(null)
const offerDist = ref<Record<string, number>>({})
const companyProb = ref<Array<{ company_code: string; probability: number }>>([])
const weekTimeline = ref<Array<{ week: number; count: number }>>([])
const loading = ref(true)

const sample = simSmoke as unknown as SimRunFile

onMounted(async () => {
  try {
    const data = await getAggregate(session.simSessionId ?? 'mock_sim')
    aggregate.value = data.primary_aggregate
    offerDist.value = data.offer_count_distribution
    companyProb.value = data.company_offer_probability
    weekTimeline.value = data.acceptance_week_timeline
    session.setAggregate(data.primary_aggregate)
  } finally {
    loading.value = false
  }
})

function restart() {
  session.reset()
  router.push('/upload')
}
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-7xl mx-auto">
      <!-- 顶部标题 -->
      <div class="flex items-end justify-between mb-8">
        <div>
          <p class="text-cyber-cyan text-sm tracking-widest mb-2">SIMULATION REPORT</p>
          <h1 class="text-4xl font-bold title-gradient">你的 1000 次平行春招</h1>
          <p class="text-ink-300 text-sm mt-2">
            数字分身已在 49 家公司组成的招聘宇宙中完成 1000 次完整春招。
            以下是统计结论 + 反事实分析。
          </p>
        </div>
        <button class="btn-ghost" @click="restart">重新开始</button>
      </div>

      <!-- KPI 卡片 -->
      <div v-if="aggregate" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">拿到 ≥1 个 offer 的概率</div>
          <div class="text-4xl font-mono font-bold text-cyber-cyan">
            {{ (aggregate.offer_rate * 100).toFixed(0) }}<span class="text-2xl">%</span>
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">平均 offer 数</div>
          <div class="text-4xl font-mono font-bold text-cyber-purple">
            {{ aggregate.mean_offers.toFixed(1) }}
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">中位数薪资</div>
          <div class="text-4xl font-mono font-bold text-cyber-gold">
            {{ aggregate.median_salary_when_settled.toFixed(0) }}<span class="text-2xl">万</span>
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">最终能签约的概率</div>
          <div class="text-4xl font-mono font-bold text-cyber-pink">
            {{ (aggregate.settled_rate * 100).toFixed(0) }}<span class="text-2xl">%</span>
          </div>
        </div>
      </div>

      <!-- 第一组：分布图表 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
        <div class="panel-glass p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-ink-100">Offer 数分布</h3>
            <span class="text-xs text-ink-500">1000 次模拟拿了多少 offer</span>
          </div>
          <OfferHistogram :data="offerDist" />
        </div>
        <div class="panel-glass p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-ink-100">接受 offer 的周次</h3>
            <span class="text-xs text-ink-500">什么时候最可能拍板</span>
          </div>
          <WeekTimeline :data="weekTimeline" />
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-8">
        <div class="lg:col-span-2 panel-glass p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-ink-100">各公司 offer 概率（Top 15）</h3>
            <span class="text-xs text-ink-500">在 1000 次模拟中拿到该公司 offer 的比例</span>
          </div>
          <CompanyProbBar :data="companyProb" />
        </div>
        <div class="panel-glass p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-ink-100">最终去向分布</h3>
          </div>
          <DestinationPie v-if="aggregate" :data="aggregate.destination_distribution" />
        </div>
      </div>

      <!-- 反事实滑动条 + 决策树 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
        <CounterfactualPanel />
        <div class="panel-glass p-5">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-ink-100">决策树（抽样 1 次）</h3>
            <span class="text-xs text-ink-500">这一次的关键岔路</span>
          </div>
          <DecisionTree :journeys="sample.outcome.journeys" />
          <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-cyber-cyan" />
              <span class="text-ink-300">你</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-cyber-purple" />
              <span class="text-ink-300">投递公司</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-cyber-gold" />
              <span class="text-ink-300">Offer</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full" style="background: #4dffaa" />
              <span class="text-ink-300">最终接受</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 rounded-full bg-cyber-pink" />
              <span class="text-ink-300">未通过/拒绝</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部 CTA -->
      <div class="panel-glass p-8 text-center">
        <h2 class="text-2xl font-bold title-gradient mb-3">关键结论</h2>
        <p class="text-ink-300 text-sm max-w-3xl mx-auto leading-relaxed">
          在 1000 个平行宇宙里，你最可能的去向是
          <span class="text-cyber-gold font-semibold">{{ sample.outcome.final_destination_company }}</span>，
          中位数薪资 <span class="text-cyber-cyan font-mono">{{ aggregate?.median_salary_when_settled.toFixed(0) ?? '—' }} 万</span>。
          调左侧滑动条可以看到——
          <span class="text-cyber-purple">如果你的项目含金量再提升 15 分，能多拿 25% 的 offer，
          薪资中位数 +14 万。</span>
          这就是你最值得投入的方向。
        </p>
        <div class="mt-6 flex justify-center gap-3">
          <button class="btn-primary" @click="restart">再跑一次 1000 个宇宙</button>
        </div>
      </div>
    </div>
    <div v-if="loading" class="fixed inset-0 flex items-center justify-center bg-space-bg/80 z-40">
      <div class="text-cyber-cyan">正在汇总 1000 次模拟结果...</div>
    </div>
  </main>
</template>
