<script setup lang="ts">
import { useRouter } from 'vue-router'

/**
 * 落地页 / 新首页 —— 全站门面。
 *
 * 产品定位：可实验的人才市场沙盘 · 先实验，再决策。
 * 把人才市场从"只能凭经验决策"变成"可以先实验再决策"。
 *
 * 结构：
 * 1. Hero：定位标语 + 一句副文案 + 主 CTA（进个人端）。
 * 2. 三端大卡片：个人 / 企业 / 学校，各自一句话价值 + 跳转。
 * 3. 底部一行"三端联动"说明，点题"同一个虚拟市场里三方各自做实验"。
 *
 * 视觉严格 follow 现有深色赛博风（panel-glass / title-gradient / cyber-* 配色），
 * 全用形状 + 色块 + 线条，不用 emoji / 图标字体。
 */

const router = useRouter()

interface RoleCard {
  key: string
  tag: string
  title: string
  desc: string
  // 三步式一句话（分成短语更有节奏，用箭头串起来体现"流程/实验"）
  steps: string[]
  to: string
  cta: string
  color: string
  // 是否"已上线"（个人端），未上线的打"实验中"标以示克制的真诚
  live: boolean
}

const cards: RoleCard[] = [
  {
    key: 'personal',
    tag: '个人 · 求职者',
    title: '把自己丢进 1000 次春招',
    desc: '上传简历，AI 造出你的数字分身，替你在虚拟人才市场里跑完整个春招，再告诉你"如果换一步会怎样"。',
    steps: ['上传简历', '生成数字分身', '跑 1000 次春招', '反事实推演'],
    to: '/upload',
    cta: '上传简历，开始实验',
    color: '#00e5ff',
    live: true
  },
  {
    key: 'enterprise',
    tag: '企业 · 招聘方',
    title: '在市场里试招聘策略',
    desc: '为企业造招聘数字分身，在虚拟市场里改门槛、改薪资、改画像偏好，先看结果再落地，顺带拿到反向雇主品牌洞察。',
    steps: ['企业数字分身', '招聘策略实验', '反向品牌洞察'],
    to: '/enterprise',
    cta: '进入企业实验台',
    color: '#9d4dff',
    live: false
  },
  {
    key: 'school',
    tag: '学校 · 就业中心',
    title: '看清本校的市场竞争力',
    desc: '把本校毕业生作为一个群体投进市场，看整体竞争力、定位技能缺口，再精准对接最匹配的雇主。',
    steps: ['群体竞争力', '技能缺口定位', '对接雇主'],
    to: '/school',
    cta: '进入学校驾驶舱',
    color: '#ffcc4d',
    live: false
  }
]

function go(to: string) {
  router.push(to)
}

// hex → rgba，用于内联柔光（同 TriRoleNav 思路，避免动态类名被 tree-shake）
function tint(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
</script>

<template>
  <main class="w-full min-h-screen pt-24 pb-16 px-6">
    <div class="max-w-6xl mx-auto">
      <!-- ============ HERO ============ -->
      <section class="text-center mb-16 md:mb-20">
        <!-- 定位小标：一条青线 + 文字，克制的仪式感 -->
        <div class="inline-flex items-center gap-3 mb-6">
          <span class="block w-8 h-px bg-cyber-cyan/60" />
          <span class="text-cyber-cyan text-xs tracking-[0.3em] uppercase">
            可实验的人才市场沙盘
          </span>
          <span class="block w-8 h-px bg-cyber-cyan/60" />
        </div>

        <h1 class="text-5xl md:text-7xl font-bold title-gradient leading-tight mb-6">
          先实验，再决策
        </h1>

        <p class="text-ink-300 text-lg md:text-xl max-w-3xl mx-auto leading-relaxed">
          人才市场过去只能凭经验决策。我们把它变成一个可以先实验的沙盘——
          <span class="text-ink-100">个人、企业、学校</span>
          都能在同一个虚拟市场里造数字分身、反复推演，
          看清"换一个选择会怎样"，再把决策落到现实。
        </p>

        <div class="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
          <button
            class="btn-primary text-base px-8 py-3"
            @click="go('/upload')"
          >
            上传简历，跑一次你的春招
          </button>
          <button
            class="btn-ghost text-base"
            @click="go('/dashboard')"
          >
            先看市场看板
          </button>
        </div>
      </section>

      <!-- ============ 三端大卡片 ============ -->
      <section>
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-sm text-ink-500 uppercase tracking-widest">三个视角 · 同一个市场</h2>
          <span class="hidden md:block text-xs text-ink-500">选择你的身份进入实验</span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div
            v-for="card in cards"
            :key="card.key"
            class="role-card group panel-glass p-7 flex flex-col cursor-pointer transition-all duration-300 hover:-translate-y-1"
            :style="{ '--role-color': card.color }"
            @click="go(card.to)"
          >
            <!-- 顶部：色块 + 标签 + 上线态 -->
            <div class="flex items-center justify-between mb-5">
              <div class="flex items-center gap-3">
                <span
                  class="w-3 h-3 rounded-sm flex-shrink-0"
                  :style="{ background: card.color, boxShadow: `0 0 12px ${card.color}` }"
                />
                <span class="text-xs tracking-wider text-ink-300">{{ card.tag }}</span>
              </div>
              <span
                v-if="card.live"
                class="text-[10px] px-2 py-0.5 rounded-full border"
                :style="{ color: card.color, borderColor: tint(card.color, 0.4), background: tint(card.color, 0.08) }"
              >已上线</span>
              <span
                v-else
                class="text-[10px] px-2 py-0.5 rounded-full border border-white/10 text-ink-500"
              >实验中</span>
            </div>

            <!-- 标题 -->
            <h3
              class="text-2xl font-bold mb-3 transition-colors"
              :style="{ color: card.color }"
            >{{ card.title }}</h3>

            <!-- 描述 -->
            <p class="text-sm text-ink-300 leading-relaxed mb-6 flex-1">
              {{ card.desc }}
            </p>

            <!-- 三步式流程：色块节点 + 箭头线，体现"可实验的流程" -->
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1 mb-6">
              <template v-for="(step, i) in card.steps" :key="step">
                <span class="text-xs text-ink-100">{{ step }}</span>
                <span
                  v-if="i < card.steps.length - 1"
                  class="text-ink-500 text-xs"
                  aria-hidden="true"
                >&rsaquo;</span>
              </template>
            </div>

            <!-- CTA 行：底部一条 hover 显色的线 + 文字 -->
            <div class="flex items-center justify-between pt-4 border-t border-white/5">
              <span
                class="text-sm font-semibold transition-colors"
                :style="{ color: card.color }"
              >{{ card.cta }}</span>
              <span
                class="text-lg transition-transform duration-200 group-hover:translate-x-1"
                :style="{ color: card.color }"
                aria-hidden="true"
              >&rarr;</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ 三端联动 说明 ============ -->
      <section class="mt-16 panel-glass p-7 md:p-8">
        <div class="flex flex-col md:flex-row md:items-center gap-6">
          <!-- 左：三色汇聚的极简示意（纯色块 + 线，非图标） -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <span class="w-2.5 h-2.5 rounded-sm" style="background:#00e5ff" />
            <span class="w-6 h-px bg-white/15" />
            <span class="w-2.5 h-2.5 rounded-sm" style="background:#9d4dff" />
            <span class="w-6 h-px bg-white/15" />
            <span class="w-2.5 h-2.5 rounded-sm" style="background:#ffcc4d" />
          </div>
          <div>
            <div class="text-ink-100 font-semibold mb-1">三端共享同一个虚拟人才市场</div>
            <p class="text-sm text-ink-300 leading-relaxed">
              个人投递、企业招聘、学校输送，在沙盘里互为对手盘与供需双方。
              一端的策略变化会传导到另一端——这才是"可实验"的意义：
              不是各自模拟，而是在一个联动的市场里，先看见结果，再做决策。
            </p>
          </div>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
/* 卡片 hover 时用角色主题色点亮边框与柔光，靠 CSS 变量传色 */
.role-card {
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.role-card:hover {
  border-color: color-mix(in srgb, var(--role-color) 40%, transparent);
  box-shadow: 0 8px 40px -12px color-mix(in srgb, var(--role-color) 35%, transparent);
}
</style>
