<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'

/**
 * 最终去向分布饼图（实际用环形 donut）。
 * 显示 top 8 + 其他。
 */
const props = defineProps<{
  data: Record<string, number>
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
  const height = 280
  const radius = Math.min(width, height) / 2 - 10

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)

  // top 8 + 其他
  const entries = Object.entries(props.data).map(([k, v]) => ({ name: k, value: v }))
  entries.sort((a, b) => b.value - a.value)
  const top = entries.slice(0, 8)
  const otherSum = entries.slice(8).reduce((s, e) => s + e.value, 0)
  if (otherSum > 0) {
    top.push({ name: '其他', value: otherSum })
  }

  const palette = ['#00e5ff', '#9d4dff', '#ff4d9d', '#ffcc4d', '#4dffaa', '#ff7c4d', '#4d9dff', '#b84dff', '#5f6786']
  const color = d3.scaleOrdinal<string>().domain(top.map((d) => d.name)).range(palette)

  const g = d3.select(svg).append('g').attr('transform', `translate(${width / 2},${height / 2})`)

  const pie = d3.pie<{ name: string; value: number }>().value((d) => d.value).sort(null)
  const arc = d3.arc<d3.PieArcDatum<{ name: string; value: number }>>()
    .innerRadius(radius * 0.55)
    .outerRadius(radius)
  const arcHover = d3.arc<d3.PieArcDatum<{ name: string; value: number }>>()
    .innerRadius(radius * 0.55)
    .outerRadius(radius * 1.05)

  const total = d3.sum(top, (d) => d.value)

  const paths = g.selectAll('path')
    .data(pie(top))
    .enter()
    .append('path')
    .attr('fill', (d) => color(d.data.name))
    .attr('stroke', '#05060d')
    .attr('stroke-width', 2)
    .attr('opacity', 0.9)
    .each(function (d) {
      // 初始角度都从 0 开始，方便动画
      ;(this as SVGPathElement & { _current: d3.PieArcDatum<{ name: string; value: number }> })._current = { ...d, startAngle: 0, endAngle: 0 }
    })

  paths.transition()
    .duration(800)
    .attrTween('d', function (d) {
      const self = this as SVGPathElement & { _current: d3.PieArcDatum<{ name: string; value: number }> }
      const i = d3.interpolate(self._current, d)
      self._current = i(1)
      return (t: number) => arc(i(t)) ?? ''
    })

  paths.on('mouseenter', function () {
    d3.select(this).transition().duration(180).attr('d', arcHover as unknown as () => string)
  }).on('mouseleave', function () {
    d3.select(this).transition().duration(180).attr('d', arc as unknown as () => string)
  })

  // 中心字幕：低调显示总样本数（不再占主导）
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('fill', '#5f6786')
    .attr('font-size', '11px')
    .attr('y', 0)
    .text('1000 次模拟')
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('fill', '#5f6786')
    .attr('font-size', '9px')
    .attr('y', 14)
    .text('最终去向占比')

  // 图例（两列，避免单列被 donut 遮挡看不清）
  const legend = d3.select(svg).append('g').attr('transform', `translate(8, 8)`)
  const colPerSide = Math.ceil(top.length / 2)
  top.forEach((d, i) => {
    const col = Math.floor(i / colPerSide)
    const row = legend.append('g').attr('transform', `translate(${col * 120}, ${(i % colPerSide) * 18})`)
    row.append('rect').attr('width', 10).attr('height', 10).attr('fill', color(d.name)).attr('rx', 2)
    row.append('text')
      .attr('x', 15)
      .attr('y', 9)
      .attr('fill', '#c4ccdf')
      .attr('font-size', '11px')
      .text(`${d.name} ${((d.value / total) * 100).toFixed(0)}%`)
  })
}

onMounted(render)
watch(() => props.data, render, { deep: true })
</script>

<template>
  <svg ref="svgRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
</template>
