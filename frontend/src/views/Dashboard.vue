<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import * as d3 from 'd3'
import { adminListCompanies, adminListPersonas } from '@/api'
import type { Company } from '@/types/contracts'

/**
 * 市场看板：全市场统计可视化。
 *
 * 与 Report 页的区别：
 * - Report 是单个用户跑完 sim 后的"个人结果"
 * - Dashboard 是整个沙盘市场的"宏观画像"
 *
 * 数据来源：admin endpoints（同样的 CRUD 数据，只是聚合视角）
 * 不引入新 backend endpoint：从公司列表 + persona 列表前端聚合
 */

const companies = ref<Company[]>([])
const personas = ref<Array<Record<string, unknown>>>([])
const loading = ref(true)
const lastUpdated = ref<string>('')

async function reload() {
  loading.value = true
  try {
    const [c, p] = await Promise.all([adminListCompanies(), adminListPersonas()])
    companies.value = c
    personas.value = p
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN')
  } catch (e) {
    console.warn('dashboard load failed', e)
  } finally {
    loading.value = false
  }
}

onMounted(reload)

// ========= 聚合统计 =========

const stats = computed(() => {
  const c = companies.value
  const p = personas.value
  if (!c.length) {
    return null
  }
  // hiring_bar 均值
  const avgBar = c.reduce((s, x) => s + x.hidden_signals.hiring_bar, 0) / c.length
  // 简历质量均值
  const avgQuality = p.length > 0
    ? p.reduce((s, x) => {
        const q = (x.official_cv as Record<string, unknown>)?.resume_quality
        return s + (typeof q === 'number' ? q : 0)
      }, 0) / p.length
    : 0
  // 总 JD 数
  const totalJDs = c.reduce((s, x) => s + (x.job_postings?.length ?? 0), 0)
  return {
    companies: c.length,
    personas: p.length,
    avgBar: Math.round(avgBar),
    avgQuality: Math.round(avgQuality),
    totalJDs,
    // 估算的全市场 simulated offer 数（拍脑袋的统计推断）：
    // 49 公司 × 平均 0.3 offer 率 / 公司 × 200 候选人 ≈ 总 offer
    estimatedOffers: Math.round(c.length * 0.4 * p.length)
  }
})

// 行业分布
const industryDist = computed(() => {
  const counter: Record<string, number> = {}
  for (const c of companies.value) {
    const key = c.industry.split(/[-/]/)[0]  // 截短：互联网-短视频 → 互联网
    counter[key] = (counter[key] || 0) + 1
  }
  return Object.entries(counter)
    .map(([k, v]) => ({ name: k, count: v }))
    .sort((a, b) => b.count - a.count)
})

// hiring_bar 直方图
const barHistogram = computed(() => {
  const bins: Array<{ range: string; count: number }> = [
    { range: '60-70', count: 0 },
    { range: '70-80', count: 0 },
    { range: '80-90', count: 0 },
    { range: '90-100', count: 0 }
  ]
  for (const c of companies.value) {
    const b = c.hidden_signals.hiring_bar
    if (b < 70) {
      bins[0].count++
    } else if (b < 80) {
      bins[1].count++
    } else if (b < 90) {
      bins[2].count++
    } else {
      bins[3].count++
    }
  }
  return bins
})

// 学校 tier 分布
const tierDist = computed(() => {
  const order = ['top', '985_top', '985', '211', 'double_non', 'lower', 'overseas_top', 'overseas_other']
  const labels: Record<string, string> = {
    top: '清北复交',
    '985_top': 'C9/985 头部',
    '985': '普通 985',
    '211': '211',
    double_non: '双非一本',
    lower: '二本及以下',
    overseas_top: '海外 QS100',
    overseas_other: '海外其他'
  }
  const counter: Record<string, number> = {}
  for (const p of personas.value) {
    const tier = (p.hidden_signals as Record<string, unknown>)?.school_tier as string
    counter[tier] = (counter[tier] || 0) + 1
  }
  return order
    .filter((t) => counter[t])
    .map((t) => ({ label: labels[t] || t, count: counter[t] }))
})

// ========= D3 渲染 =========

const industryRef = ref<SVGSVGElement | null>(null)
const barRef = ref<SVGSVGElement | null>(null)
const tierRef = ref<SVGSVGElement | null>(null)

function renderIndustryChart() {
  const svg = industryRef.value
  if (!svg || !industryDist.value.length) {
    return
  }
  const width = svg.parentElement?.clientWidth ?? 400
  const height = Math.max(220, industryDist.value.length * 22)
  const margin = { top: 8, right: 40, bottom: 8, left: 90 }
  const innerW = width - margin.left - margin.right
  const innerH = height - margin.top - margin.bottom

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  const y = d3.scaleBand().domain(industryDist.value.map((d) => d.name)).range([0, innerH]).padding(0.25)
  const x = d3.scaleLinear().domain([0, d3.max(industryDist.value, (d) => d.count) ?? 1]).range([0, innerW])

  g.selectAll('rect')
    .data(industryDist.value)
    .enter()
    .append('rect')
    .attr('x', 0)
    .attr('y', (d) => y(d.name) ?? 0)
    .attr('width', (d) => x(d.count))
    .attr('height', y.bandwidth())
    .attr('fill', 'url(#purpleGrad)')
    .attr('rx', 3)

  // 标签
  g.selectAll('text.label')
    .data(industryDist.value)
    .enter()
    .append('text')
    .attr('class', 'label')
    .attr('x', -8)
    .attr('y', (d) => (y(d.name) ?? 0) + y.bandwidth() / 2 + 4)
    .attr('text-anchor', 'end')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '11px')
    .text((d) => d.name)

  // 数值
  g.selectAll('text.val')
    .data(industryDist.value)
    .enter()
    .append('text')
    .attr('class', 'val')
    .attr('x', (d) => x(d.count) + 6)
    .attr('y', (d) => (y(d.name) ?? 0) + y.bandwidth() / 2 + 4)
    .attr('fill', '#e8ecff')
    .attr('font-size', '11px')
    .attr('font-family', 'monospace')
    .text((d) => d.count)

  // 渐变
  const defs = d3.select(svg).append('defs')
  const grad = defs.append('linearGradient').attr('id', 'purpleGrad').attr('x1', '0').attr('x2', '1').attr('y1', '0').attr('y2', '0')
  grad.append('stop').attr('offset', '0').attr('stop-color', '#9d4dff')
  grad.append('stop').attr('offset', '1').attr('stop-color', '#ff4d9d')
}

function renderBarHist() {
  const svg = barRef.value
  if (!svg) {
    return
  }
  const data = barHistogram.value
  const width = svg.parentElement?.clientWidth ?? 400
  const height = 200
  const margin = { top: 12, right: 16, bottom: 32, left: 36 }
  const innerW = width - margin.left - margin.right
  const innerH = height - margin.top - margin.bottom

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  const x = d3.scaleBand().domain(data.map((d) => d.range)).range([0, innerW]).padding(0.2)
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.count) ?? 1]).range([innerH, 0])

  g.selectAll('rect')
    .data(data)
    .enter()
    .append('rect')
    .attr('x', (d) => x(d.range) ?? 0)
    .attr('y', (d) => y(d.count))
    .attr('width', x.bandwidth())
    .attr('height', (d) => innerH - y(d.count))
    .attr('fill', '#00e5ff')
    .attr('rx', 2)

  g.selectAll('text.val')
    .data(data)
    .enter()
    .append('text')
    .attr('class', 'val')
    .attr('x', (d) => (x(d.range) ?? 0) + x.bandwidth() / 2)
    .attr('y', (d) => y(d.count) - 4)
    .attr('text-anchor', 'middle')
    .attr('fill', '#e8ecff')
    .attr('font-size', '11px')
    .text((d) => d.count)

  // x 轴
  g.append('g').attr('transform', `translate(0,${innerH})`).call(d3.axisBottom(x)).selectAll('text').attr('fill', '#a0a8c8').attr('font-size', '10px')
  g.selectAll('.domain, .tick line').attr('stroke', '#3a3f55')
}

function renderTierPie() {
  const svg = tierRef.value
  if (!svg || !tierDist.value.length) {
    return
  }
  const width = svg.parentElement?.clientWidth ?? 360
  const height = 240
  const radius = Math.min(width, height) / 2 - 20

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${width / 2},${height / 2})`)

  const colors = ['#9d4dff', '#ff4d9d', '#00e5ff', '#ffb74d', '#7fff7f', '#ff7f7f', '#4d9dff', '#9dff4d']
  const pie = d3.pie<{ label: string; count: number }>().value((d) => d.count).sort(null)
  const arc = d3.arc<d3.PieArcDatum<{ label: string; count: number }>>().innerRadius(radius * 0.5).outerRadius(radius)

  g.selectAll('path')
    .data(pie(tierDist.value))
    .enter()
    .append('path')
    .attr('d', arc)
    .attr('fill', (_, i) => colors[i % colors.length])
    .attr('stroke', '#05060d')
    .attr('stroke-width', 2)

  // labels with leader lines
  g.selectAll('text')
    .data(pie(tierDist.value))
    .enter()
    .append('text')
    .attr('transform', (d) => `translate(${arc.centroid(d)})`)
    .attr('text-anchor', 'middle')
    .attr('font-size', '10px')
    .attr('fill', '#fff')
    .text((d) => (d.data.count > 5 ? d.data.count : ''))

  // 中心总数
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('font-size', '24px')
    .attr('font-weight', 'bold')
    .attr('fill', '#e8ecff')
    .attr('dy', 0)
    .text(personas.value.length)
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('font-size', '11px')
    .attr('fill', '#a0a8c8')
    .attr('dy', 16)
    .text('总求职者')
}

watch(industryDist, () => setTimeout(renderIndustryChart, 50))
watch(barHistogram, () => setTimeout(renderBarHist, 50))
watch(tierDist, () => setTimeout(renderTierPie, 50))
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-7xl mx-auto">
      <!-- 顶部 -->
      <div class="flex items-end justify-between mb-8">
        <div>
          <p class="text-cyber-cyan text-sm tracking-widest mb-2">MARKET DASHBOARD</p>
          <h1 class="text-4xl font-bold title-gradient">市场看板</h1>
          <p class="text-ink-300 text-sm mt-2">
            春招平行宇宙是动态人才市场，公司和求职者随时加入退出。
            <span v-if="lastUpdated" class="text-ink-500 ml-2">最近刷新 {{ lastUpdated }}</span>
          </p>
        </div>
        <button class="btn-ghost text-sm" :disabled="loading" @click="reload">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>

      <!-- KPI 卡片 -->
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">入驻公司</p>
          <p class="text-4xl font-bold title-gradient mt-2">{{ stats.companies }}</p>
          <p class="text-ink-500 text-xs mt-1">总计 {{ stats.totalJDs }} 个 JD</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">活跃求职者</p>
          <p class="text-4xl font-bold title-gradient mt-2">{{ stats.personas }}</p>
          <p class="text-ink-500 text-xs mt-1">平均简历质量 {{ stats.avgQuality }}/100</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">平均招聘门槛</p>
          <p class="text-4xl font-bold title-gradient mt-2">{{ stats.avgBar }}<span class="text-2xl">/100</span></p>
          <p class="text-ink-500 text-xs mt-1">越高 = 越挑</p>
        </div>
        <div class="panel-glass p-5">
          <p class="text-ink-400 text-xs">估算 Offer 容量</p>
          <p class="text-4xl font-bold title-gradient mt-2">{{ stats.estimatedOffers }}</p>
          <p class="text-ink-500 text-xs mt-1">市场整体可发 offer 数（估算）</p>
        </div>
      </div>

      <!-- 行业分布 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">行业分布</h3>
            <span class="text-xs text-ink-500">按公司数量排序</span>
          </div>
          <svg ref="industryRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
        </div>
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">招聘门槛分布</h3>
            <span class="text-xs text-ink-500">高 bar 越多市场越挑</span>
          </div>
          <svg ref="barRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
        </div>
      </div>

      <!-- 学校 tier -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">求职者学校 tier 分布</h3>
            <span class="text-xs text-ink-500">竞争画像</span>
          </div>
          <svg ref="tierRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
        </div>
        <div class="panel-glass p-5">
          <div class="flex items-baseline justify-between mb-2">
            <h3 class="text-base text-ink-100">市场叙事</h3>
            <span class="text-xs text-ink-500">从数据读出的故事</span>
          </div>
          <div v-if="stats" class="text-ink-200 text-sm space-y-2 mt-4">
            <p>当前市场 <span class="text-cyber-cyan font-mono">{{ stats.companies }}</span> 家公司提供 <span class="text-cyber-cyan font-mono">{{ stats.totalJDs }}</span> 个 JD，吸引 <span class="text-cyber-cyan font-mono">{{ stats.personas }}</span> 名求职者。</p>
            <p>平均招聘门槛 <span class="text-cyber-cyan font-mono">{{ stats.avgBar }}/100</span>——
              <span v-if="stats.avgBar > 80">市场偏挑剔，低分候选人需更精准定位</span>
              <span v-else-if="stats.avgBar > 70">市场总体活跃，竞争激烈但机会充足</span>
              <span v-else>市场友好，多数公司愿意尝试</span>。
            </p>
            <p>求职者平均简历质量 <span class="text-cyber-cyan font-mono">{{ stats.avgQuality }}/100</span>，估算市场可消化的 offer 总数约 <span class="text-cyber-cyan font-mono">{{ stats.estimatedOffers }}</span>。</p>
            <p class="text-ink-400 text-xs mt-4 pt-3 border-t border-ink-800">
              市场状态实时变化：访问 <router-link to="/admin" class="text-cyber-cyan underline">市场治理</router-link> 可加入/退出公司或求职者。
            </p>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
