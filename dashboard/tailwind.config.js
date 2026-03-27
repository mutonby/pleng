/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          300: '#3eeabd',
          400: '#22d3a7',
          500: '#1a9e7e',
          600: '#158a6b',
          700: '#0f6e55',
        },
        surface: {
          700: '#181b24',
          800: '#13161e',
          850: '#0d0f14',
          900: '#08090d',
        },
        border: {
          DEFAULT: '#1e2230',
          bright: '#2a2f40',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
        sans: ['Instrument Sans', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['Playfair Display', 'Georgia', 'serif'],
      },
      boxShadow: {
        glow: '0 0 20px rgba(34, 211, 167, 0.15)',
        'glow-sm': '0 0 10px rgba(34, 211, 167, 0.1)',
      },
    },
  },
  plugins: [],
}
