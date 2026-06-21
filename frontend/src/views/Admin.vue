<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import {
  adminListCompanies,
  adminAddCompany,
  adminDeleteCompany,
  adminListPersonas,
  adminAddPersona,
  adminDeletePersona
} from '@/api'
import type { Company } from '@/types/contracts'

/**
 * 市场治理页：体现"动态市场"产品定位。
 *
 * 设计取舍：
 * - 两个 tab（公司池 / 求职者池）共享同一页，节省切换成本
 * - 列表 + "+ 添加" 按钮 + 每行删除按钮（PATCH 改字段先不做，CRUD 已有 backend，先聚焦 demo 关键交互）
 * - 添加表单用 modal，字段只暴露关键的（其余用 sane defaults）
 * - 删除是硬删，确认对话框防误操作
 */

type Tab = 'companies' | 'personas'
const activeTab = ref<Tab>('companies')

// ---------- 公司池 ----------
const companies = ref<Company[]>([])
const loadingCompanies = ref(false)
async function reloadCompanies() {
  loadingCompanies.value = true
  try {
    companies.value = await adminListCompanies()
  } catch (e) {
    console.warn('listCompanies failed', e)
  } finally {
    loadingCompanies.value = false
  }
}

// ---------- 求职者池 ----------
const personas = ref<Array<Record<string, unknown>>>([])
const loadingPersonas = ref(false)
async function reloadPersonas() {
  loadingPersonas.value = true
  try {
    personas.value = await adminListPersonas()
  } catch (e) {
    console.warn('listPersonas failed', e)
  } finally {
    loadingPersonas.value = false
  }
}

onMounted(async () => {
  await Promise.all([reloadCompanies(), reloadPersonas()])
})

// ---------- 添加公司表单 ----------
const showCompanyForm = ref(false)
const newCompany = ref({
  code_name: '',
  industry: '互联网',
  size_label: 'MEDIUM（500-5000 人）',
  headquarters_city: '北京',
  hiring_bar: 75,
  hiring_style: 'project_heavy',
  culture_tags: '快节奏,扁平,技术驱动',
  salary: '20-30k·15薪',
  job_title: '工程师-校招',
  job_keywords: 'Python,FastAPI,RAG'
})
const adding = ref(false)
const errorMsg = ref('')

async function submitCompany() {
  if (!newCompany.value.code_name.trim()) {
    errorMsg.value = '请输入公司代号'
    return
  }
  adding.value = true
  errorMsg.value = ''
  try {
    const payload: Company = {
      code_name: newCompany.value.code_name.trim(),
      inspired_by_hint: '现场添加',
      industry: newCompany.value.industry,
      size_label: newCompany.value.size_label,
      headquarters_city: newCompany.value.headquarters_city,
      job_postings: [
        {
          job_title: newCompany.value.job_title,
          job_category: '技术',
          salary: newCompany.value.salary,
          years_required: '应届',
          degree_required: '本科及以上',
          city_required: newCompany.value.headquarters_city,
          keywords: newCompany.value.job_keywords.split(',').map((s) => s.trim()).filter(Boolean),
          description: `${newCompany.value.code_name} 的 ${newCompany.value.job_title} 岗位`,
          company_name: newCompany.value.code_name.trim(),
          work_address: newCompany.value.headquarters_city,
          publish_date: new Date().toISOString().slice(0, 10)
        }
      ],
      hidden_signals: {
        hiring_bar: newCompany.value.hiring_bar,
        hiring_style: newCompany.value.hiring_style,
        culture_tags: newCompany.value.culture_tags.split(',').map((s) => s.trim()).filter(Boolean),
        business_growth: 70,
        pct_over_35: 20,
        hidden_filters: []
      }
    }
    await adminAddCompany(payload)
    showCompanyForm.value = false
    // 重置表单
    newCompany.value.code_name = ''
    await reloadCompanies()
    showToast('公司 ' + payload.code_name + ' 已加入沙盘')
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '添加失败'
  } finally {
    adding.value = false
  }
}

async function removeCompany(code: string) {
  if (!confirm(`确认删除公司 "${code}"？该操作不可撤销`)) {
    return
  }
  try {
    await adminDeleteCompany(code)
    await reloadCompanies()
    showToast('公司 ' + code + ' 已退出')
  } catch (e) {
    alert('删除失败: ' + (e instanceof Error ? e.message : ''))
  }
}

// ---------- 添加求职者表单 ----------
const showPersonaForm = ref(false)
const newPersona = ref({
  candidate_id: '',
  name: '',
  school: '某 985',
  school_tier: '985',
  major: '计算机',
  degree: '本科',
  age: 22,
  city: '北京',
  resume_quality: 70,
  target_roles: '算法工程师,后端工程师'
})

async function submitPersona() {
  if (!newPersona.value.candidate_id.trim() || !newPersona.value.name.trim()) {
    errorMsg.value = '请填写 ID 和姓名'
    return
  }
  adding.value = true
  errorMsg.value = ''
  try {
    const payload = {
      candidate_id: newPersona.value.candidate_id.trim(),
      is_primary: false,
      official_cv: {
        resume_quality: newPersona.value.resume_quality,
        name: newPersona.value.name,
        gender: '未知',
        job_status: '应届',
        age: newPersona.value.age,
        work_years: '应届',
        highest_degree: newPersona.value.degree,
        current_address: newPersona.value.city,
        job_expectation: {
          target_industries: ['互联网'],
          target_roles: newPersona.value.target_roles.split(',').map((s) => s.trim()).filter(Boolean),
          target_cities: [newPersona.value.city],
          min_salary: '15-25k·14薪'
        },
        work_internship_history: [],
        project_history: [],
        education_history: [
          {
            school: newPersona.value.school,
            degree: newPersona.value.degree,
            major: newPersona.value.major,
            period: '2022.09 - 2026.06'
          }
        ],
        personal_strengths: '技术基础扎实',
        certificates: []
      },
      hidden_signals: {
        school_tier: newPersona.value.school_tier,
        gpa_percentile: 70,
        project_strength: 70,
        internship_strength: 50,
        achievements_strength: 40,
        communication_score: 65,
        stress_tolerance: 70,
        overwork_tolerance: 50
      }
    }
    await adminAddPersona(payload)
    showPersonaForm.value = false
    newPersona.value.candidate_id = ''
    newPersona.value.name = ''
    await reloadPersonas()
    showToast('求职者 ' + payload.candidate_id + ' 已加入沙盘')
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '添加失败'
  } finally {
    adding.value = false
  }
}

async function removePersona(id: string) {
  if (!confirm(`确认删除求职者 "${id}"？`)) {
    return
  }
  try {
    await adminDeletePersona(id)
    await reloadPersonas()
    showToast('求职者 ' + id + ' 已退出')
  } catch (e) {
    alert('删除失败: ' + (e instanceof Error ? e.message : ''))
  }
}

// 统计

// 搜索过滤
const searchCompany = ref('')
const searchPersona = ref('')
const filteredCompanies = computed(() => {
  const q = searchCompany.value.trim().toLowerCase()
  if (!q) return companies.value
  return companies.value.filter((c) =>
    c.code_name.toLowerCase().includes(q) ||
    c.industry.toLowerCase().includes(q) ||
    c.headquarters_city.toLowerCase().includes(q)
  )
})
const filteredPersonas = computed(() => {
  const q = searchPersona.value.trim().toLowerCase()
  if (!q) return personas.value
  return personas.value.filter((pe) => {
    const cv = pe.official_cv as Record<string, unknown>
    return (
      (pe.candidate_id as string).toLowerCase().includes(q) ||
      ((cv?.name as string) || '').toLowerCase().includes(q)
    )
  })
})

// 添加成功 toast
const toast = ref('')
function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 2500)
}

const stats = computed(() => ({
  companies: companies.value.length,
  personas: personas.value.length
}))
</script>

<template>
  <main class="w-full min-h-screen pt-20 pb-12 px-6">
    <div class="max-w-7xl mx-auto">
      <!-- 顶部 -->
      <div class="mb-8">
        <p class="text-cyber-cyan text-sm tracking-widest mb-2">MARKET GOVERNANCE</p>
        <h1 class="text-4xl font-bold title-gradient">市场治理</h1>
        <p class="text-ink-300 text-sm mt-2">
          沙盘是动态市场：公司和求职者随时加入退出。当前市场规模
          <span class="text-cyber-cyan font-mono">{{ stats.companies }}</span> 家公司、
          <span class="text-cyber-cyan font-mono">{{ stats.personas }}</span> 个求职者。
        </p>
      </div>

      <!-- tabs -->
      <div class="flex gap-2 mb-6 border-b border-ink-700">
        <button
          class="px-4 py-2 text-sm transition"
          :class="activeTab === 'companies' ? 'text-cyber-cyan border-b-2 border-cyber-cyan' : 'text-ink-400 hover:text-ink-200'"
          @click="activeTab = 'companies'"
        >
          公司池 <span class="text-xs opacity-60">({{ stats.companies }})</span>
        </button>
        <button
          class="px-4 py-2 text-sm transition"
          :class="activeTab === 'personas' ? 'text-cyber-cyan border-b-2 border-cyber-cyan' : 'text-ink-400 hover:text-ink-200'"
          @click="activeTab = 'personas'"
        >
          求职者池 <span class="text-xs opacity-60">({{ stats.personas }})</span>
        </button>
      </div>

      <!-- 公司池 tab -->
      <div v-if="activeTab === 'companies'">
        <div class="flex justify-between items-center mb-4 gap-3">
          <input v-model="searchCompany" placeholder="搜索代号 / 行业 / 城市..." class="flex-1 bg-ink-800 border border-ink-700 rounded px-3 py-1.5 text-sm" />
          <span class="text-ink-500 text-xs whitespace-nowrap">{{ filteredCompanies.length }}/{{ companies.length }}</span>
          <button class="btn-primary text-sm" @click="showCompanyForm = true">+ 加入新公司</button>
        </div>
        <div v-if="loadingCompanies" class="text-ink-400 text-sm">加载中...</div>
        <div v-else class="panel-glass overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-ink-800/50 text-ink-400">
              <tr>
                <th class="text-left p-3">代号</th>
                <th class="text-left p-3">行业</th>
                <th class="text-left p-3">规模</th>
                <th class="text-left p-3">城市</th>
                <th class="text-left p-3">招聘 bar</th>
                <th class="text-left p-3">招聘风格</th>
                <th class="text-left p-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in filteredCompanies" :key="c.code_name" class="border-t border-ink-800 hover:bg-ink-800/30">
                <td class="p-3 font-mono text-cyber-cyan">{{ c.code_name }}</td>
                <td class="p-3 text-ink-200">{{ c.industry }}</td>
                <td class="p-3 text-ink-300 text-xs">{{ c.size_label }}</td>
                <td class="p-3 text-ink-300">{{ c.headquarters_city }}</td>
                <td class="p-3 font-mono">{{ c.hidden_signals.hiring_bar }}</td>
                <td class="p-3 text-ink-300 text-xs">{{ c.hidden_signals.hiring_style }}</td>
                <td class="p-3">
                  <button class="text-red-400 hover:text-red-300 text-xs" @click="removeCompany(c.code_name)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 求职者池 tab -->
      <div v-if="activeTab === 'personas'">
        <div class="flex justify-between items-center mb-4 gap-3">
          <input v-model="searchPersona" placeholder="搜索 ID / 姓名..." class="flex-1 bg-ink-800 border border-ink-700 rounded px-3 py-1.5 text-sm" />
          <span class="text-ink-500 text-xs whitespace-nowrap">{{ filteredPersonas.length }}/{{ personas.length }}</span>
          <button class="btn-primary text-sm" @click="showPersonaForm = true">+ 加入新求职者</button>
        </div>
        <div v-if="loadingPersonas" class="text-ink-400 text-sm">加载中...</div>
        <div v-else class="panel-glass overflow-hidden max-h-[600px] overflow-y-auto">
          <table class="w-full text-sm">
            <thead class="bg-ink-800/50 text-ink-400 sticky top-0">
              <tr>
                <th class="text-left p-3">ID</th>
                <th class="text-left p-3">姓名</th>
                <th class="text-left p-3">学校 tier</th>
                <th class="text-left p-3">学历</th>
                <th class="text-left p-3">年龄</th>
                <th class="text-left p-3">简历质量</th>
                <th class="text-left p-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in filteredPersonas" :key="(p.candidate_id as string)" class="border-t border-ink-800 hover:bg-ink-800/30">
                <td class="p-3 font-mono text-cyber-cyan text-xs">{{ (p.candidate_id as string) }}</td>
                <td class="p-3 text-ink-200">{{ ((p.official_cv as Record<string, unknown>)?.name as string) || '-' }}</td>
                <td class="p-3 text-ink-300 text-xs">{{ ((p.hidden_signals as Record<string, unknown>)?.school_tier as string) }}</td>
                <td class="p-3 text-ink-300 text-xs">{{ ((p.official_cv as Record<string, unknown>)?.highest_degree as string) }}</td>
                <td class="p-3">{{ ((p.official_cv as Record<string, unknown>)?.age as number) }}</td>
                <td class="p-3 font-mono">{{ ((p.official_cv as Record<string, unknown>)?.resume_quality as number) }}</td>
                <td class="p-3">
                  <button class="text-red-400 hover:text-red-300 text-xs" @click="removePersona(p.candidate_id as string)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 添加公司 modal -->
    <div
      v-if="showCompanyForm"
      class="fixed inset-0 flex items-center justify-center bg-black/70 z-50"
      @click.self="showCompanyForm = false"
    >
      <div class="panel-glass p-6 w-[480px]">
        <h3 class="text-lg font-bold mb-4 text-cyber-cyan">加入新公司</h3>
        <div class="space-y-3 text-sm">
          <div>
            <label class="block text-ink-400 mb-1">代号（如 X-厂）<span class="text-red-400">*</span></label>
            <input v-model="newCompany.code_name" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-ink-400 mb-1">行业</label>
              <input v-model="newCompany.industry" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
            <div>
              <label class="block text-ink-400 mb-1">城市</label>
              <input v-model="newCompany.headquarters_city" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
          </div>
          <div>
            <label class="block text-ink-400 mb-1">规模标签</label>
            <select v-model="newCompany.size_label" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2">
              <option>STARTUP（&lt;100 人）</option>
              <option>SMALL（100-500 人）</option>
              <option>MEDIUM（500-5000 人）</option>
              <option>LARGE（5000-50000 人）</option>
              <option>MEGA（&gt;50000 人）</option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-ink-400 mb-1">招聘 bar (0-100)</label>
              <input v-model.number="newCompany.hiring_bar" type="number" min="0" max="100" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
            <div>
              <label class="block text-ink-400 mb-1">招聘风格</label>
              <select v-model="newCompany.hiring_style" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2">
                <option value="pedigree_first">看学历</option>
                <option value="project_heavy">看项目</option>
                <option value="leetcode_heavy">看算法</option>
                <option value="culture_fit">看文化</option>
                <option value="case_based">看 case</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-ink-400 mb-1">文化标签（逗号分隔）</label>
            <input v-model="newCompany.culture_tags" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
          <div>
            <label class="block text-ink-400 mb-1">职位名称</label>
            <input v-model="newCompany.job_title" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
          <div>
            <label class="block text-ink-400 mb-1">薪资</label>
            <input v-model="newCompany.salary" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
        </div>
        <div v-if="errorMsg" class="text-red-400 text-xs mt-3">{{ errorMsg }}</div>
        <div class="flex justify-end gap-2 mt-4">
          <button class="btn-ghost text-sm" @click="showCompanyForm = false">取消</button>
          <button class="btn-primary text-sm" :disabled="adding" @click="submitCompany">
            <span v-if="adding">添加中...</span>
            <span v-else>加入沙盘</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 添加求职者 modal -->
    <div
      v-if="showPersonaForm"
      class="fixed inset-0 flex items-center justify-center bg-black/70 z-50"
      @click.self="showPersonaForm = false"
    >
      <div class="panel-glass p-6 w-[480px]">
        <h3 class="text-lg font-bold mb-4 text-cyber-cyan">加入新求职者</h3>
        <div class="space-y-3 text-sm">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-ink-400 mb-1">ID<span class="text-red-400">*</span></label>
              <input v-model="newPersona.candidate_id" placeholder="compete_999" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
            <div>
              <label class="block text-ink-400 mb-1">姓名<span class="text-red-400">*</span></label>
              <input v-model="newPersona.name" placeholder="张同学" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-ink-400 mb-1">学校</label>
              <input v-model="newPersona.school" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
            <div>
              <label class="block text-ink-400 mb-1">学校 tier</label>
              <select v-model="newPersona.school_tier" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2">
                <option value="top">清北复交</option>
                <option value="985_top">C9/985 头部</option>
                <option value="985">普通 985</option>
                <option value="211">211</option>
                <option value="double_non">双非一本</option>
                <option value="lower">二本及以下</option>
                <option value="overseas_top">海外 QS 100</option>
                <option value="overseas_other">海外其他</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block text-ink-400 mb-1">学历</label>
              <select v-model="newPersona.degree" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2">
                <option>本科</option>
                <option>硕士</option>
                <option>博士</option>
              </select>
            </div>
            <div>
              <label class="block text-ink-400 mb-1">年龄</label>
              <input v-model.number="newPersona.age" type="number" min="18" max="40" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
            <div>
              <label class="block text-ink-400 mb-1">简历质量</label>
              <input v-model.number="newPersona.resume_quality" type="number" min="0" max="100" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
            </div>
          </div>
          <div>
            <label class="block text-ink-400 mb-1">专业</label>
            <input v-model="newPersona.major" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
          <div>
            <label class="block text-ink-400 mb-1">目标岗位（逗号分隔）</label>
            <input v-model="newPersona.target_roles" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
          <div>
            <label class="block text-ink-400 mb-1">现居城市</label>
            <input v-model="newPersona.city" class="w-full bg-ink-800 border border-ink-700 rounded px-3 py-2" />
          </div>
        </div>
        <div v-if="errorMsg" class="text-red-400 text-xs mt-3">{{ errorMsg }}</div>
        <div class="flex justify-end gap-2 mt-4">
          <button class="btn-ghost text-sm" @click="showPersonaForm = false">取消</button>
          <button class="btn-primary text-sm" :disabled="adding" @click="submitPersona">
            <span v-if="adding">添加中...</span>
            <span v-else>加入沙盘</span>
          </button>
        </div>
      </div>
    </div>
    <!-- 全局 toast 浮层（动态市场操作反馈）-->
    <transition name="fade">
      <div v-if="toast" class="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 bg-cyber-cyan/20 border border-cyber-cyan text-cyber-cyan px-5 py-2 rounded-full text-sm backdrop-blur-sm">
        {{ toast }}
      </div>
    </transition>
  </main>
</template>
