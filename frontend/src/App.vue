<script setup lang="ts">
// 根组件：纯路由 outlet + 背景星空层
// 把星空背景做成全局共享，因为 Upload/Finetuning/Sandbox/Report 都需要"宇宙感"
import StarField from '@/components/StarField.vue'
</script>

<template>
  <div class="app-root relative w-full h-full">
    <!-- 全局星空背景，z-index 最低 -->
    <StarField class="fixed inset-0 -z-10" />

    <!-- 顶部导航栏（仅显示当前阶段，非交互式） -->
    <header class="fixed top-0 left-0 right-0 z-50 px-8 py-4 flex items-center justify-between bg-space-bg/40 backdrop-blur-sm border-b border-white/5">
      <div class="flex items-center gap-3">
        <div class="w-2 h-2 rounded-full bg-cyber-cyan animate-pulse" />
        <h1 class="text-lg font-semibold title-gradient">春招平行宇宙</h1>
        <span class="text-xs text-ink-500 ml-2">Spring Recruitment Parallel Universe</span>
      </div>
      <nav class="flex items-center gap-6 text-xs text-ink-300">
        <span :class="{ 'text-cyber-cyan': $route.name === 'upload' }">01 上传</span>
        <span class="text-ink-500">→</span>
        <span :class="{ 'text-cyber-cyan': $route.name === 'profile' }">02 画像</span>
        <span class="text-ink-500">→</span>
        <span :class="{ 'text-cyber-cyan': $route.name === 'sandbox' }">03 沙盘</span>
        <span class="text-ink-500">→</span>
        <span :class="{ 'text-cyber-cyan': $route.name === 'report' }">04 报告</span>
        <span class="text-ink-700">|</span>
        <router-link
          to="/dashboard"
          class="hover:text-cyber-cyan transition"
          :class="$route.name === 'dashboard' ? 'text-cyber-cyan' : 'text-ink-400'"
        >市场看板</router-link>
        <router-link
          to="/admin"
          class="hover:text-cyber-cyan transition"
          :class="$route.name === 'admin' ? 'text-cyber-cyan' : 'text-ink-400'"
        >治理</router-link>
      </nav>
    </header>

    <!-- 路由视图 -->
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.4s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
