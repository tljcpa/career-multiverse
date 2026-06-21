<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'

/**
 * 各公司 offer 概率横向 bar chart。
 * 关键设计：top 15 公司，按概率排序，颜色越亮表示越可能。
 */
const props = defineProps<{
  data: Array<{ company_code: string; probability: number }>
}>()

const svgRef = ref<SVGSVGElement | null>(null)

function render() {
  const svg = svgRef.value
  if (!svg) {
    return
  }
  // 防御：数据未到位时清空 svg 并退出，避免 d3 在空 domain 上拼出无效 path
  const _dataLen = Array.isArray(props.data) ? props.data.length : Object.keys(props.data ?? {}).length
  if (!_dataLen) {
    d3.select(svg).selectAll('*').remove()
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const top = [...props.data].sort((a, b) => b.probability - a.probability).slice(0, 15)
  const margin = { top: 8, right: 50, bottom: 8, left: 80 }
  const innerW = container.clientWidth - margin.left - margin.right
  const rowH = 22
  const innerH = top.length * rowH
  const height = innerH + margin.top + margin.bottom

  d3.select(svg).selectAll('*').remove()

  const x = d3.scaleLinear().domain([0, 1]).range([0, innerW])
  const y = d3.scaleBand<string>().domain(top.map((d) => d.company_code)).range([0, innerH]).padding(0.25)

  d3.select(svg).attr('viewBox', `0 0 ${container.clientWidth} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  // 背景轨道
  g.selectAll('rect.track')
    .data(top)
    .enter()
    .append('rect')
    .attr('class', 'track')
    .attr('x', 0)
    .attr('y', (d) => y(d.company_code) ?? 0)
    .attr('width', innerW)
    .attr('height', y.bandwidth())
    .attr('fill', '#0f1424')
    .attr('rx', 2)

  // 数据条
  const colorScale = d3.scaleLinear<string>()
    .domain([0, 0.5, 1])
    .range(['#5f6786', '#00e5ff', '#9d4dff'])

  g.selectAll('rect.bar')
    .data(top)
    .enter()
    .append('rect')
    .attr('class', 'bar')
    .attr('x', 0)
    .attr('y', (d) => y(d.company_code) ?? 0)
    .attr('height', y.bandwidth())
    .attr('width', 0)
    .attr('fill', (d) => colorScale(d.probability))
    .attr('rx', 2)
    .transition()
    .duration(800)
    .delay((_, i) => i * 40)
    .attr('width', (d) => x(d.probability))

  // 数值
  g.selectAll('text.val')
    .data(top)
    .enter()
    .append('text')
    .attr('class', 'val')
    .attr('x', (d) => x(d.probability) + 6)
    .attr('y', (d) => (y(d.company_code) ?? 0) + y.bandwidth() / 2)
    .attr('dominant-baseline', 'middle')
    .attr('fill', '#e8ecff')
    .attr('font-size', '11px')
    .attr('opacity', 0)
    .text((d) => `${(d.probability * 100).toFixed(0)}%`)
    .transition()
    .duration(600)
    .delay((_, i) => i * 40 + 500)
    .attr('opacity', 1)

  // y 轴标签（公司名）
  g.selectAll('text.label')
    .data(top)
    .enter()
    .append('text')
    .attr('class', 'label')
    .attr('x', -6)
    .attr('y', (d) => (y(d.company_code) ?? 0) + y.bandwidth() / 2)
    .attr('text-anchor', 'end')
    .attr('dominant-baseline', 'middle')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '11px')
    .text((d) => d.company_code)
}

onMounted(render)
watch(() => props.data, render, { deep: true })
</script>

<template>
  <svg ref="svgRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
</template>
