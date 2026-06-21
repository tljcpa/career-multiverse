<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'

/**
 * 全局星空背景层。
 *
 * 实现：纯 Canvas 2D（不用 Three.js）。
 * 理由：
 * - 仅做背景星点闪烁，Canvas 2D 已经够用，能省一整个 WebGL context
 * - 主沙盘组件再用 Three.js，避免两个 WebGL canvas 争抢资源
 * - 性能：每帧只重绘点，60fps 没压力
 */
const canvasRef = ref<HTMLCanvasElement | null>(null)
let rafId = 0
let stars: Array<{ x: number; y: number; r: number; tw: number; phase: number }> = []

function resize() {
  const canvas = canvasRef.value
  if (!canvas) {
    return
  }
  const w = window.innerWidth
  const h = window.innerHeight
  const dpr = window.devicePixelRatio || 1
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.scale(dpr, dpr)
  }
  // 星点密度：每 6000 平方像素一个
  const n = Math.floor((w * h) / 6000)
  stars = []
  for (let i = 0; i < n; i++) {
    stars.push({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.4 + 0.2,
      tw: Math.random() * 0.04 + 0.005,
      phase: Math.random() * Math.PI * 2
    })
  }
}

function frame(t: number) {
  const canvas = canvasRef.value
  if (!canvas) {
    return
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return
  }
  const w = window.innerWidth
  const h = window.innerHeight
  // 深空底色（不完全透明，留些层次）
  ctx.fillStyle = 'rgba(5, 6, 13, 1)'
  ctx.fillRect(0, 0, w, h)

  // 星云：两个柔光圆斑
  const g1 = ctx.createRadialGradient(w * 0.2, h * 0.3, 0, w * 0.2, h * 0.3, 350)
  g1.addColorStop(0, 'rgba(157, 77, 255, 0.10)')
  g1.addColorStop(1, 'rgba(157, 77, 255, 0)')
  ctx.fillStyle = g1
  ctx.fillRect(0, 0, w, h)

  const g2 = ctx.createRadialGradient(w * 0.8, h * 0.7, 0, w * 0.8, h * 0.7, 400)
  g2.addColorStop(0, 'rgba(0, 229, 255, 0.08)')
  g2.addColorStop(1, 'rgba(0, 229, 255, 0)')
  ctx.fillStyle = g2
  ctx.fillRect(0, 0, w, h)

  // 星点
  for (const s of stars) {
    s.phase += s.tw
    const alpha = 0.5 + 0.5 * Math.sin(s.phase)
    ctx.beginPath()
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(232, 236, 255, ${alpha})`
    ctx.fill()
  }

  rafId = requestAnimationFrame(frame)
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  rafId = requestAnimationFrame(frame)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  cancelAnimationFrame(rafId)
})
</script>

<template>
  <canvas ref="canvasRef" class="block" />
</template>
