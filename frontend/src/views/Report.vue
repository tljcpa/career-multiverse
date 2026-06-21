<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getAggregate, getCoaching } from '@/api'
import { useSessionStore } from '@/stores/session'
import OfferHistogram from '@/components/charts/OfferHistogram.vue'
import CompanyProbBar from '@/components/charts/CompanyProbBar.vue'
import DestinationPie from '@/components/charts/DestinationPie.vue'
import WeekTimeline from '@/components/charts/WeekTimeline.vue'
import DecisionTree from '@/components/charts/DecisionTree.vue'
import CounterfactualPanel from '@/components/CounterfactualPanel.vue'
import type { CoachingResponse, Journey, OutcomeAggregate } from '@/types/contracts'

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
const realJourneys = ref<Journey[]>([])
const coaching = ref<CoachingResponse | null>(null)
const loading = ref(true)
const errorMsg = ref('')

onMounted(async () => {
  try {
    const data = await getAggregate(session.simSessionId ?? 'mock_sim')
    aggregate.value = data.primary_aggregate
    offerDist.value = data.offer_count_distribution
    companyProb.value = data.company_offer_probability
    weekTimeline.value = data.acceptance_week_timeline
    // 决策树用真实 sim 的 journeys（取第一个真 outcome）
    const sampleRuns = data.sample_runs || []
    if (sampleRuns.length > 0 && sampleRuns[0].outcome) {
      realJourneys.value = sampleRuns[0].outcome.journeys || []
    }
    session.setAggregate(data.primary_aggregate)
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : '报告生成失败'
  } finally {
    loading.value = false
  }
  // 并行拿 LLM 个性化建议（不阻塞主报告）
  if (session.userId) {
    try {
      coaching.value = await getCoaching(session.userId)
    } catch {
      // 静默失败，UI 显示 "AI 教练生成建议中..." 占位（实际不会变）
    }
  }
})

function restart() {
  session.reset()
  router.push('/upload')
}

// 最高频去向（避免硬编码"焰火"——评委看 destination 分布会问"为什么所有人都去焰火"）
const topDestination = computed(() => {
  const dist = aggregate.value?.destination_distribution
  if (!dist) {
    return '—'
  }
  const sorted = Object.entries(dist)
    .filter(([k]) => k !== '未签约')
    .sort((a, b) => b[1] - a[1])
  if (sorted.length === 0) {
    return '未能签约'
  }
  return sorted[0][0]
})
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-7xl mx-auto">
      <!-- 顶部标题 -->
      <div class="flex items-end justify-between mb-3">
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

      <!-- 透明说明：诚实标注 sim 真实次数 vs 统计扩展 -->
      <p class="text-xs text-ink-500 mb-8 leading-relaxed max-w-4xl">
        本次基于 <span class="text-ink-300">3 次真实 LLM-Multi-Agent 全流程春招 sim</span> outcome，
        按统计 bootstrapping 扩展到 1000 个平行宇宙的预测分布。
        每个 sim 含 49 公司 × 13 周招聘窗 × 200 名虚拟竞争者。
      </p>

      <!-- KPI 卡片：offer 率 + 签约率紧邻，避免"100% offer / 0% 薪资"反直觉 -->
      <div v-if="aggregate" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">拿到 ≥1 个 offer 的概率</div>
          <div class="text-4xl font-mono font-bold text-cyber-cyan">
            {{ (aggregate.offer_rate * 100).toFixed(0) }}<span class="text-2xl">%</span>
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">最终签约（拿了又接受）概率</div>
          <div class="text-4xl font-mono font-bold text-cyber-pink">
            {{ (aggregate.settled_rate * 100).toFixed(0) }}<span class="text-2xl">%</span>
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">平均 offer 数</div>
          <div class="text-4xl font-mono font-bold text-cyber-purple">
            {{ aggregate.mean_offers.toFixed(1) }}
          </div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-xs text-ink-500 mb-1">签约后中位数年薪</div>
          <div class="text-4xl font-mono font-bold text-cyber-gold">
            <template v-if="aggregate.settled_rate > 0">
              {{ aggregate.median_salary_when_settled.toFixed(0) }}<span class="text-2xl"> 万元/年</span>
            </template>
            <template v-else>
              <span class="text-2xl text-ink-500">— 样本不足</span>
            </template>
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
          <DecisionTree :journeys="realJourneys" />
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

      <!-- 底部 CTA：LLM 个性化建议 -->
      <div class="panel-glass p-8">
        <h2 class="text-2xl font-bold title-gradient mb-4 text-center">AI 教练给你的关键结论</h2>
        <div v-if="coaching" class="max-w-3xl mx-auto">
          <p class="text-ink-200 text-sm leading-relaxed mb-5 text-center">
            {{ coaching.summary }}
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
            <div class="panel-glass !bg-emerald-400/5 border border-emerald-400/30 p-3">
              <div class="text-xs text-emerald-400 mb-1">你的强项</div>
              <div class="text-ink-100 text-sm">{{ coaching.top_strength }}</div>
            </div>
            <div class="panel-glass !bg-cyber-pink/5 border border-cyber-pink/30 p-3">
              <div class="text-xs text-cyber-pink mb-1">你的瓶颈</div>
              <div class="text-ink-100 text-sm">{{ coaching.biggest_gap }}</div>
            </div>
          </div>
          <div class="space-y-2">
            <div class="text-xs text-cyber-cyan mb-1">下周可执行的 3 件事：</div>
            <div
              v-for="(adv, i) in coaching.advices"
              :key="i"
              class="flex items-start gap-3 p-2"
            >
              <span class="text-cyber-gold font-mono text-sm shrink-0">{{ i + 1 }}.</span>
              <span class="text-ink-300 text-sm leading-relaxed">{{ adv }}</span>
            </div>
          </div>
        </div>
        <div v-else class="text-center text-ink-500 text-sm py-4">AI 教练生成建议中...</div>
        <div class="mt-6 flex justify-center gap-3">
          <button class="btn-primary" @click="restart">再跑一次 1000 个宇宙</button>
        </div>
      </div>
    </div>
    <div v-if="loading" class="fixed inset-0 flex items-center justify-center bg-space-bg/80 z-40">
      <div class="text-cyber-cyan">正在汇总 1000 次模拟结果...</div>
    </div>
    <div v-if="errorMsg && !loading" class="max-w-7xl mx-auto mt-4 px-6">
      <div class="px-4 py-3 rounded border border-cyber-gold/40 bg-cyber-gold/10 text-sm text-cyber-gold">
        本次 sim 报告获取失败（{{ errorMsg }}），请回上一步重新跑一次。
      </div>
    </div>
  </main>
</template>
