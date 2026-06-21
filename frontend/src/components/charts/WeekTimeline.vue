<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'

/**
 * 接受 offer 的周次时间线（area chart）。
 */
const props = defineProps<{
  data: Array<{ week: number; count: number }>
}>()

const svgRef = ref<SVGSVGElement | null>(null)

function render() {
  const svg = svgRef.value
  if (!svg) {
    return
  }
  // data 为空时早返回，避免 d3.area / scale 在空 domain 上生成无效 path "L... Z"
  // 触发场景：Report 首次挂载时 aggregate API 还没返回，data=[]
  if (!props.data || props.data.length === 0) {
    d3.select(svg).selectAll('*').remove()
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const width = container.clientWidth
  const height = 200
  const margin = { top: 12, right: 16, bottom: 28, left: 36 }
  const innerW = width - margin.left - margin.right
  const innerH = height - margin.top - margin.bottom

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)
  const g = d3.select(svg).append('g').attr('transform', `translate(${margin.left},${margin.top})`)

  const x = d3.scaleLinear().domain(d3.extent(props.data, (d) => d.week) as [number, number]).range([0, innerW])
  const y = d3.scaleLinear().domain([0, (d3.max(props.data, (d) => d.count) ?? 1) * 1.15]).range([innerH, 0])

  // gradient
  const defs = d3.select(svg).append('defs')
  const grad = defs.append('linearGradient').attr('id', 'areaGrad').attr('x1', '0').attr('y1', '0').attr('x2', '0').attr('y2', '1')
  grad.append('stop').attr('offset', '0').attr('stop-color', '#9d4dff').attr('stop-opacity', 0.6)
  grad.append('stop').attr('offset', '1').attr('stop-color', '#9d4dff').attr('stop-opacity', 0)

  const area = d3.area<{ week: number; count: number }>()
    .x((d) => x(d.week))
    .y0(innerH)
    .y1((d) => y(d.count))
    .curve(d3.curveCatmullRom)

  const line = d3.line<{ week: number; count: number }>()
    .x((d) => x(d.week))
    .y((d) => y(d.count))
    .curve(d3.curveCatmullRom)

  g.append('path')
    .datum(props.data)
    .attr('fill', 'url(#areaGrad)')
    .attr('d', area)

  g.append('path')
    .datum(props.data)
    .attr('fill', 'none')
    .attr('stroke', '#9d4dff')
    .attr('stroke-width', 2)
    .attr('d', line)

  // dots
  g.selectAll('circle')
    .data(props.data)
    .enter()
    .append('circle')
    .attr('cx', (d) => x(d.week))
    .attr('cy', (d) => y(d.count))
    .attr('r', 3)
    .attr('fill', '#ff4d9d')
    .attr('stroke', '#05060d')
    .attr('stroke-width', 1.5)

  // axes
  g.append('g').attr('transform', `translate(0,${innerH})`).call(d3.axisBottom(x).ticks(props.data.length).tickFormat((d) => `W${d}`)).selectAll('text').attr('fill', '#a0a8c8').attr('font-size', '10px')
  g.append('g').call(d3.axisLeft(y).ticks(4)).selectAll('text').attr('fill', '#5f6786').attr('font-size', '10px')
  g.selectAll('.domain, .tick line').attr('stroke', '#3a3f55')
}

onMounted(render)
watch(() => props.data, render, { deep: true })
</script>

<template>
  <svg ref="svgRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
</template>
