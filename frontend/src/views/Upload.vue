<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { uploadCandidate } from '@/api'
import { useSessionStore } from '@/stores/session'

/**
 * 上传页：用户旅程第一步。
 *
 * 设计目标：
 * 1. 视觉冲击：一段标语 + cyber 风格上传区
 * 2. 输入项：简历文件（拖拽 / 点击）、GitHub、Blog
 * 3. 一键启动 → 跳到 Finetuning
 *
 * mock 阶段：简历内容不真上传，直接走 mockUpload 返回 user_id
 */
const router = useRouter()
const session = useSessionStore()

const resumeFile = ref<File | null>(null)
const githubUrl = ref('')
const blogUrl = ref('')
const extraUrl = ref('')
const dragOver = ref(false)
const submitting = ref(false)
const errorMsg = ref('')

function onFileChosen(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    resumeFile.value = target.files[0]
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) {
    resumeFile.value = f
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}

function onDragLeave() {
  dragOver.value = false
}

async function startJourney() {
  // 注意：mock 阶段允许跳过简历，是为了 demo 流畅，真实接口里 resume 必填
  if (submitting.value) {
    return
  }
  submitting.value = true
  errorMsg.value = ''
  try {
    const form = new FormData()
    if (resumeFile.value) {
      form.append('resume_file', resumeFile.value)
    }
    if (githubUrl.value) {
      form.append('github_url', githubUrl.value)
    }
    if (blogUrl.value) {
      form.append('blog_url', blogUrl.value)
    }
    if (extraUrl.value) {
      form.append('extra_links', extraUrl.value)
    }
    const resp = await uploadCandidate(form)
    session.setUser(resp)
    router.push('/profile')
  } catch (err) {
    if (err instanceof Error) {
      errorMsg.value = err.message
    } else {
      errorMsg.value = '上传失败，请重试'
    }
  } finally {
    submitting.value = false
  }
}

function skipDemo() {
  // demo 模式：直接走 mock，不需要任何输入
  startJourney()
}
</script>

<template>
  <main class="w-full min-h-screen flex items-center justify-center px-6 pt-20 pb-12">
    <div class="w-full max-w-4xl">
      <!-- 标题 -->
      <div class="text-center mb-12">
        <p class="text-cyber-cyan text-sm tracking-widest mb-3">智联招聘 · 2026 春招 AI 创新大赛</p>
        <h1 class="text-5xl md:text-6xl font-bold title-gradient mb-4 leading-tight">
          上传你的简历<br />让 AI 帮你跑一遍平行春招
        </h1>
        <p class="text-ink-300 text-lg max-w-2xl mx-auto">
          LLM 一次性读完你的简历，输出五维内部画像 + 每维评分理由，然后让数字分身进入
          约 300 家虚构公司组成的招聘宇宙，经历完整春招——投递、笔试、面试、谈薪。
          统计告诉你：在平行宇宙里，你最可能去哪里、能拿多少、哪一步是关键岔路。
        </p>
      </div>

      <!-- 主表单卡片 -->
      <div class="panel-glass p-8">
        <!-- 文件上传区 -->
        <label
          class="block border-2 border-dashed rounded-lg p-10 text-center transition-all cursor-pointer"
          :class="[
            dragOver
              ? 'border-cyber-cyan bg-cyber-cyan/5'
              : 'border-white/15 hover:border-cyber-cyan/50 hover:bg-white/2'
          ]"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop"
        >
          <input type="file" accept=".pdf,.md,.markdown" class="hidden" @change="onFileChosen" />
          <div v-if="!resumeFile">
            <div class="text-5xl text-cyber-cyan/70 mb-4">⇪</div>
            <div class="text-lg text-ink-100 mb-2">拖拽简历到这里，或点击选择</div>
            <div class="text-xs text-ink-500">支持 PDF / Markdown，最大 5MB</div>
          </div>
          <div v-else class="text-cyber-cyan">
            <div class="checkmark mx-auto mb-2"></div>
            <div class="text-base">{{ resumeFile.name }}</div>
            <div class="text-xs text-ink-500 mt-1">{{ (resumeFile.size / 1024).toFixed(1) }} KB</div>
          </div>
        </label>

        <!-- 链接输入 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
          <div>
            <label class="block text-xs text-ink-300 mb-2">GitHub（可选，看你的代码）</label>
            <input
              v-model="githubUrl"
              type="url"
              placeholder="https://github.com/yourname"
              class="w-full bg-space-deep border border-white/10 rounded px-4 py-3 text-ink-100 focus:border-cyber-cyan focus:outline-none transition-colors"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-300 mb-2">个人博客（可选，看你的思考）</label>
            <input
              v-model="blogUrl"
              type="url"
              placeholder="https://yourname.dev"
              class="w-full bg-space-deep border border-white/10 rounded px-4 py-3 text-ink-100 focus:border-cyber-cyan focus:outline-none transition-colors"
            />
          </div>
        </div>

        <div class="mt-4">
          <label class="block text-xs text-ink-300 mb-2">其他链接（论文 / 比赛 / 作品集，可选）</label>
          <input
            v-model="extraUrl"
            type="url"
            placeholder="https://..."
            class="w-full bg-space-deep border border-white/10 rounded px-4 py-3 text-ink-100 focus:border-cyber-cyan focus:outline-none transition-colors"
          />
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="mt-4 text-sm text-cyber-pink">
          {{ errorMsg }}
        </div>

        <!-- 启动按钮 -->
        <div class="mt-8 flex flex-col sm:flex-row gap-4 items-center justify-between">
          <div class="text-xs text-ink-500">
            <span class="text-cyber-gold">隐私承诺：</span>简历内容仅用于本次模拟，
            不会上传到大模型训练数据集，本地推理 + 即用即删。
          </div>
          <div class="flex gap-3 items-center">
            <span class="text-xs text-cyber-cyan animate-pulse">评委推荐 →</span>
            <button class="btn-primary !bg-gradient-to-r !from-cyber-cyan/80 !to-cyber-purple/80" :disabled="submitting" @click="skipDemo">
              使用 Demo 数据
            </button>
            <button class="btn-ghost" :disabled="submitting" @click="startJourney">
              <span v-if="submitting">启动中...</span>
              <span v-else>用我的简历</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 产品三大模块 -->
      <div class="text-xs text-ink-500 mt-10 mb-3 uppercase tracking-widest">产品三大模块</div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="panel-glass p-5">
          <div class="text-cyber-cyan text-3xl font-mono mb-2">A</div>
          <div class="text-ink-100 font-semibold mb-1">LLM 画像评估</div>
          <div class="text-xs text-ink-300">一次调用同时输出 5 维评分 + 每维理由 + 学校档判定，对评委透明可追溯</div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-cyber-purple text-3xl font-mono mb-2">B</div>
          <div class="text-ink-100 font-semibold mb-1">沙盘推演</div>
          <div class="text-xs text-ink-300">化身在约 300 家虚构公司的春招宇宙中跑出多个平行结局</div>
        </div>
        <div class="panel-glass p-5">
          <div class="text-cyber-pink text-3xl font-mono mb-2">C</div>
          <div class="text-ink-100 font-semibold mb-1">反事实分析</div>
          <div class="text-xs text-ink-300">如果你的项目再深一点 / 学校再好一点，offer 率和薪资会发生什么</div>
        </div>
      </div>
    </div>
  </main>
</template>
