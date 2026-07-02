<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'
import {
  enterprises,
  strategyExperiments,
  marketPositions,
  type EnterpriseTwin,
  type StrategyExperiment,
  type MarketPosition
} from '@/data/mockEnterprise'

/**
 * 企业端演示视图 —— "企业数字分身 + 策略实验"。
 *
 * 和候选人侧对称：候选人有数字分身跑平行宇宙，企业也能把自己的招聘策略
 * 丢进虚拟人才市场做对照实验。三个区块：
 *   1. 企业数字分身卡（可切换 3 家示例企业）
 *   2. 策略实验对比（核心卖点）：只招高学历 vs 招潜力型培养，3 年后四维对照
 *   3. 反向品牌视图：你公司在应届生眼里的画像 + 门槛市场相对位置
 *
 * 数据全部来自 mockEnterprise.ts，onMounted 加载，不调后端。
 */

// 当前选中的企业
const list = ref<EnterpriseTwin[]>([])
const activeId = ref<string>('')

const active = computed<EnterpriseTwin | null>(() => {
  return list.value.find((e) => e.id === activeId.value) ?? null
})
const experiment = computed<StrategyExperiment | null>(() => {
  return activeId.value ? strategyExperiments[activeId.value] ?? null : null
})
const market = computed<MarketPosition | null>(() => {
  return activeId.value ? marketPositions[activeId.value] ?? null : null
})

// 四维指标的展示元信息（雷达 + 对照卡共用）
const metricMeta = [
  { key: 'talentQuality', label: '人才质量分' },
  { key: 'retentionRate', label: '留存率' },
  { key: 'laborCostScore', label: '人力成本控制' },
  { key: 'teamStability', label: '团队稳定性' }
] as const

const urgencyLabel = (u: string): string => {
  if (u === 'high') {
    return '急招'
  }
  if (u === 'mid') {
    return '常规'
  }
  return '储备'
}
const urgencyColor = (u: string): string => {
  if (u === 'high') {
    return 'text-cyber-pink border-cyber-pink/40 bg-cyber-pink/5'
  }
  if (u === 'mid') {
    return 'text-cyber-cyan border-cyber-cyan/40 bg-cyber-cyan/5'
  }
  return 'text-ink-300 border-ink-500/40 bg-white/5'
}

// ============ D3 雷达图 ============
const radarRef = ref<SVGSVGElement | null>(null)

function renderRadar() {
  const svg = radarRef.value
  const exp = experiment.value
  if (!svg || !exp) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const size = Math.min(container.clientWidth, 360)
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 44 // 留标签边距
  const axes = metricMeta.length

  d3.select(svg).selectAll('*').remove()
  const root = d3
    .select(svg)
    .attr('viewBox', `0 0 ${size} ${size}`)
    .attr('width', '100%')
    .append('g')

  // 背景同心多边形网格（4 圈）
  const rings = 4
  for (let r = 1; r <= rings; r++) {
    const rr = (radius * r) / rings
    const pts: string[] = []
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2
      pts.push(`${cx + rr * Math.cos(angle)},${cy + rr * Math.sin(angle)}`)
    }
    root
      .append('polygon')
      .attr('points', pts.join(' '))
      .attr('fill', 'none')
      .attr('stroke', '#3a3f55')
      .attr('stroke-width', 0.8)
      .attr('opacity', 0.6)
  }

  // 轴线 + 标签
  for (let i = 0; i < axes; i++) {
    const angle = (Math.PI * 2 * i) / axes - Math.PI / 2
    const x2 = cx + radius * Math.cos(angle)
    const y2 = cy + radius * Math.sin(angle)
    root
      .append('line')
      .attr('x1', cx)
      .attr('y1', cy)
      .attr('x2', x2)
      .attr('y2', y2)
      .attr('stroke', '#3a3f55')
      .attr('stroke-width', 0.8)
    const lx = cx + (radius + 24) * Math.cos(angle)
    const ly = cy + (radius + 24) * Math.sin(angle)
    root
      .append('text')
      .attr('x', lx)
      .attr('y', ly)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#a0a8c8')
      .attr('font-size', '11px')
      .text(metricMeta[i].label)
  }

  // 把一套 outcome 画成一层多边形
  const drawLayer = (outcome: Record<string, number>, color: string, fillOpacity: number, id: string) => {
    const pts: [number, number][] = []
    for (let i = 0; i < axes; i++) {
      const angle = (Math.PI * 2 * i) / axes - Math.PI / 2
      const val = outcome[metricMeta[i].key] ?? 0
      const rr = (radius * val) / 100
      pts.push([cx + rr * Math.cos(angle), cy + rr * Math.sin(angle)])
    }
    const poly = root
      .append('polygon')
      .attr('points', pts.map((p) => p.join(',')).join(' '))
      .attr('fill', color)
      .attr('fill-opacity', 0)
      .attr('stroke', color)
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0)
    poly.transition().duration(700).attr('fill-opacity', fillOpacity).attr('stroke-opacity', 0.9)
    // 顶点
    pts.forEach((p) => {
      root
        .append('circle')
        .attr('cx', p[0])
        .attr('cy', p[1])
        .attr('r', 0)
        .attr('fill', color)
        .transition()
        .duration(700)
        .attr('r', 3)
    })
  }

  // A 组用青色，B 组用金色，B 覆盖在上层（是我们想推的赢家）
  drawLayer(exp.strategyA.outcome as unknown as Record<string, number>, '#00e5ff', 0.12, 'a')
  drawLayer(exp.strategyB.outcome as unknown as Record<string, number>, '#ffcc4d', 0.18, 'b')
}

// ============ D3 逐年趋势（分组柱：质量 vs 成本指数） ============
const trendRef = ref<SVGSVGElement | null>(null)

function renderTrend() {
  const svg = trendRef.value
  const exp = experiment.value
  if (!svg || !exp) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const width = container.clientWidth
  const height = 240
  const margin = { top: 16, right: 16, bottom: 40, left: 36 }
  const innerW = width - margin.left - margin.right
  const innerH = height - margin.top - margin.bottom

  d3.select(svg).selectAll('*').remove()

  // 组织成 { year, aQuality, bQuality } 逐年对照人才质量
  const years = exp.strategyA.yearByYear.map((d) => d.year)
  const rows = years.map((yr, i) => ({
    year: yr,
    a: exp.strategyA.yearByYear[i].talentQuality,
    b: exp.strategyB.yearByYear[i].talentQuality
  }))

  const x0 = d3.scaleBand<string>().domain(years).range([0, innerW]).padding(0.28)
  const x1 = d3.scaleBand<string>().domain(['a', 'b']).range([0, x0.bandwidth()]).padding(0.12)
  const y = d3.scaleLinear().domain([0, 100]).range([innerH, 0])

  const g = d3
    .select(svg)
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', '100%')
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  const color = (k: string): string => {
    if (k === 'a') {
      return '#00e5ff'
    }
    return '#ffcc4d'
  }

  rows.forEach((row) => {
    const gx = x0(row.year) ?? 0
    ;(['a', 'b'] as const).forEach((k) => {
      const val = k === 'a' ? row.a : row.b
      g.append('rect')
        .attr('x', gx + (x1(k) ?? 0))
        .attr('y', innerH)
        .attr('width', x1.bandwidth())
        .attr('height', 0)
        .attr('rx', 3)
        .attr('fill', color(k))
        .attr('fill-opacity', 0.85)
        .transition()
        .duration(700)
        .attr('y', y(val))
        .attr('height', innerH - y(val))
      g.append('text')
        .attr('x', gx + (x1(k) ?? 0) + x1.bandwidth() / 2)
        .attr('y', y(val) - 5)
        .attr('text-anchor', 'middle')
        .attr('fill', color(k))
        .attr('font-size', '10px')
        .attr('opacity', 0)
        .text(val)
        .transition()
        .duration(700)
        .delay(300)
        .attr('opacity', 1)
    })
  })

  // x 轴
  g.append('g')
    .attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x0))
    .selectAll('text')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '11px')
  // y 轴
  g.append('g')
    .call(d3.axisLeft(y).ticks(4))
    .selectAll('text')
    .attr('fill', '#5f6786')
    .attr('font-size', '10px')
  g.selectAll('.domain, .tick line').attr('stroke', '#3a3f55')
}

function renderAll() {
  nextTick(() => {
    renderRadar()
    renderTrend()
  })
}

onMounted(() => {
  // mock 加载：模拟"从后台拉企业分身"，实际直接读本地数据
  list.value = enterprises
  activeId.value = enterprises[0]?.id ?? ''
  renderAll()
})

// 切换企业时重绘两张图
watch(activeId, renderAll)

function selectEnterprise(id: string) {
  activeId.value = id
}

// 反向品牌：门槛在市场标尺上的百分比位置（0-120 尺度映射到条宽）
const barScaleMax = 120
const pct = (v: number): string => `${Math.min(100, (v / barScaleMax) * 100)}%`
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-16 px-6">
    <div class="max-w-6xl mx-auto">
      <!-- 页头 -->
      <div class="mb-6">
        <div class="text-xs text-ink-500 mb-1">企业端 · 虚拟人才市场</div>
        <h1 class="text-3xl font-bold title-gradient">企业数字分身 · 策略实验室</h1>
        <p class="text-sm text-ink-300 mt-2 max-w-2xl leading-relaxed">
          候选人能在平行宇宙里预演求职，企业同样能把招聘策略丢进虚拟人才市场做对照实验——
          不用拿真实的一届应届生试错，就看到 3 年后的结果。
        </p>
      </div>

      <template v-if="active">
        <!-- 企业切换 tab -->
        <div class="flex flex-wrap gap-2 mb-6">
          <button
            v-for="e in list"
            :key="e.id"
            class="px-4 py-2 rounded-lg text-sm border transition-all cursor-pointer"
            :class="e.id === activeId
              ? 'border-cyber-cyan/60 text-cyber-cyan bg-cyber-cyan/10'
              : 'border-white/5 text-ink-300 bg-space-panel/50 hover:border-cyber-cyan/30'"
            @click="selectEnterprise(e.id)"
          >
            {{ e.codeName }}
          </button>
        </div>

        <!-- ===== 区块 1：企业数字分身卡 ===== -->
        <div class="panel-glass p-6 mb-6">
          <div class="flex items-start justify-between flex-wrap gap-4 mb-5">
            <div>
              <div class="flex items-center gap-3">
                <h2 class="text-2xl font-bold text-ink-100">{{ active.codeName }}</h2>
                <span class="text-xs px-2 py-0.5 rounded-full border border-cyber-purple/40 text-cyber-purple bg-cyber-purple/5">
                  数字分身
                </span>
              </div>
              <div class="text-sm text-ink-300 mt-2">
                {{ active.industry }} <span class="text-ink-500">·</span> {{ active.scale }}
              </div>
            </div>
            <div class="text-right">
              <div class="text-xs text-ink-500 mb-1">招聘门槛 hiring_bar（0-120）</div>
              <div class="text-4xl font-mono font-bold text-cyber-gold">{{ active.hiringBar }}</div>
            </div>
          </div>

          <div class="grid md:grid-cols-2 gap-5">
            <!-- 岗位需求 -->
            <div>
              <div class="text-xs text-ink-500 mb-3">当前岗位需求</div>
              <div class="space-y-2">
                <div
                  v-for="r in active.openRoles"
                  :key="r.role"
                  class="flex items-center gap-3 p-3 rounded border border-ink-500/20 bg-white/[0.02]"
                >
                  <span class="text-sm text-ink-100 flex-1">{{ r.role }}</span>
                  <span class="text-xs font-mono text-ink-300">×{{ r.headcount }}</span>
                  <span class="text-xs px-2 py-0.5 rounded border" :class="urgencyColor(r.urgency)">
                    {{ urgencyLabel(r.urgency) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 文化 + 筛选策略 -->
            <div>
              <div class="text-xs text-ink-500 mb-3">文化标签</div>
              <div class="flex flex-wrap gap-2 mb-5">
                <span
                  v-for="t in active.cultureTags"
                  :key="t"
                  class="text-xs px-3 py-1 rounded-full border border-cyber-cyan/25 text-cyber-cyan bg-cyber-cyan/5"
                >
                  {{ t }}
                </span>
              </div>
              <div class="text-xs text-ink-500 mb-2">当前筛选策略</div>
              <div class="text-sm text-ink-300 leading-relaxed p-3 rounded border-l-2 border-cyber-purple/40 bg-white/[0.02]">
                {{ active.screeningStrategy }}
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 区块 2：策略实验对比（核心卖点） ===== -->
        <div v-if="experiment" class="panel-glass p-6 mb-6">
          <div class="flex items-center justify-between mb-1 flex-wrap gap-2">
            <h2 class="text-lg font-bold text-ink-100">策略实验：两种招聘策略，3 年后见分晓</h2>
            <span class="text-xs text-ink-500">在虚拟人才市场里跑对照，不拿真人试错</span>
          </div>
          <p class="text-xs text-ink-500 mb-5">同一批岗位、同样的招聘预算，只改筛选策略，模拟推进 3 年。</p>

          <!-- 两个策略头卡 -->
          <div class="grid md:grid-cols-2 gap-4 mb-6">
            <div class="p-4 rounded-lg border border-cyber-cyan/30 bg-cyber-cyan/[0.04]">
              <div class="flex items-center gap-2 mb-1">
                <span class="w-3 h-3 rounded-sm bg-cyber-cyan inline-block"></span>
                <span class="text-cyber-cyan font-semibold">策略 A · {{ experiment.strategyA.name }}</span>
              </div>
              <div class="text-xs text-ink-300">{{ experiment.strategyA.subtitle }}</div>
            </div>
            <div class="p-4 rounded-lg border border-cyber-gold/30 bg-cyber-gold/[0.04]">
              <div class="flex items-center gap-2 mb-1">
                <span class="w-3 h-3 rounded-sm bg-cyber-gold inline-block"></span>
                <span class="text-cyber-gold font-semibold">策略 B · {{ experiment.strategyB.name }}</span>
              </div>
              <div class="text-xs text-ink-300">{{ experiment.strategyB.subtitle }}</div>
            </div>
          </div>

          <div class="grid md:grid-cols-2 gap-6">
            <!-- 雷达图：3 年后四维终局对照 -->
            <div>
              <div class="text-xs text-ink-500 mb-2 text-center">3 年后四维终局对照</div>
              <div class="flex justify-center">
                <svg ref="radarRef" class="block" preserveAspectRatio="xMidYMid meet" />
              </div>
              <div class="flex justify-center gap-5 mt-2 text-xs">
                <span class="flex items-center gap-1.5 text-ink-300">
                  <span class="w-3 h-3 rounded-sm bg-cyber-cyan inline-block"></span>只招高学历
                </span>
                <span class="flex items-center gap-1.5 text-ink-300">
                  <span class="w-3 h-3 rounded-sm bg-cyber-gold inline-block"></span>招潜力型培养
                </span>
              </div>
            </div>

            <!-- 逐年人才质量趋势柱 -->
            <div>
              <div class="text-xs text-ink-500 mb-2 text-center">人才质量分 · 逐年趋势</div>
              <svg ref="trendRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
              <p class="text-xs text-ink-500 mt-1 text-center leading-relaxed">
                潜力组起点低，随培养曲线逐年爬升，在第 3 年反超。
              </p>
            </div>
          </div>

          <!-- 四维指标数字对照卡 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
            <div
              v-for="m in metricMeta"
              :key="m.key"
              class="p-3 rounded-lg border border-ink-500/20 bg-white/[0.02]"
            >
              <div class="text-xs text-ink-500 mb-2">{{ m.label }}</div>
              <div class="flex items-baseline justify-between">
                <span class="text-xs text-cyber-cyan">高学历</span>
                <span class="font-mono text-cyber-cyan">{{ experiment.strategyA.outcome[m.key] }}</span>
              </div>
              <div class="flex items-baseline justify-between mt-1">
                <span class="text-xs text-cyber-gold">潜力型</span>
                <span class="font-mono font-bold text-cyber-gold">{{ experiment.strategyB.outcome[m.key] }}</span>
              </div>
              <!-- 差值指示条 -->
              <div class="mt-2 h-1 rounded-full bg-ink-500/20 overflow-hidden">
                <div
                  class="h-full"
                  :class="experiment.strategyB.outcome[m.key] >= experiment.strategyA.outcome[m.key] ? 'bg-cyber-gold' : 'bg-cyber-cyan'"
                  :style="{ width: Math.min(100, Math.abs(experiment.strategyB.outcome[m.key] - experiment.strategyA.outcome[m.key]) * 3 + 10) + '%' }"
                ></div>
              </div>
            </div>
          </div>

          <!-- 实验结论 -->
          <div class="mt-6 p-4 rounded-lg border border-cyber-gold/25 bg-cyber-gold/[0.03]">
            <div class="text-xs text-cyber-gold font-semibold mb-2">实验结论</div>
            <p class="text-sm text-ink-100 leading-relaxed">{{ experiment.verdict }}</p>
          </div>
        </div>

        <!-- ===== 区块 3：反向品牌视图 ===== -->
        <div v-if="market" class="panel-glass p-6">
          <div class="flex items-center justify-between mb-1 flex-wrap gap-2">
            <h2 class="text-lg font-bold text-ink-100">反向品牌视图：你在应届生眼里长什么样</h2>
            <span class="text-xs text-ink-500">候选人侧数据反推</span>
          </div>
          <p class="text-xs text-ink-500 mb-5">企业总在筛候选人，但候选人也在筛企业。这是把镜头反过来。</p>

          <!-- 门槛市场相对位置标尺 -->
          <div class="mb-6">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs text-ink-500">招聘门槛在市场里的相对位置</span>
              <span class="text-xs text-ink-300">
                市场前 <span class="text-cyber-gold font-mono">{{ 100 - market.percentile }}%</span>
              </span>
            </div>
            <div class="relative h-8">
              <!-- 底轨 -->
              <div class="absolute top-3.5 left-0 right-0 h-1 rounded-full bg-gradient-to-r from-ink-500/30 via-cyber-cyan/30 to-cyber-gold/40"></div>
              <!-- 市场中位标记 -->
              <div class="absolute top-1.5 flex flex-col items-center" :style="{ left: pct(market.marketMedian) }">
                <div class="w-px h-5 bg-ink-500"></div>
                <span class="text-[10px] text-ink-500 mt-0.5 whitespace-nowrap -translate-x-1/2">市场中位 {{ market.marketMedian }}</span>
              </div>
              <!-- 前 10% 门槛线 -->
              <div class="absolute top-1.5 flex flex-col items-center" :style="{ left: pct(market.marketTop10) }">
                <div class="w-px h-5 bg-cyber-pink/60"></div>
                <span class="text-[10px] text-cyber-pink/70 mt-0.5 whitespace-nowrap -translate-x-1/2">前 10% 线 {{ market.marketTop10 }}</span>
              </div>
              <!-- 我的门槛（发光点） -->
              <div class="absolute top-2 -translate-x-1/2" :style="{ left: pct(market.myBar) }">
                <div class="w-4 h-4 rounded-full bg-cyber-gold shadow-[0_0_12px_rgba(255,204,77,0.8)]"></div>
              </div>
            </div>
            <div class="text-center mt-6">
              <span class="text-xs text-ink-500">你的门槛 </span>
              <span class="font-mono text-cyber-gold font-bold">{{ market.myBar }}</span>
            </div>
          </div>

          <div class="grid md:grid-cols-2 gap-4 mb-5">
            <!-- 文化印象 -->
            <div class="p-4 rounded-lg border border-cyber-pink/25 bg-cyber-pink/[0.03]">
              <div class="text-xs text-cyber-pink font-semibold mb-2">应届生眼里的一句话印象</div>
              <p class="text-sm text-ink-100 leading-relaxed">"{{ active.brandImpression }}"</p>
            </div>
            <!-- 能吸引的候选人画像 -->
            <div class="p-4 rounded-lg border border-cyber-purple/25 bg-cyber-purple/[0.03]">
              <div class="text-xs text-cyber-purple font-semibold mb-2">这个门槛能吸引到谁</div>
              <p class="text-sm text-ink-100 leading-relaxed">{{ active.attractsProfile }}</p>
            </div>
          </div>

          <!-- 市场位置解读 -->
          <div class="p-4 rounded-lg border-l-2 border-cyber-cyan/40 bg-white/[0.02]">
            <div class="text-xs text-cyber-cyan font-semibold mb-2">市场位置解读</div>
            <p class="text-sm text-ink-300 leading-relaxed">{{ market.desc }}</p>
          </div>
        </div>
      </template>

      <div v-else class="text-center pt-32 text-cyber-cyan">企业分身加载中...</div>
    </div>
  </main>
</template>
