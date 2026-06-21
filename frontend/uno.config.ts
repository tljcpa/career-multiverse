import { defineConfig, presetUno, presetAttributify, presetIcons } from 'unocss'

// UnoCSS 配置：默认 uno preset + 属性化 + 图标
// 这里定义沙盘项目用色调（深空科技感）
export default defineConfig({
  presets: [
    presetUno(),
    presetAttributify(),
    presetIcons({
      scale: 1.2
    })
  ],
  theme: {
    colors: {
      // 深空背景色
      'space-bg': '#05060d',
      'space-deep': '#0a0e1a',
      'space-panel': '#0f1424',
      // 主调：智联蓝 + 紫色发光
      'cyber-cyan': '#00e5ff',
      'cyber-purple': '#9d4dff',
      'cyber-pink': '#ff4d9d',
      'cyber-gold': '#ffcc4d',
      // 文字
      'ink-100': '#e8ecff',
      'ink-300': '#a0a8c8',
      'ink-500': '#5f6786'
    },
    fontFamily: {
      sans: '"PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      mono: '"JetBrains Mono", "Fira Code", monospace'
    }
  },
  shortcuts: {
    // 玻璃面板：reusable 卡片
    'panel-glass': 'bg-space-panel/70 backdrop-blur-md border border-white/5 rounded-lg',
    // 主按钮（cyber 风）
    'btn-primary': 'px-6 py-3 rounded bg-gradient-to-r from-cyber-cyan to-cyber-purple text-black font-semibold cursor-pointer hover:opacity-90 transition-all',
    'btn-ghost': 'px-4 py-2 rounded border border-cyber-cyan/40 text-cyber-cyan cursor-pointer hover:bg-cyber-cyan/10 transition-all',
    // 标题渐变
    'title-gradient': 'bg-gradient-to-r from-cyber-cyan via-cyber-purple to-cyber-pink bg-clip-text text-transparent'
  },
  safelist: ['i-tabler-upload', 'i-tabler-rocket', 'i-tabler-chart-bar', 'i-tabler-world']
})
