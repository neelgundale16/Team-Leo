import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      animation: {
        'fade-in':           'fadeIn 0.15s ease-in',
        'correction-flash':  'correctionFlash 0.6s ease-out',
        'slide-in':          'slideIn 0.3s ease-out',
        'pulse-slow':        'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        correctionFlash: {
          '0%':   { backgroundColor: '#166534', boxShadow: '0 0 12px #16a34a' },
          '50%':  { backgroundColor: '#14532d', boxShadow: '0 0 20px #22c55e' },
          '100%': { backgroundColor: '#14532d', boxShadow: 'none' },
        },
        slideIn: {
          '0%':   { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      colors: {
        'veracity-red':   '#dc2626',
        'veracity-dark':  '#0a0a0a',
        'veracity-card':  '#0d0d0d',
        'veracity-border':'#222222',
      },
    },
  },
  plugins: [],
}

export default config