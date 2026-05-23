<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as THREE from 'three'
import type { Company } from '@/types/contracts'

/**
 * 3D 沙盘核心组件（Three.js）。
 *
 * 设计决策：
 * 1. 公司分布：分行业聚成星团（cluster），同行业 5-7 家围一圈；星团再围中心 user 化身分布
 *    这样视觉上有"行业宇宙"的感觉，不是均匀散点
 * 2. user 化身：中心 octahedron（八面体）+ 内部小球，旋转 + pulse
 * 3. 投递动画：从 user 发出粒子流到目标公司，粒子用 BufferGeometry + 自定义着色（移动 alpha）
 * 4. 公司节点 hover：scale + glow；click：emit 给父组件
 * 5. 性能：所有公司节点用 Mesh，但材质共享（每个 industry 一种颜色）
 *
 * 不用 GLTFLoader 加载 3D 模型：体积大、需要静态托管、加载延迟。
 * 用原始几何体足够表达概念。
 */
const props = defineProps<{
  companies: Company[]
  // 当前周次（用于驱动投递动画时机）
  currentWeek: number
  // 当前已投递的公司 codes
  appliedCompanies: string[]
}>()

const emit = defineEmits<{
  (e: 'company-click', company: Company): void
  (e: 'company-hover', company: Company | null): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)

// Three.js 上下文：保留在 ref 外，避免响应式开销
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let rafId = 0
let raycaster: THREE.Raycaster | null = null
let pointer = new THREE.Vector2()

// 公司节点 mesh map：code_name → mesh
const companyMeshes = new Map<string, THREE.Mesh>()
// 公司位置 map：用于投递粒子目标点
const companyPositions = new Map<string, THREE.Vector3>()
// 当前 hover 中的 mesh
let hoveredMesh: THREE.Mesh | null = null

// 中心化身
let avatarGroup: THREE.Group | null = null

// 行业 → 颜色
const industryColors: Record<string, number> = {
  '互联网-短视频/直播': 0xff4d9d,
  '互联网-电商': 0xff7c4d,
  '互联网-社交/内容社区': 0xffcc4d,
  '互联网-搜索/工具/SaaS': 0x4dffaa,
  '互联网-本地生活/外卖': 0xff9d4d,
  '互联网-长视频': 0xb84dff,
  '互联网-在线音乐': 0xff4dff,
  '游戏': 0x9d4dff,
  'AI-基础模型': 0x00e5ff,
  'AI-应用层（Agent/RAG/垂直工具）': 0x4dccff,
  'AI-医疗影像': 0x4dffe5,
  'AI-制药': 0x4dffb8,
  'AI-具身智能/机器人': 0x6e4dff,
  '硬件-半导体设计/EDA': 0xffd700,
  '硬件-消费电子/品牌': 0xff8c4d,
  '硬件-通信/网络设备': 0x4d9dff,
  '硬件-工业软件/精密仪器': 0xc4ff4d,
  '通信/基础设施': 0x4d5fff,
  '新能源': 0x4dffff,
  '新能源车': 0x4dff7c,
  '金融': 0xffe54d,
  '金融-银行/保险科技': 0xffcc7c,
  '咨询': 0xb89d4d,
  '快消': 0xffb84d,
  '跨境电商/出海品牌': 0xff7cff,
  '生物医药/CRO': 0x4dffd1,
  '教育科技/在线教育': 0x7cffe5,
  '航空航天/军工': 0xa0a8c8,
  '国央企-能源/电网': 0x6da8c8,
  '政府/事业单位（数字政务方向）': 0x8a9bc4,
  '外企-科技/中国研发中心': 0x9d4dff
}

function colorForIndustry(industry: string): number {
  if (industry in industryColors) {
    return industryColors[industry]
  }
  return 0x9d4dff
}

// 用 hash 把字符串映射成稳定颜色（fallback）

// ---------- 场景初始化 ----------
function initScene() {
  const container = containerRef.value
  if (!container) {
    return
  }
  const w = container.clientWidth
  const h = container.clientHeight

  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x05060d, 0.012)

  camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 500)
  camera.position.set(0, 18, 45)
  camera.lookAt(0, 0, 0)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  renderer.setClearColor(0x000000, 0)
  container.appendChild(renderer.domElement)

  raycaster = new THREE.Raycaster()

  // 环境光 + 主光
  scene.add(new THREE.AmbientLight(0xffffff, 0.4))
  const dir = new THREE.DirectionalLight(0xffffff, 0.6)
  dir.position.set(20, 30, 20)
  scene.add(dir)

  // 中心 user 化身
  buildAvatar()

  // 公司节点
  buildCompanyNodes()

  // 监听
  container.addEventListener('mousemove', onPointerMove)
  container.addEventListener('click', onPointerClick)
  window.addEventListener('resize', onResize)
}

function buildAvatar() {
  if (!scene) {
    return
  }
  avatarGroup = new THREE.Group()

  // 外层八面体（线框 + 半透明）
  const octGeo = new THREE.OctahedronGeometry(2.2, 0)
  const octMat = new THREE.MeshBasicMaterial({
    color: 0x00e5ff,
    wireframe: true,
    transparent: true,
    opacity: 0.8
  })
  const oct = new THREE.Mesh(octGeo, octMat)
  avatarGroup.add(oct)

  // 内层小球（发光）
  const coreGeo = new THREE.SphereGeometry(0.8, 32, 32)
  const coreMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff })
  const core = new THREE.Mesh(coreGeo, coreMat)
  avatarGroup.add(core)

  // 光晕（用透明 sphere 模拟 glow）
  const glowGeo = new THREE.SphereGeometry(1.5, 32, 32)
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x00e5ff,
    transparent: true,
    opacity: 0.2
  })
  const glow = new THREE.Mesh(glowGeo, glowMat)
  avatarGroup.add(glow)

  // 标签（用 sprite + canvas texture）
  const label = makeLabelSprite('你的数字分身', '#00e5ff')
  label.position.set(0, 3.5, 0)
  label.scale.set(8, 2, 1)
  avatarGroup.add(label)

  scene.add(avatarGroup)
}

function makeLabelSprite(text: string, color: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'rgba(15, 20, 36, 0.9)'
  ctx.fillRect(0, 0, 512, 128)
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.strokeRect(2, 2, 508, 124)
  ctx.font = 'bold 56px PingFang SC, sans-serif'
  ctx.fillStyle = color
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 256, 64)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true })
  return new THREE.Sprite(mat)
}

function buildCompanyNodes() {
  if (!scene) {
    return
  }
  // 按行业聚类
  const byIndustry = new Map<string, Company[]>()
  for (const c of props.companies) {
    if (!byIndustry.has(c.industry)) {
      byIndustry.set(c.industry, [])
    }
    byIndustry.get(c.industry)!.push(c)
  }

  const industries = Array.from(byIndustry.keys())
  // 行业簇围绕中心环形分布，cluster 中心半径 R1=28
  const clusterRadius = 28
  // 簇内：公司在小圆上分布，半径 R2=4..6
  let idx = 0
  for (const industry of industries) {
    const companies = byIndustry.get(industry)!
    const clusterAngle = (idx / industries.length) * Math.PI * 2
    // 给每个簇加点 y 偏移让宇宙立体起来
    const clusterY = (Math.sin(idx * 1.7) + Math.cos(idx * 0.9)) * 4
    const cx = Math.cos(clusterAngle) * clusterRadius
    const cz = Math.sin(clusterAngle) * clusterRadius
    const r2 = 3 + Math.min(companies.length * 0.6, 4)

    companies.forEach((company, i) => {
      const localAngle = (i / companies.length) * Math.PI * 2
      const px = cx + Math.cos(localAngle) * r2
      const pz = cz + Math.sin(localAngle) * r2
      const py = clusterY + (Math.sin(i * 2.3) * 1.2)

      const mesh = makeCompanyNode(company)
      mesh.position.set(px, py, pz)
      mesh.userData.company = company
      mesh.userData.basePos = new THREE.Vector3(px, py, pz)
      scene!.add(mesh)
      companyMeshes.set(company.code_name, mesh)
      companyPositions.set(company.code_name, mesh.position.clone())
    })
    idx++
  }
}

function makeCompanyNode(company: Company): THREE.Mesh {
  // 节点大小用 hiring_bar 反映：bar 越高节点越大
  const bar = company.hidden_signals.hiring_bar ?? 75
  const size = 0.5 + (bar / 100) * 0.8

  // 用 icosahedron 模拟"水晶"
  const geo = new THREE.IcosahedronGeometry(size, 0)
  const color = colorForIndustry(company.industry)
  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.7,
    roughness: 0.3,
    metalness: 0.6
  })
  const mesh = new THREE.Mesh(geo, mat)

  // glow 子物体
  const glowGeo = new THREE.SphereGeometry(size * 1.6, 16, 16)
  const glowMat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.18
  })
  const glow = new THREE.Mesh(glowGeo, glowMat)
  mesh.add(glow)

  return mesh
}

// ---------- 粒子投递动画 ----------
interface Projectile {
  particles: THREE.Points
  positions: Float32Array
  velocities: Float32Array
  startTime: number
  duration: number
  target: THREE.Vector3
}
let projectiles: Projectile[] = []

function launchProjectile(targetCompanyCode: string) {
  if (!scene) {
    return
  }
  const target = companyPositions.get(targetCompanyCode)
  if (!target) {
    return
  }

  const n = 30
  const positions = new Float32Array(n * 3)
  const velocities = new Float32Array(n * 3)
  // 从 user 位置（0,0,0）出发
  for (let i = 0; i < n; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 0.5
    positions[i * 3 + 1] = (Math.random() - 0.5) * 0.5
    positions[i * 3 + 2] = (Math.random() - 0.5) * 0.5
  }
  const direction = target.clone().normalize()
  const speed = target.length() / 1.5
  for (let i = 0; i < n; i++) {
    velocities[i * 3] = direction.x * speed
    velocities[i * 3 + 1] = direction.y * speed
    velocities[i * 3 + 2] = direction.z * speed
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  // 用 industry 颜色
  const company = props.companies.find((c) => c.code_name === targetCompanyCode)
  const color = company ? colorForIndustry(company.industry) : 0x00e5ff

  const mat = new THREE.PointsMaterial({
    color,
    size: 0.4,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  })
  const points = new THREE.Points(geo, mat)
  scene.add(points)

  projectiles.push({
    particles: points,
    positions,
    velocities,
    startTime: performance.now(),
    duration: 1500,
    target: target.clone()
  })
}

function updateProjectiles(dt: number) {
  if (!scene) {
    return
  }
  const now = performance.now()
  projectiles = projectiles.filter((p) => {
    const age = now - p.startTime
    const t = age / p.duration
    if (t > 1) {
      scene!.remove(p.particles)
      p.particles.geometry.dispose()
      ;(p.particles.material as THREE.Material).dispose()
      return false
    }
    // 让粒子向 target 收敛（lerp + 减速）
    const posAttr = p.particles.geometry.getAttribute('position') as THREE.BufferAttribute
    const arr = posAttr.array as Float32Array
    for (let i = 0; i < arr.length; i += 3) {
      // 朝 target 拖拽（带轻微抖动）
      arr[i] += (p.target.x - arr[i]) * dt * 2.5 + (Math.random() - 0.5) * 0.05
      arr[i + 1] += (p.target.y - arr[i + 1]) * dt * 2.5 + (Math.random() - 0.5) * 0.05
      arr[i + 2] += (p.target.z - arr[i + 2]) * dt * 2.5 + (Math.random() - 0.5) * 0.05
    }
    posAttr.needsUpdate = true
    ;(p.particles.material as THREE.PointsMaterial).opacity = 0.9 * (1 - t)
    return true
  })
}

// ---------- 渲染循环 ----------
let lastFrameTime = 0
function animate(t: number) {
  if (!renderer || !scene || !camera) {
    return
  }
  const dt = lastFrameTime ? (t - lastFrameTime) / 1000 : 0
  lastFrameTime = t

  // 化身：旋转 + pulse
  if (avatarGroup) {
    avatarGroup.rotation.y += dt * 0.4
    avatarGroup.rotation.x += dt * 0.2
    const pulseScale = 1 + Math.sin(t / 600) * 0.05
    avatarGroup.scale.setScalar(pulseScale)
  }

  // 公司节点：自旋
  companyMeshes.forEach((mesh) => {
    mesh.rotation.y += dt * 0.5
  })

  // 投递粒子
  updateProjectiles(dt)

  // 缓慢绕轨拍摄
  const radius = 45
  const camAngle = t / 16000
  camera.position.x = Math.sin(camAngle) * radius
  camera.position.z = Math.cos(camAngle) * radius
  camera.lookAt(0, 0, 0)

  renderer.render(scene, camera)
  rafId = requestAnimationFrame(animate)
}

// ---------- 交互 ----------
function onPointerMove(e: MouseEvent) {
  const container = containerRef.value
  if (!container || !camera || !raycaster) {
    return
  }
  const rect = container.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(pointer, camera)
  const meshes = Array.from(companyMeshes.values())
  const intersects = raycaster.intersectObjects(meshes, false)

  if (intersects.length > 0) {
    const mesh = intersects[0].object as THREE.Mesh
    if (hoveredMesh !== mesh) {
      // 取消上一个的高亮
      if (hoveredMesh) {
        hoveredMesh.scale.setScalar(1)
      }
      hoveredMesh = mesh
      mesh.scale.setScalar(1.6)
      container.style.cursor = 'pointer'
      emit('company-hover', mesh.userData.company)
    }
  } else {
    if (hoveredMesh) {
      hoveredMesh.scale.setScalar(1)
      hoveredMesh = null
      container.style.cursor = 'default'
      emit('company-hover', null)
    }
  }
}

function onPointerClick() {
  if (hoveredMesh && hoveredMesh.userData.company) {
    emit('company-click', hoveredMesh.userData.company)
  }
}

function onResize() {
  const container = containerRef.value
  if (!container || !renderer || !camera) {
    return
  }
  const w = container.clientWidth
  const h = container.clientHeight
  renderer.setSize(w, h)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

// ---------- 监听投递列表变化 → 触发动画 ----------
let lastAppliedSet = new Set<string>()
watch(
  () => props.appliedCompanies,
  (newList) => {
    for (const code of newList) {
      if (!lastAppliedSet.has(code)) {
        launchProjectile(code)
      }
    }
    lastAppliedSet = new Set(newList)
  },
  { deep: true }
)

// ---------- 生命周期 ----------
onMounted(() => {
  // 等下一帧让容器获得正确尺寸
  requestAnimationFrame(() => {
    initScene()
    rafId = requestAnimationFrame(animate)
  })
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  window.removeEventListener('resize', onResize)
  const container = containerRef.value
  if (container) {
    container.removeEventListener('mousemove', onPointerMove)
    container.removeEventListener('click', onPointerClick)
  }
  // 清理 Three 资源
  companyMeshes.forEach((mesh) => {
    mesh.geometry.dispose()
    ;(mesh.material as THREE.Material).dispose()
  })
  companyMeshes.clear()
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
  }
})

// 暴露给父组件的方法
defineExpose({
  launchProjectile
})
</script>

<template>
  <div ref="containerRef" class="w-full h-full relative" />
</template>
