<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'

/**
 * Offer 数分布直方图（D3.js）。
 * x: 拿到的 offer 数量（0..8）
 * y: 在 1000 次平行宇宙中出现的次数
 */
const props = defineProps<{
  data: Record<string, number>  // key=offer 数，value=次数
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
  const width = container.clientWidth
  const height = 220
  const margin = { top: 10, right: 16, bottom: 32, left: 40 }
  const innerW = width - margin.left - margin.right
  const innerH = height - margin.top - margin.bottom

  // 清空
  d3.select(svg).selectAll('*').remove()

  const entries = Object.entries(props.data)
    .map(([k, v]) => ({ offers: +k, count: v }))
    .sort((a, b) => a.offers - b.offers)

  const x = d3.scaleBand<number>().domain(entries.map((d) => d.offers)).range([0, innerW]).padding(0.18)
  const yMax = d3.max(entries, (d) => d.count) ?? 1
  const y = d3.scaleLinear().domain([0, yMax * 1.1]).range([innerH, 0])

  const g = d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  // 渐变
  const defs = d3.select(svg).append('defs')
  const grad = defs.append('linearGradient').attr('id', 'barGradOffer').attr('x1', '0').attr('y1', '0').attr('x2', '0').attr('y2', '1')
  grad.append('stop').attr('offset', '0').attr('stop-color', '#00e5ff').attr('stop-opacity', 1)
  grad.append('stop').attr('offset', '1').attr('stop-color', '#9d4dff').attr('stop-opacity', 0.6)

  // bars
  g.selectAll('rect')
    .data(entries)
    .enter()
    .append('rect')
    .attr('x', (d) => x(d.offers) ?? 0)
    .attr('y', innerH)
    .attr('width', x.bandwidth())
    .attr('height', 0)
    .attr('fill', 'url(#barGradOffer)')
    .attr('rx', 3)
    .transition()
    .duration(700)
    .delay((_, i) => i * 60)
    .attr('y', (d) => y(d.count))
    .attr('height', (d) => innerH - y(d.count))

  // 数值标签
  g.selectAll('text.value')
    .data(entries)
    .enter()
    .append('text')
    .attr('class', 'value')
    .attr('x', (d) => (x(d.offers) ?? 0) + x.bandwidth() / 2)
    .attr('y', (d) => y(d.count) - 4)
    .attr('text-anchor', 'middle')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '10px')
    .attr('opacity', 0)
    .text((d) => d.count)
    .transition()
    .duration(700)
    .delay((_, i) => i * 60 + 400)
    .attr('opacity', 1)

  // x 轴
  g.append('g')
    .attr('transform', `translate(0,${innerH})`)
    .call(d3.axisBottom(x).tickFormat((d) => String(d)))
    .selectAll('text')
    .attr('fill', '#a0a8c8')
    .attr('font-size', '11px')
  g.selectAll('.domain, .tick line').attr('stroke', '#5f6786')

  // y 轴
  g.append('g')
    .call(d3.axisLeft(y).ticks(4))
    .selectAll('text')
    .attr('fill', '#5f6786')
    .attr('font-size', '10px')
  g.selectAll('.domain, .tick line').attr('stroke', '#3a3f55')

  // x label
  g.append('text')
    .attr('x', innerW / 2)
    .attr('y', innerH + 28)
    .attr('text-anchor', 'middle')
    .attr('fill', '#5f6786')
    .attr('font-size', '10px')
    .text('单次模拟拿到的 offer 数')
}

onMounted(() => render())
watch(() => props.data, render, { deep: true })
</script>

<template>
  <svg ref="svgRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
</template>
