<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { interviewHR } from '@/api'
import { useSessionStore } from '@/stores/session'
import type { Company, HRInterviewResponse } from '@/types/contracts'

const session = useSessionStore()

/**
 * HR 采访对话框。
 *
 * 这是 demo 的"杀手锏交互"之一：评委可以质问任一家虚拟 HR，
 * 测试 hidden_signals 是不是真的影响行为。
 */
const props = defineProps<{
  company: Company
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

interface Message {
  role: 'user' | 'hr'
  text: string
  hidden?: string
}

const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const scrollRef = ref<HTMLDivElement | null>(null)

const suggestedQuestions = [
  '你们的 985 偏好真实存在吗？',
  '加班文化怎么样？',
  '35 岁以上员工比例是多少？',
  '薪资可以谈吗？'
]

async function ask(question?: string) {
  const q = (question ?? input.value).trim()
  if (!q || loading.value) {
    return
  }
  messages.value.push({ role: 'user', text: q })
  input.value = ''
  loading.value = true
  scrollDown()
  try {
    const resp: HRInterviewResponse = await interviewHR({
      company_code: props.company.code_name,
      user_id: session.userId ?? 'demo',
      question: q
    })
    messages.value.push({ role: 'hr', text: resp.reply, hidden: resp.hidden_signal_revealed })
  } catch (err) {
    messages.value.push({
      role: 'hr',
      text: err instanceof Error ? `（HR 一时未答上来：${err.message}）` : '（HR 一时未答上来）'
    })
  } finally {
    loading.value = false
    scrollDown()
  }
}

function scrollDown() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur"
    role="dialog"
    aria-modal="true"
    :aria-label="`和 ${company.code_name} HR 对话`"
    tabindex="-1"
    @click.self="emit('close')"
    @keydown.esc="emit('close')"
  >
    <div class="panel-glass w-full max-w-3xl max-h-[85vh] flex flex-col">
      <!-- 头部 -->
      <div class="flex items-start justify-between p-5 border-b border-white/5">
        <div>
          <div class="flex items-center gap-3 mb-2">
            <span class="text-xs px-2 py-0.5 rounded-full bg-cyber-cyan/10 text-cyber-cyan border border-cyber-cyan/30">
              {{ company.industry }}
            </span>
            <span class="text-xs text-ink-500">{{ company.size_label }} · {{ company.headquarters_city }}</span>
          </div>
          <h3 class="text-2xl font-bold text-ink-100">{{ company.code_name }}</h3>
        </div>
        <button class="text-ink-300 hover:text-cyber-pink text-2xl leading-none px-2" @click="emit('close')" aria-label="关闭对话框">
          ×
        </button>
      </div>

      <!-- 双栏：左边公司信息 / 右边对话 -->
      <div class="flex-1 flex overflow-hidden">
        <!-- 公司侧栏 -->
        <aside class="w-72 border-r border-white/5 p-4 overflow-y-auto text-xs space-y-4">
          <div>
            <div class="text-cyber-cyan tracking-widest mb-2">招聘标尺</div>
            <div class="flex items-baseline gap-2">
              <span class="text-3xl font-mono text-cyber-gold">{{ company.hidden_signals.hiring_bar }}</span>
              <span class="text-ink-500">/ 100</span>
            </div>
            <div class="text-ink-500 mt-1">{{ company.hidden_signals.hiring_style }}</div>
          </div>

          <div>
            <div class="text-cyber-cyan tracking-widest mb-2">文化标签</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="t in company.hidden_signals.culture_tags"
                :key="t"
                class="px-2 py-0.5 rounded bg-space-deep border border-white/10 text-ink-300"
              >{{ t }}</span>
            </div>
          </div>

          <div>
            <div class="text-cyber-cyan tracking-widest mb-2">业务增长</div>
            <div class="h-2 bg-space-deep rounded-full overflow-hidden">
              <div
                class="h-full bg-gradient-to-r from-cyber-cyan to-cyber-gold"
                :style="{ width: company.hidden_signals.business_growth + '%' }"
              />
            </div>
            <div class="text-ink-500 mt-1">{{ company.hidden_signals.business_growth }} / 100</div>
          </div>

          <div>
            <div class="text-cyber-cyan tracking-widest mb-2">35+ 占比</div>
            <div class="text-xl font-mono text-ink-100">{{ company.hidden_signals.pct_over_35 }}%</div>
          </div>

          <div>
            <div class="text-cyber-cyan tracking-widest mb-2">开放岗位</div>
            <ul class="space-y-1">
              <li v-for="j in company.job_postings" :key="j.job_title" class="text-ink-300">
                · {{ j.job_title }}
              </li>
            </ul>
          </div>
        </aside>

        <!-- 对话主区 -->
        <div class="flex-1 flex flex-col">
          <div ref="scrollRef" class="flex-1 overflow-y-auto p-5 space-y-3">
            <div v-if="messages.length === 0" class="text-center text-ink-500 text-sm py-10">
              <div class="mb-4">向 {{ company.code_name }} 的 HR 提问</div>
              <div class="flex flex-wrap justify-center gap-2">
                <button
                  v-for="q in suggestedQuestions"
                  :key="q"
                  class="btn-ghost text-xs"
                  @click="ask(q)"
                >{{ q }}</button>
              </div>
            </div>
            <div v-for="(m, i) in messages" :key="i">
              <div v-if="m.role === 'user'" class="flex justify-end">
                <div class="max-w-xs bg-cyber-cyan/10 border border-cyber-cyan/30 text-ink-100 rounded-lg px-4 py-2 text-sm">
                  {{ m.text }}
                </div>
              </div>
              <div v-else class="flex">
                <div class="max-w-md bg-space-deep border border-white/10 rounded-lg px-4 py-2 text-sm">
                  <div class="text-ink-100">{{ m.text }}</div>
                  <div v-if="m.hidden" class="mt-2 pt-2 border-t border-white/5 text-[10px] text-cyber-gold font-mono">
                    {{ m.hidden }}
                  </div>
                </div>
              </div>
            </div>
            <div v-if="loading" class="text-xs text-ink-500 italic">HR 思考中...</div>
          </div>

          <!-- 输入框 -->
          <div class="border-t border-white/5 p-4 flex gap-2">
            <input
              v-model="input"
              type="text"
              placeholder="问任何问题，HR 会以 hidden_signals 为根据回答..."
              class="flex-1 bg-space-deep border border-white/10 rounded px-4 py-2 text-sm text-ink-100 focus:border-cyber-cyan focus:outline-none"
              @keydown.enter="ask()"
            />
            <button class="btn-primary !px-5 !py-2 text-sm" :disabled="loading" @click="ask()">
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
