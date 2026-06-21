import axios, { type AxiosInstance } from 'axios'

/**
 * Axios 封装。
 *
 * 设计：通过 VITE_USE_MOCK 切换。
 * 当 mock 开启时，api 模块的实现完全不调用这个 client（直接走 mock.ts）。
 * 当 mock 关闭时（M5 集成），统一从这里发请求，便于加 interceptor。
 */
export const httpClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' }
})

// 简单的全局错误拦截：把 backend 的 detail 字段提到 message 上
httpClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.data?.detail) {
      err.message = err.response.data.detail
    }
    return Promise.reject(err)
  }
)

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
