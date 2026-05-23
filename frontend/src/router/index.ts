import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

// 用户旅程顺序：Upload → Finetuning → Sandbox → Report
// 用 hash 路由：纯静态部署也能跑，对 demo 友好
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/upload'
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/Upload.vue')
  },
  {
    path: '/finetuning',
    name: 'finetuning',
    component: () => import('@/views/Finetuning.vue')
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

export default router
