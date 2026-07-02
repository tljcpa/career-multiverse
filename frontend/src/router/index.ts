import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { useSessionStore } from '@/stores/session'

// 用户旅程顺序：Upload → Finetuning → Sandbox → Report
// 用 hash 路由：纯静态部署也能跑，对 demo 友好
const routes: RouteRecordRaw[] = [
  {
    // 首页：三端愿景落地页（个人 / 企业 / 学校 = 可实验的人才市场）
    path: '/',
    name: 'landing',
    component: () => import('@/views/Landing.vue')
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/Upload.vue')
  },
  {
    // 企业端：企业数字分身 + 策略实验 + 反向品牌（演示视图）
    path: '/enterprise',
    name: 'enterprise',
    component: () => import('@/views/Enterprise.vue')
  },
  {
    // 学校端：本校群体竞争力 + 技能缺口 + 对接雇主（演示视图）
    path: '/school',
    name: 'school',
    component: () => import('@/views/School.vue')
  },
  {
    // profile：替代旧 finetuning 黑话页
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/Profile.vue')
  },
  {
    path: '/sandbox',
    name: 'sandbox',
    component: () => import('@/views/Sandbox.vue')
  },
  {
    path: '/report',
    name: 'report',
    component: () => import('@/views/Report.vue')
  },
  {
    // 市场治理页：公司池 + 求职者池 CRUD
    // 体现"动态市场"产品定位（评委可现场加一家公司/求职者）
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/Admin.vue')
  },
  {
    // 市场看板：全市场统计可视化
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue')
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 守卫：sandbox / finetuning / report 必须先有 user_id（即跑过 upload）
// admin / dashboard 是评委用的，不拦
const PROTECTED = new Set(['profile', 'sandbox', 'report'])
router.beforeEach((to) => {
  if (PROTECTED.has(String(to.name))) {
    const session = useSessionStore()
    if (!session.hasUploaded) {
      return { name: 'upload' }
    }
  }
  return true
})

export default router
