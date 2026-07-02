<script setup lang="ts">
import { computed } from 'vue'

/**
 * 三端切换导航条（个人 / 企业 / 学校）—— 可复用组件。
 *
 * 用途：在三端各自的落地页 / 主界面顶部提供统一的视角切换。
 * 视觉与全站深色赛博风一致：半透明玻璃条 + 青边高亮 + 色块指示（不用 emoji / 图标字体）。
 *
 * 设计取舍：
 * - 组件本身不做路由跳转的"业务判断"，只负责渲染 + 用 router-link 导航，
 *   高亮态由当前 $route.path 与每个角色的 to 前缀比对得出（前缀匹配，容忍子路由）。
 * - 每个角色配一个主题色（个人青 / 企业紫 / 学校金），选中时用该色做描边 + 底部指示条 + 前置色块，
 *   未选中态统一低饱和，避免三色同时抢眼（"克制不堆砌"）。
 * - active 也可由父组件用 activeRole 显式指定（比如落地页想强制某个态），不传则走路由推断。
 */

interface RoleItem {
  key: 'personal' | 'enterprise' | 'school'
  label: string
  sub: string
  to: string
  // 主题色的 hex（用于色块 / 描边内联样式，避免 UnoCSS 动态类名被 tree-shake）
  color: string
}

const props = defineProps<{
  // 可选：父组件显式指定当前激活的角色；不传则按路由前缀推断
  activeRole?: 'personal' | 'enterprise' | 'school'
}>()

// 三端定义。to 用作路由前缀匹配的基准。
const roles: RoleItem[] = [
  { key: 'personal', label: '个人', sub: '求职者', to: '/upload', color: '#00e5ff' },
  { key: 'enterprise', label: '企业', sub: '招聘方', to: '/enterprise', color: '#9d4dff' },
  { key: 'school', label: '学校', sub: '就业中心', to: '/school', color: '#ffcc4d' }
]

// 当前激活角色：优先用 props.activeRole，否则用路由推断在模板里逐项计算
function isActive(role: RoleItem, currentPath: string): boolean {
  if (props.activeRole) {
    return props.activeRole === role.key
  }
  // 前缀匹配：/upload、/enterprise/xxx 都能命中对应端
  return currentPath === role.to || currentPath.startsWith(role.to + '/')
}

// 把 hex 转成低透明度的 rgba，用于选中态的柔光底色（避免写死一堆类名）
const rolesWithTint = computed(() =>
  roles.map((r) => {
    return {
      ...r,
      // 选中态背景柔光（约 10% 透明度）
      tint: hexToRgba(r.color, 0.1),
      // 选中态描边（约 45% 透明度）
      border: hexToRgba(r.color, 0.45)
    }
  })
)

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
</script>

<template>
  <div class="tri-role-nav inline-flex items-center gap-1 p-1 rounded-full panel-glass">
    <router-link
      v-for="role in rolesWithTint"
      :key="role.key"
      :to="role.to"
      class="tri-role-item relative flex items-center gap-2.5 px-5 py-2 rounded-full transition-all duration-200"
      :class="isActive(role, $route.path)
        ? 'is-active'
        : 'text-ink-300 hover:text-ink-100 hover:bg-white/2'"
      :style="isActive(role, $route.path)
        ? { background: role.tint, border: `1px solid ${role.border}` }
        : { border: '1px solid transparent' }"
    >
      <!-- 前置色块：形状 + 色彩区分三端，不用图标字体 -->
      <span
        class="w-2 h-2 rounded-sm flex-shrink-0 transition-all"
        :style="{
          background: role.color,
          boxShadow: isActive(role, $route.path) ? `0 0 8px ${role.color}` : 'none',
          opacity: isActive(role, $route.path) ? 1 : 0.5
        }"
      />
      <span class="flex flex-col leading-none">
        <span
          class="text-sm font-semibold"
          :style="isActive(role, $route.path) ? { color: role.color } : {}"
        >{{ role.label }}</span>
        <span class="text-[10px] text-ink-500 mt-0.5">{{ role.sub }}</span>
      </span>
    </router-link>
  </div>
</template>

<style scoped>
/* active 态额外的顶部微光（用伪元素，避免污染布局） */
.tri-role-item.is-active {
  backdrop-filter: blur(4px);
}
</style>
