<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as d3 from 'd3'
import {
  schoolMeta,
  dimStats,
  skillGaps,
  topEmployers,
  destinations,
  cohortOutcome,
  type SchoolMeta,
  type DimStat,
  type SkillGap,
  type EmployerMatch,
  type DestinationSlice
} from '@/data/mockSchool'

/**
 * 学校端（高校就业指导中心）演示视图。
 *
 * 这一页是产品的商业主战场：C 端学生个人跑 sim 是流量入口，
 * B 端高校就业中心买"本校学生群体的人才洞察"才是营收来源。
 *
 * 四个区块：
 * 1. 本校群体五维竞争力分布（雷达图，本校均值 vs 市场均值）
 * 2. 技能缺口分析（本校 - 市场 的差值发散条形图）
 * 3. 该重点对接的 Top 雇主（按群体画像匹配度排序）
 * 4. 群体就业去向预测（1000 次模拟聚合的去向环形图 + 中位薪资）
 *
 * 数据全部来自 mockSchool.ts，onMounted 加载，不调后端（演示视图）。
 */

const meta = ref<SchoolMeta>(schoolMeta)
const dims = ref<DimStat[]>([])
const gaps = ref<SkillGap[]>([])
const employers = ref<EmployerMatch[]>([])
const dests = ref<DestinationSlice[]>([])
const outcome = ref(cohortOutcome)

const radarRef = ref<SVGSVGElement | null>(null)
const gapRef = ref<SVGSVGElement | null>(null)
const destRef = ref<SVGSVGElement | null>(null)

onMounted(() => {
  // 加载 mock（模拟一次数据装载）
  dims.value = dimStats
  gaps.value = skillGaps
  employers.value = topEmployers
  dests.value = destinations
  outcome.value = cohortOutcome
  // 等 DOM 布局稳定再画（父容器 clientWidth 才准），沿用 Dashboard 的 setTimeout 惯例
  setTimeout(() => {
    renderRadar()
    renderGap()
    renderDest()
  }, 50)
})

// ========= 1. 五维雷达图（本校均值 vs 市场均值）=========

function renderRadar() {
  const svg = radarRef.value
  if (!svg || !dims.value.length) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const width = container.clientWidth
  const height = 300
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) / 2 - 44
  const n = dims.value.length
  const angleSlice = (Math.PI * 2) / n
  const maxVal = 100

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${cx},${cy})`)

  // 同心网格圈
  const levels = 4
  for (let l = 1; l <= levels; l++) {
    const r = (radius * l) / levels
    const pts: Array<[number, number]> = []
    for (let i = 0; i < n; i++) {
      const angle = i * angleSlice - Math.PI / 2
      pts.push([Math.cos(angle) * r, Math.sin(angle) * r])
    }
    g.append('polygon')
      .attr('points', pts.map((p) => p.join(',')).join(' '))
      .attr('fill', 'none')
      .attr('stroke', '#2a3050')
      .attr('stroke-width', 1)
  }

  // 轴线 + 轴标签
  dims.value.forEach((d, i) => {
    const angle = i * angleSlice - Math.PI / 2
    const x = Math.cos(angle) * radius
    const y = Math.sin(angle) * radius
    g.append('line')
      .attr('x1', 0)
      .attr('y1', 0)
      .attr('x2', x)
      .attr('y2', y)
      .attr('stroke', '#2a3050')
      .attr('stroke-width', 1)
    const lx = Math.cos(angle) * (radius + 22)
    const ly = Math.sin(angle) * (radius + 22)
    let anchor = 'middle'
    if (lx > 6) {
      anchor = 'start'
    } else if (lx < -6) {
      anchor = 'end'
    }
    g.append('text')
      .attr('x', lx)
      .attr('y', ly)
      .attr('text-anchor', anchor)
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#a0a8c8')
      .attr('font-size', '11px')
      .text(d.label)
  })

  // 构造多边形顶点
  function toPoints(accessor: (d: DimStat) => number): Array<[number, number]> {
    return dims.value.map((d, i) => {
      const angle = i * angleSlice - Math.PI / 2
      const r = (accessor(d) / maxVal) * radius
      return [Math.cos(angle) * r, Math.sin(angle) * r]
    })
  }

  // 市场均值（灰色描边，作对照）
  const marketPts = toPoints((d) => d.market)
  g.append('polygon')
    .attr('points', marketPts.map((p) => p.join(',')).join(' '))
    .attr('fill', 'none')
    .attr('stroke', '#5f6786')
    .attr('stroke-width', 1.5)
    .attr('stroke-dasharray', '4,3')

  // 本校均值（青紫渐变填充）
  const schoolPts = toPoints((d) => d.mean)
  const defs = d3.select(svg).append('defs')
  const grad = defs
    .append('radialGradient')
    .attr('id', 'radarGrad')
  grad.append('stop').attr('offset', '0').attr('stop-color', '#00e5ff').attr('stop-opacity', '0.35')
  grad.append('stop').attr('offset', '1').attr('stop-color', '#9d4dff').attr('stop-opacity', '0.15')

  g.append('polygon')
    .attr('points', schoolPts.map((p) => p.join(',')).join(' '))
    .attr('fill', 'url(#radarGrad)')
    .attr('stroke', '#00e5ff')
    .attr('stroke-width', 2)

  // 本校顶点圆点
  g.selectAll('circle.pt')
    .data(schoolPts)
    .enter()
    .append('circle')
    .attr('class', 'pt')
    .attr('cx', (p) => p[0])
    .attr('cy', (p) => p[1])
    .attr('r', 3)
    .attr('fill', '#00e5ff')
}

// ========= 2. 技能缺口发散条形图（本校 - 市场）=========

function renderGap() {
  const svg = gapRef.value
  if (!svg || !gaps.value.length) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const data = gaps.value
  const margin = { top: 8, right: 44, bottom: 8, left: 96 }
  const width = container.clientWidth
  const innerW = width - margin.left - margin.right
  const rowH = 34
  const innerH = data.length * rowH
  const height = innerH + margin.top + margin.bottom

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  const maxAbs = d3.max(data, (d) => Math.abs(d.gap)) ?? 1
  const x = d3.scaleLinear().domain([-maxAbs, maxAbs]).range([0, innerW])
  const y = d3.scaleBand<string>().domain(data.map((d) => d.label)).range([0, innerH]).padding(0.4)
  const zero = x(0)

  // 零轴
  g.append('line')
    .attr('x1', zero)
    .attr('x2', zero)
    .attr('y1', 0)
    .attr('y2', innerH)
    .attr('stroke', '#2a3050')
    .attr('stroke-width', 1)

  // 条：短板（负）粉色，优势（正）绿色
  g.selectAll('rect.bar')
    .data(data)
    .enter()
    .append('rect')
    .attr('class', 'bar')
    .attr('y', (d) => y(d.label) ?? 0)
    .attr('height', y.bandwidth())
    .attr('x', (d) => (d.gap >= 0 ? zero : x(d.gap)))
    .attr('width', 0)
    .attr('fill', (d) => (d.gap >= 0 ? '#4dffaa' : '#ff4d9d'))
    .attr('rx', 2)
    .transition()
    .duration(800)
    .delay((_, i) => i * 60)
    .attr('width', (d) => Math.abs(x(d.gap) - zero))

  // 维度标签（左侧）
  g.selectAll('text.label')
    .data(data)
    .enter()
    .append('text')
    .attr('class', 'label')
    .attr('x', -8)
    .attr('y', (d) => (y(d.label) ?? 0) + y.bandwidth() / 2)
    .attr('text-anchor', 'end')
    .attr('dominant-baseline', 'middle')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '11px')
    .text((d) => d.label)

  // 差值数值
  g.selectAll('text.val')
    .data(data)
    .enter()
    .append('text')
    .attr('class', 'val')
    .attr('y', (d) => (y(d.label) ?? 0) + y.bandwidth() / 2)
    .attr('x', (d) => (d.gap >= 0 ? x(d.gap) + 6 : x(d.gap) - 6))
    .attr('text-anchor', (d) => (d.gap >= 0 ? 'start' : 'end'))
    .attr('dominant-baseline', 'middle')
    .attr('fill', (d) => (d.gap >= 0 ? '#4dffaa' : '#ff4d9d'))
    .attr('font-size', '11px')
    .attr('font-family', 'monospace')
    .attr('opacity', 0)
    .text((d) => (d.gap >= 0 ? '+' : '') + d.gap)
    .transition()
    .duration(500)
    .delay((_, i) => i * 60 + 500)
    .attr('opacity', 1)
}

// ========= 4. 群体去向环形图 =========

function renderDest() {
  const svg = destRef.value
  if (!svg || !dests.value.length) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const width = container.clientWidth
  const height = 300
  const radius = Math.min(width, height) / 2 - 12

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${width / 2},${height / 2})`)

  const palette = ['#00e5ff', '#9d4dff', '#ff4d9d', '#ffcc4d', '#4dffaa', '#ff7c4d', '#5f6786']
  const color = d3.scaleOrdinal<string>().domain(dests.value.map((d) => d.name)).range(palette)

  const pie = d3.pie<DestinationSlice>().value((d) => d.ratio).sort(null)
  const arc = d3
    .arc<d3.PieArcDatum<DestinationSlice>>()
    .innerRadius(radius * 0.55)
    .outerRadius(radius)
  const arcHover = d3
    .arc<d3.PieArcDatum<DestinationSlice>>()
    .innerRadius(radius * 0.55)
    .outerRadius(radius * 1.05)

  const paths = g
    .selectAll('path')
    .data(pie(dests.value))
    .enter()
    .append('path')
    .attr('fill', (d) => color(d.data.name))
    .attr('stroke', '#05060d')
    .attr('stroke-width', 2)
    .attr('opacity', 0.9)
    .each(function (d) {
      ;(this as SVGPathElement & { _current: d3.PieArcDatum<DestinationSlice> })._current = {
        ...d,
        startAngle: 0,
        endAngle: 0
      }
    })

  paths
    .transition()
    .duration(800)
    .attrTween('d', function (d) {
      const self = this as SVGPathElement & { _current: d3.PieArcDatum<DestinationSlice> }
      const i = d3.interpolate(self._current, d)
      self._current = i(1)
      return (t: number) => arc(i(t)) ?? ''
    })

  paths
    .on('mouseenter', function () {
      d3.select(this).transition().duration(180).attr('d', arcHover as unknown as () => string)
    })
    .on('mouseleave', function () {
      d3.select(this).transition().duration(180).attr('d', arc as unknown as () => string)
    })

  // 中心：整体中位薪资
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('fill', '#ffcc4d')
    .attr('font-size', '22px')
    .attr('font-weight', 'bold')
    .attr('font-family', 'monospace')
    .attr('y', -2)
    .text(outcome.value.overall_median_salary.toLocaleString('zh-CN'))
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('fill', '#5f6786')
    .attr('font-size', '10px')
    .attr('y', 16)
    .text('中位月薪(元)')

  // 图例（右上，两列）
  const legend = d3.select(svg).append('g').attr('transform', 'translate(8, 8)')
  const colPerSide = Math.ceil(dests.value.length / 2)
  dests.value.forEach((d, i) => {
    const col = Math.floor(i / colPerSide)
    const row = legend
      .append('g')
      .attr('transform', `translate(${col * 128}, ${(i % colPerSide) * 18})`)
    row.append('rect').attr('width', 10).attr('height', 10).attr('fill', color(d.name)).attr('rx', 2)
    row
      .append('text')
      .attr('x', 15)
      .attr('y', 9)
      .attr('fill', '#c4ccdf')
      .attr('font-size', '11px')
      .text(`${d.name} ${d.ratio}%`)
  })
}

// 匹配度颜色分档
function matchColor(m: number): string {
  if (m >= 85) {
    return 'text-cyber-gold'
  }
  if (m >= 78) {
    return 'text-cyber-cyan'
  }
  return 'text-cyber-purple'
}
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-7xl mx-auto">
      <!-- 顶部 -->
      <div class="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <p class="text-cyber-cyan text-sm tracking-widest mb-2">SCHOOL INSIGHT</p>
          <h1 class="text-4xl font-bold title-gradient">高校就业洞察</h1>
          <p class="text-ink-300 text-sm mt-2">
            <span class="text-ink-100">{{ meta.school_name }}</span>
            · {{ meta.cohort_label }} · 纳入洞察
            <span class="text-cyber-cyan font-mono">{{ meta.student_count }}</span> 名学生
            <span class="text-ink-500 ml-2">
              每人跑 {{ meta.simulated_universes.toLocaleString('zh-CN') }} 次平行宇宙模拟
            </span>
          </p>
        </div>
        <div class="text-right">
          <div class="text-xs text-ink-500 mb-1">数据更新</div>
          <div class="text-sm font-mono text-ink-100">{{ meta.updated_at }}</div>
          <div class="text-xs text-ink-500 mt-1">面向就业指导中心</div>
        </div>
      </div>

      <!-- KPI 卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">群体中位月薪</p>
          <p class="text-4xl font-mono font-bold text-cyber-gold mt-2">
            {{ (outcome.overall_median_salary / 1000).toFixed(1) }}<span class="text-xl">k</span>
          </p>
          <p class="text-ink-500 text-xs mt-1">剔除升学口径</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">模拟就业率</p>
          <p class="text-4xl font-mono font-bold text-cyber-cyan mt-2">
            {{ Math.round(outcome.employment_rate * 100) }}<span class="text-2xl">%</span>
          </p>
          <p class="text-ink-500 text-xs mt-1">1000 次模拟拿到 offer 比例</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">多 offer 率</p>
          <p class="text-4xl font-mono font-bold text-cyber-purple mt-2">
            {{ Math.round(outcome.multi_offer_rate * 100) }}<span class="text-2xl">%</span>
          </p>
          <p class="text-ink-500 text-xs mt-1">拿到 ≥2 个 offer</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">高门槛雇主命中</p>
          <p class="text-4xl font-mono font-bold text-cyber-pink mt-2">
            {{ Math.round(outcome.top_tier_offer_rate * 100) }}<span class="text-2xl">%</span>
          </p>
          <p class="text-ink-500 text-xs mt-1">门槛 ≥80 雇主 offer 占比</p>
        </div>
      </div>

      <!-- 1. 五维雷达 + 2. 技能缺口 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">本校群体五维竞争力</h3>
            <span class="text-xs text-ink-500">
              <span class="text-cyber-cyan">实线本校</span> ·
              <span class="text-ink-300">虚线市场</span>
            </span>
          </div>
          <svg ref="radarRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
        </div>

        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">技能缺口分析</h3>
            <span class="text-xs text-ink-500">本校均值 − 市场均值</span>
          </div>
          <svg ref="gapRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
          <div class="mt-3 pt-3 border-t border-ink-800 space-y-2">
            <div
              v-for="gp in gaps"
              :key="gp.key"
              class="flex items-start gap-2 text-xs"
            >
              <span
                class="mt-0.5 w-14 flex-shrink-0 font-mono"
                :class="gp.gap >= 0 ? 'text-emerald-400' : 'text-cyber-pink'"
              >{{ gp.gap >= 0 ? '+' : '' }}{{ gp.gap }}</span>
              <span class="text-ink-300 leading-relaxed">{{ gp.advice }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 3. Top 雇主 + 4. 去向预测 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">该重点对接的 Top 雇主</h3>
            <span class="text-xs text-ink-500">按群体画像匹配度排序</span>
          </div>
          <div class="space-y-2 mt-3">
            <div
              v-for="(e, idx) in employers"
              :key="e.code_name"
              class="p-3 rounded border border-ink-800 hover:border-cyber-cyan/40 transition"
            >
              <div class="flex items-center gap-3">
                <span class="text-ink-500 font-mono text-sm w-5">{{ idx + 1 }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-ink-100 font-semibold">{{ e.code_name }}</span>
                    <span class="text-xs text-ink-500">· {{ e.industry }}</span>
                  </div>
                </div>
                <div class="text-right w-16">
                  <div class="text-xs text-ink-500">匹配度</div>
                  <div class="font-mono font-bold text-sm" :class="matchColor(e.match)">
                    {{ e.match }}
                  </div>
                </div>
                <div class="text-right w-20">
                  <div class="text-xs text-ink-500">期望 offer</div>
                  <div class="font-mono text-sm text-cyber-cyan">{{ e.expected_offers }}</div>
                </div>
              </div>
              <div class="flex items-center gap-2 mt-2 pl-8">
                <div class="flex-1 h-1.5 bg-ink-800 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-gradient-to-r from-cyber-cyan to-cyber-purple"
                    :style="{ width: e.match + '%' }"
                  ></div>
                </div>
                <span class="text-xs text-ink-500 w-14 text-right">门槛 {{ e.hiring_bar }}</span>
              </div>
              <p class="text-xs text-ink-400 mt-2 pl-8 leading-relaxed">{{ e.reason }}</p>
            </div>
          </div>
        </div>

        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">群体就业去向预测</h3>
            <span class="text-xs text-ink-500">1000 次模拟聚合</span>
          </div>
          <svg ref="destRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
          <div class="mt-3 pt-3 border-t border-ink-800">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-ink-500 text-xs">
                  <th class="text-left font-normal pb-2">去向</th>
                  <th class="text-right font-normal pb-2">占比</th>
                  <th class="text-right font-normal pb-2">中位月薪</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in dests" :key="d.name" class="border-t border-ink-800/60">
                  <td class="py-1.5 text-ink-200">{{ d.name }}</td>
                  <td class="py-1.5 text-right font-mono text-cyber-cyan">{{ d.ratio }}%</td>
                  <td class="py-1.5 text-right font-mono text-ink-300">
                    <span v-if="d.median_salary > 0">{{ d.median_salary.toLocaleString('zh-CN') }}</span>
                    <span v-else class="text-ink-600">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <p class="text-ink-500 text-xs mt-6 text-center">
        本页为高校就业指导中心演示视图，数据基于全体在校生资料的群体聚合，不展示任何单个学生的可识别信息。
      </p>
    </div>
  </main>
</template>
