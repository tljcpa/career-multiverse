import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import { fileURLToPath, URL } from 'node:url'

// Vite 配置：Vue + UnoCSS + 路径别名 @
// 选择 UnoCSS 而非 Tailwind：原子化 + 按需生成，体积更小，配置零负担
export default defineConfig({
  plugins: [vue(), UnoCSS()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // 后续 M5 集成时反代到 backend FastAPI，当前不会触发（mock 模式）
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    target: 'es2020',
    sourcemap: false,
    // 拆分 chunk：three 和 d3 比较大，单独打包减少首屏阻塞
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          d3: ['d3'],
          vue: ['vue', 'vue-router', 'pinia']
        }
      }
    }
  }
})
