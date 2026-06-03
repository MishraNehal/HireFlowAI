/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f7ff',
          100: '#ebf0ff',
          200: '#d6e0ff',
          300: '#adc2ff',
          400: '#7fa3ff',
          500: '#4d7cff',
          600: '#335eff',
          700: '#264adb',
          800: '#1f3cb3',
          900: '#1c348a',
        }
      }
    },
  },
  plugins: [],
}
