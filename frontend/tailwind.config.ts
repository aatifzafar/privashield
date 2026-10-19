import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#08111f',
        navy: '#0d1c31',
        cyan: '#34d6d0',
        mint: '#b9f3de',
        cloud: '#f4f7fb',
        line: '#dce5ef',
        warning: '#f5b949',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 18px 48px rgba(13, 28, 49, 0.08)',
        float: '0 24px 72px rgba(6, 22, 38, 0.18)',
      },
      backgroundImage: {
        'dot-grid': 'radial-gradient(rgba(50, 119, 142, 0.16) 1px, transparent 1px)',
      },
    },
  },
  plugins: [],
} satisfies Config
