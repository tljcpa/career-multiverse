<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'

/**
 * 决策树（Force-directed graph）。
 *
 * 给定一组 journey，把"应聘公司 → 是否通过简历筛 → 是否拿 offer → 是否接受"
 * 拆成多层节点，用 D3 force 布局展示。
 */
interface Journey {
  company_code: string
  final_stage: string
  offer_salary_wan: number
  is_final_destination: boolean
}

const props = defineProps<{
  journeys: Journey[]
}>()

const svgRef = ref<SVGSVGElement | null>(null)

interface NodeData extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: 'root' | 'company' | 'screen' | 'offer' | 'accept' | 'reject'
  finalDest?: boolean
}
interface LinkData extends d3.SimulationLinkDatum<NodeData> {
  source: string | NodeData
  target: string | NodeData
}

function render() {
  const svg = svgRef.value
  if (!svg) {
    return
  }
  const container = svg.parentElement
  if (!container) {
    return
  }
  const width = container.clientWidth
  const height = 360

  d3.select(svg).selectAll('*').remove()
  d3.select(svg).attr('viewBox', `0 0 ${width} ${height}`)

  const nodes: NodeData[] = [{ id: 'root', label: 'YOU', type: 'root' }]
  const links: LinkData[] = []

  for (const j of props.journeys) {
    const compId = `comp_${j.company_code}`
    nodes.push({ id: compId, label: j.company_code, type: 'company' })
    links.push({ source: 'root', target: compId })

    if (j.final_stage === 'rejected' && j.offer_salary_wan === 0) {
      const failId = `${compId}_screen_fail`
      nodes.push({ id: failId, label: '未过筛', type: 'reject' })
      links.push({ source: compId, target: failId })
      continue
    }
    if (j.offer_salary_wan > 0) {
      const offerId = `${compId}_offer`
      nodes.push({ id: offerId, label: `${j.offer_salary_wan}万`, type: 'offer' })
      links.push({ source: compId, target: offerId })
      if (j.is_final_destination) {
        const acceptId = `${compId}_accept`
        nodes.push({ id: acceptId, label: '接受！', type: 'accept', finalDest: true })
        links.push({ source: offerId, target: acceptId })
      } else if (j.final_stage === 'rejected') {
        const rejId = `${compId}_rej`
        nodes.push({ id: rejId, label: '面试落败', type: 'reject' })
        links.push({ source: offerId, target: rejId })
      }
    }
  }

  const sim = d3.forceSimulation<NodeData>(nodes)
    .force('link', d3.forceLink<NodeData, LinkData>(links).id((d) => d.id).distance(50).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(22))

  const linkSel = d3.select(svg).append('g')
    .selectAll('line')
    .data(links)
    .enter()
    .append('line')
    .attr('stroke', '#3a3f55')
    .attr('stroke-width', 1)

  const nodeSel = d3.select(svg).append('g')
    .selectAll('g')
    .data(nodes)
    .enter()
    .append('g')

  nodeSel.append('circle')
    .attr('r', (d) => {
      if (d.type === 'root') {
        return 18
      }
      if (d.finalDest) {
        return 14
      }
      return 10
    })
    .attr('fill', (d) => {
      switch (d.type) {
        case 'root': return '#00e5ff'
        case 'company': return '#9d4dff'
        case 'offer': return '#ffcc4d'
        case 'accept': return '#4dffaa'
        case 'reject': return '#ff4d9d'
        default: return '#5f6786'
      }
    })
    .attr('stroke', '#05060d')
    .attr('stroke-width', 2)

  nodeSel.append('text')
    .text((d) => d.label)
    .attr('text-anchor', 'middle')
    .attr('dy', (d) => (d.type === 'root' ? 4 : -14))
    .attr('fill', (d) => (d.type === 'root' ? '#000' : '#e8ecff'))
    .attr('font-size', (d) => (d.type === 'root' ? '11px' : '10px'))
    .attr('font-weight', (d) => (d.finalDest ? 'bold' : 'normal'))

  sim.on('tick', () => {
    linkSel
      .attr('x1', (d) => (d.source as NodeData).x ?? 0)
      .attr('y1', (d) => (d.source as NodeData).y ?? 0)
      .attr('x2', (d) => (d.target as NodeData).x ?? 0)
      .attr('y2', (d) => (d.target as NodeData).y ?? 0)
    nodeSel.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
  })
}

onMounted(render)
watch(() => props.journeys, render, { deep: true })
</script>

<template>
  <svg ref="svgRef" class="w-full block" preserveAspectRatio="xMidYMid meet" />
</template>
