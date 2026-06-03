/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class', // 配合 Element Plus 的 dark mode 类名
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#ecf5ff',
          100: '#d6eaff',
          200: '#adcfff',
          300: '#79bbff',
          400: '#3d9cff',
          500: '#409eff',
          600: '#1c86ee',
          700: '#0a6fe3',
          800: '#0058c7',
          900: '#004494',
        },
      },
      spacing: {
        '18': '4.5rem',
      },
    },
  },
  plugins: [],
}
