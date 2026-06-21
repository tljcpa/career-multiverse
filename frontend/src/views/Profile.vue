<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getCandidateProfile, getSimulationStatus, startSimulation } from '@/api'
import { useSessionStore } from '@/stores/session'
import type { CandidateProfileResponse, SimSessionStatus } from '@/types/contracts'

/**
 * 求职画像页（旅程第二步，替代旧的 finetuning 黑话页）。
 *
 * 这一页做的事是"AI 是怎么认识你的"——直接给评委看：
 * 1. 简历里抽出的关键事实（学校 / 专业 / 目标岗位）
 * 2. 五维内部画像（项目 / 实习 / 成就 / 沟通 / 学校档）+ 综合分
 * 3. 49 家公司里的初步定位（挑战 / 够格 / 保底）
 *
 * 同时后台跑 simulation/start，poll 直到 done 跳 sandbox。
 * 时间窗大致和旧 finetuning 页重叠（~60 秒），但不再用伪 LoRA 进度条骗评委。
 */

const router = useRouter()
const session = useSessionStore()

const profile = ref<CandidateProfileResponse | null>(null)
const errorMsg = ref('')
const simStatus = ref<SimSessionStatus | null>(null)

let pollTimer = 0
// 连续 404 计数：backend 重启会让 in-memory sim_session 丢失，导致 polling 永远拿 404
// 之前 catch 静默吞 → UI 永远卡在最后帧不跳转。现在 3 次连续 404 主动跳 sandbox（sim_smoke fallback 兜底）
let pollMissCount = 0

onMounted(async () => {
  if (!session.userId) {
    router.push('/upload')
    return
  }
  try {
    profile.value = await getCandidateProfile(session.userId)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '画像生成失败'
    return
  }

  // 同步起 sim（后台跑），用户读画像时 sim 在跑
  try {
    const resp = await startSimulation(session.userId, 1000)
    session.setSimSession(resp.sim_session_id)
    pollTimer = window.setInterval(poll, 800)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'sim 启动失败'
  }
})

async function poll() {
  if (!session.simSessionId) {
    return
  }
  try {
    const s = await getSimulationStatus(session.simSessionId)
    simStatus.value = s
    pollMissCount = 0
    if (s.stage === 'done') {
      window.clearInterval(pollTimer)
      setTimeout(() => router.push('/sandbox'), 400)
    }
  } catch (e) {
    // backend 重启 / sim_session 丢失 → 连续 404 → 跳 sandbox 让 sim_smoke fallback 兜底
    pollMissCount++
    if (pollMissCount >= 3) {
      window.clearInterval(pollTimer)
      errorMsg.value = '宇宙重连失败，跳转到 sandbox（使用样本数据演示）'
      setTimeout(() => router.push('/sandbox'), 800)
    }
  }
}

const simProgress = computed(() => Math.round((simStatus.value?.progress ?? 0) * 100))
const simReady = computed(() => simStatus.value?.stage === 'done')

function enterSandbox() {
  router.push('/sandbox')
}

const fiveDims = computed(() => {
  if (!profile.value) {
    return []
  }
  const s = profile.value.signals
  const r = profile.value.reasoning || {}
  return [
    { key: 'project_strength', label: '项目含金量', value: s.project_strength, color: 'text-cyber-cyan', reason: r.project_strength || '' },
    { key: 'internship_strength', label: '实习含金量', value: s.internship_strength, color: 'text-cyber-purple', reason: r.internship_strength || '' },
    { key: 'achievements_strength', label: '成就/竞赛/开源', value: s.achievements_strength, color: 'text-cyber-gold', reason: r.achievements_strength || '' },
    { key: 'communication_score', label: '沟通表达', value: s.communication_score, color: 'text-cyber-pink', reason: r.communication_score || '' },
    { key: 'gpa_percentile', label: '专业 GPA 分位', value: s.gpa_percentile, color: 'text-emerald-400', reason: r.gpa_percentile || '' }
  ]
})

const expandedDim = ref<string | null>(null)
function toggleDim(key: string) {
  expandedDim.value = expandedDim.value === key ? null : key
}

const showRubric = ref(false)
const showBreakdown = ref(false)
const schoolTierReason = computed(() => profile.value?.reasoning?.school_tier || '')

const labelColor = (label: string) => {
  if (label === '挑战') return 'text-cyber-pink'
  if (label === '保底') return 'text-emerald-400'
  if (label === '顶尖优选') return 'text-cyber-gold'
  return 'text-cyber-cyan'
}

function gapDesc(gap: number): string {
  if (gap >= 25) return `高 ${gap} 分（绰绰有余）`
  if (gap >= 15) return `高 ${gap} 分（保底）`
  if (gap >= 5) return `高 ${gap} 分（够格）`
  if (gap >= 0) return `刚好达标（差 ${gap}）`
  if (gap >= -5) return `低 ${-gap} 分（差一点）`
  if (gap >= -15) return `低 ${-gap} 分（要努力）`
  return `低 ${-gap} 分（差距大）`
}
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-6xl mx-auto">
      <div v-if="errorMsg" class="panel-glass p-6 border border-cyber-pink/40 text-cyber-pink">
        {{ errorMsg }}
      </div>

      <template v-else-if="profile">
        <!-- 顶：身份卡 -->
        <div class="panel-glass p-6 mb-6">
          <div class="flex items-end justify-between flex-wrap gap-4">
            <div>
              <div class="text-xs text-ink-500 mb-1">AI 已从你的资料中读到</div>
              <h1 class="text-3xl font-bold title-gradient">
                {{ profile.resume_summary.name || '未命名候选人' }}
              </h1>
              <div class="text-ink-300 text-sm mt-2">
                <span class="text-ink-100">{{ profile.resume_summary.school }}</span>
                · {{ profile.resume_summary.major }}
              </div>
              <div class="flex flex-wrap gap-2 mt-3">
                <span
                  v-for="role in profile.resume_summary.target_roles"
                  :key="role"
                  class="text-xs px-3 py-1 rounded-full border border-cyber-cyan/30 text-cyber-cyan bg-cyber-cyan/5"
                >
                  目标：{{ role }}
                </span>
              </div>
            </div>
            <div class="text-right">
              <div class="text-xs text-ink-500 mb-1">综合分（0-120）</div>
              <div class="text-5xl font-mono font-bold text-cyber-gold">
                {{ profile.signals.composite_score.toFixed(0) }}
              </div>
              <div class="text-xs text-ink-500 mt-1">
                学校档：{{ profile.signals.school_tier_label }}
                <span v-if="schoolTierReason" class="text-ink-700">·</span>
                <span v-if="schoolTierReason" class="text-ink-500 italic">{{ schoolTierReason }}</span>
              </div>
              <button
                class="text-xs text-cyber-cyan hover:underline mt-2"
                @click="showBreakdown = !showBreakdown"
              >{{ showBreakdown ? '▴ 收起评分构成' : '▾ 查看评分构成（83 是怎么算的）' }}</button>
            </div>
          </div>
          <!-- 评分构成展开：每项贡献明细，评委一眼看清综合分怎么来的 -->
          <div v-if="showBreakdown" class="mt-4 border-t border-ink-800 pt-4">
            <div class="text-sm text-ink-100 mb-3 font-semibold">
              综合分 = <span class="text-cyber-gold">{{ profile.signals.composite_breakdown.final.toFixed(1) }}</span>
              <span v-if="profile.signals.composite_breakdown.raw_total > 120 || profile.signals.composite_breakdown.raw_total < 0" class="text-ink-500 text-xs ml-2">
                （原始 {{ profile.signals.composite_breakdown.raw_total.toFixed(1) }}，clamp 到 [0, 120]）
              </span>
            </div>
            <div class="space-y-2 text-sm font-mono">
              <div class="flex justify-between">
                <span class="text-ink-300">(项目 {{ profile.signals.project_strength }} + 实习 {{ profile.signals.internship_strength }} + 成就 {{ profile.signals.achievements_strength }}) / 3</span>
                <span class="text-cyber-cyan">{{ profile.signals.composite_breakdown.base_avg.toFixed(1) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-300">+ 学校档加成（{{ profile.signals.composite_breakdown.school_tier_label }}）</span>
                <span :class="profile.signals.composite_breakdown.school_bonus >= 0 ? 'text-emerald-400' : 'text-cyber-pink'">
                  {{ profile.signals.composite_breakdown.school_bonus >= 0 ? '+' : '' }}{{ profile.signals.composite_breakdown.school_bonus }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-300">+ 学历加成（{{ profile.signals.composite_breakdown.degree_label }}）</span>
                <span :class="profile.signals.composite_breakdown.degree_bonus >= 0 ? 'text-emerald-400' : 'text-cyber-pink'">
                  {{ profile.signals.composite_breakdown.degree_bonus >= 0 ? '+' : '' }}{{ profile.signals.composite_breakdown.degree_bonus }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-ink-300">+ 沟通修正（(沟通 {{ profile.signals.communication_score }} - 50) × 0.1）</span>
                <span :class="profile.signals.composite_breakdown.comm_adjust >= 0 ? 'text-emerald-400' : 'text-cyber-pink'">
                  {{ profile.signals.composite_breakdown.comm_adjust >= 0 ? '+' : '' }}{{ profile.signals.composite_breakdown.comm_adjust.toFixed(1) }}
                </span>
              </div>
              <div class="flex justify-between pt-2 border-t border-ink-800">
                <span class="text-ink-300">= 原始合计</span>
                <span class="text-ink-100 font-mono">{{ profile.signals.composite_breakdown.raw_total.toFixed(1) }}</span>
              </div>
              <div
                v-if="profile.signals.composite_breakdown.raw_total > 120 || profile.signals.composite_breakdown.raw_total < 0"
                class="flex justify-between text-cyber-cyan text-xs"
              >
                <span>→ clamp 到 [0, 120]</span>
                <span class="font-mono">{{ profile.signals.composite_breakdown.final.toFixed(1) }}</span>
              </div>
              <div class="flex justify-between pt-2 border-t border-ink-800 text-cyber-gold font-bold">
                <span>综合分（用于市场匹配）</span>
                <span>{{ profile.signals.composite_breakdown.final.toFixed(1) }}</span>
              </div>
            </div>
            <p class="text-xs text-ink-500 mt-3">
              加成表写死在 backend（rubric 可点开"评分参考标准"看完整规则），LLM 只决定五维分数，
              不决定加成系数——这是产品设计的"透明 + 灵活"折衷。
            </p>
          </div>
        </div>

        <!-- 五维内部画像 -->
        <div class="panel-glass p-6 mb-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-ink-100">你的五维内部画像</h2>
            <div class="flex items-center gap-3">
              <button
                class="text-xs text-cyber-cyan hover:underline"
                @click="showRubric = true"
              >ℹ 评分参考标准</button>
              <span class="text-xs text-ink-500">LLM 真评估（0-100）</span>
            </div>
          </div>
          <div class="space-y-2">
            <div
              v-for="d in fiveDims"
              :key="d.key"
              class="rounded border border-ink-800 hover:border-cyber-cyan/30 transition cursor-pointer"
              @click="toggleDim(d.key)"
            >
              <div class="flex items-center gap-4 p-3">
                <div class="w-28 text-sm text-ink-300">{{ d.label }}</div>
                <div class="flex-1 h-2 bg-ink-800 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-gradient-to-r from-cyber-cyan to-cyber-purple"
                    :style="{ width: d.value + '%' }"
                  ></div>
                </div>
                <div class="w-12 text-right font-mono text-sm" :class="d.color">{{ d.value }}</div>
                <div class="w-28 text-xs text-cyber-cyan/70 text-right">
                  {{ expandedDim === d.key ? '▴ 收起依据' : '▾ AI 评分依据' }}
                </div>
              </div>
              <div v-if="expandedDim === d.key" class="px-3 pb-3 -mt-1">
                <div class="text-xs text-ink-400 leading-relaxed pl-32 border-l-2 border-cyber-cyan/30 ml-1">
                  <template v-if="d.reason">
                    <span class="text-cyber-cyan">评分依据：</span>{{ d.reason }}
                  </template>
                  <template v-else>
                    <span class="text-ink-600 italic">LLM 评估尚未返回理由（兜底走学校档基线）</span>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Top 5 候选公司 -->
        <div class="panel-glass p-6 mb-6">
          <div class="flex items-center justify-between mb-1">
            <h2 class="text-lg font-bold text-ink-100">沙盘里 Top 5 候选公司</h2>
            <span class="text-xs text-ink-500">综合分 vs 招聘门槛（hiring_bar）</span>
          </div>
          <p class="text-xs text-ink-500 mb-4">{{ profile.market_summary }}</p>
          <div class="space-y-2">
            <div
              v-for="c in profile.top_companies"
              :key="c.code_name"
              class="flex items-center gap-3 p-3 rounded border border-ink-800 hover:border-cyber-cyan/40 transition"
            >
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-ink-100 font-semibold">{{ c.code_name }}</span>
                  <span class="text-xs text-ink-500">· {{ c.industry }}</span>
                </div>
              </div>
              <div class="text-xs text-ink-500 w-20 text-right">
                门槛 <span class="font-mono text-ink-100">{{ c.hiring_bar }}</span>
              </div>
              <div class="text-xs flex-shrink-0 w-40 text-right" :class="c.gap >= 0 ? 'text-emerald-400' : 'text-cyber-pink'">
                {{ gapDesc(c.gap) }}
              </div>
              <div class="w-20 text-right text-xs font-semibold" :class="labelColor(c.label)">{{ c.label }}</div>
            </div>
          </div>
        </div>

        <!-- 底：sim 进度 + CTA -->
        <div class="panel-glass p-6">
          <div v-if="!simReady">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm text-cyber-cyan">{{ simStatus?.message || '初始化中...' }}</div>
              <div class="text-sm font-mono text-cyber-cyan">{{ simProgress }}%</div>
            </div>
            <div class="h-2 bg-ink-800 rounded-full overflow-hidden">
              <div
                class="h-full bg-gradient-to-r from-cyber-cyan via-cyber-purple to-cyber-pink transition-all duration-500"
                :style="{ width: simProgress + '%' }"
              ></div>
            </div>
            <p class="text-xs text-ink-500 mt-3">
              后台正在跑 1000 个春招宇宙。读完上面的画像，分身就进沙盘了。
            </p>
          </div>
          <div v-else class="text-center">
            <div class="text-cyber-gold font-semibold mb-3">1000 个平行宇宙已就绪</div>
            <button class="btn-primary" @click="enterSandbox">进入 3D 沙盘 →</button>
          </div>
        </div>
      </template>

      <div v-else class="text-center pt-32 text-cyber-cyan">画像分析中...</div>
    </div>

    <!-- 评分参考标准 modal：给评委看 LLM 打分的区间指引（透明化） -->
    <div
      v-if="showRubric"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur"
      role="dialog"
      aria-modal="true"
      @click.self="showRubric = false"
      @keydown.esc="showRubric = false"
      tabindex="-1"
    >
      <div class="panel-glass w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6">
        <div class="flex items-start justify-between mb-4">
          <h3 class="text-xl font-bold title-gradient">五维评分参考标准</h3>
          <button class="text-ink-500 hover:text-ink-100 text-xl leading-none" @click="showRubric = false" aria-label="关闭">×</button>
        </div>
        <p class="text-xs text-ink-500 mb-5 leading-relaxed">
          以下区间是 LLM 评估时的指引（写在 backend prompt 里）。LLM 在区间内做综合判断，
          引用简历里的具体证据生成 reasoning，每次评估都能在 Profile 页点击"▾ AI 评分依据"看到引用。
        </p>

        <div class="space-y-4 text-sm">
          <div>
            <div class="text-cyber-cyan font-semibold mb-2">项目含金量 (project_strength)</div>
            <ul class="text-ink-300 space-y-1 ml-4">
              <li>· <span class="text-cyber-gold">70+</span>：深度项目（架构 + 完整技术栈 + 高复杂度），如开源 100+ star / 千万级 QPS pipeline</li>
              <li>· <span class="text-cyber-cyan">40-60</span>：课程项目 / 毕设级别</li>
              <li>· <span class="text-cyber-pink">&lt; 30</span>：无项目或仅 toy demo</li>
            </ul>
          </div>

          <div>
            <div class="text-cyber-purple font-semibold mb-2">实习含金量 (internship_strength)</div>
            <ul class="text-ink-300 space-y-1 ml-4">
              <li>· <span class="text-cyber-gold">80+</span>：大厂（字节 / 阿里 / 腾讯 / Google 等）+ ≥ 6 个月</li>
              <li>· <span class="text-cyber-cyan">50-65</span>：中小厂 / 短周期（≤ 3 个月）</li>
              <li>· <span class="text-cyber-pink">&lt; 30</span>：无实习经历</li>
            </ul>
          </div>

          <div>
            <div class="text-cyber-gold font-semibold mb-2">成就 / 竞赛 / 开源 (achievements_strength)</div>
            <ul class="text-ink-300 space-y-1 ml-4">
              <li>· <span class="text-cyber-gold">70+</span>：省一+ / ACM-ICPC 金银 / CCF 论文 / 开源 ≥ 100 star / 行业认证</li>
              <li>· <span class="text-cyber-cyan">40-65</span>：省二 / 校级一等 / 蓝桥杯省级</li>
              <li>· <span class="text-cyber-pink">&lt; 30</span>：仅课程作业，无外部认证</li>
            </ul>
          </div>

          <div>
            <div class="text-cyber-pink font-semibold mb-2">沟通表达 (communication_score)</div>
            <ul class="text-ink-300 space-y-1 ml-4">
              <li>· <span class="text-cyber-cyan">60-70</span>：行业基线（默认值，简历表达清晰）</li>
              <li>· <span class="text-cyber-gold">75-85</span>：简历逻辑性强、量化表述、自我介绍段写得好</li>
              <li>· <span class="text-ink-500">注</span>：仅靠简历推断，真实沟通能力以面试为准</li>
            </ul>
          </div>

          <div>
            <div class="text-emerald-400 font-semibold mb-2">专业 GPA 分位 (gpa_percentile)</div>
            <ul class="text-ink-300 space-y-1 ml-4">
              <li>· 简历明写 GPA / 排名 → 直接用真值</li>
              <li>· 未明写 → 按学校档推断：985_top → 75, 985 → 65, 211 → 55, 双非 → 45</li>
            </ul>
          </div>

          <div class="pt-4 mt-4 border-t border-ink-800">
            <div class="text-xs text-ink-400 leading-relaxed">
              <span class="text-cyber-gold font-semibold">综合分公式</span> =
              (项目 + 实习 + 成就) / 3 + <span class="text-cyber-cyan">学校档加成</span> +
              <span class="text-cyber-purple">学历加成</span> + (沟通 - 50) × 0.1
              <br><br>
              <span class="text-cyber-cyan">学校档加成</span>：
              清北 +20 / C9 +15 / 985 +10 / 211 +5 / 双非 0 / 二本及以下 -5 /
              海外 QS100 内 +12 / 海外其他 +2 / 专升本 -3 / 专科 -8
              <br><br>
              <span class="text-cyber-purple">学历加成</span>：
              博士 +10 / 硕士 +5 / 本科 0 / 专升本 -2 / 专科 -5 / 高中 -10
              <br><br>
              综合分 clamp 到 [0, 120]。≥ 95（≥ 市场最强公司 hiring_bar + 5）进入"顶尖优选"模式，
              Top 5 改按 hiring_bar 降序而非 hiring_bar - composite 距离。
            </div>
          </div>
        </div>

        <div class="mt-6 text-center">
          <button class="btn-ghost" @click="showRubric = false">关闭</button>
        </div>
      </div>
    </div>
  </main>
</template>
