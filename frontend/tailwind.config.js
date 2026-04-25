/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        display: ['Syne', 'sans-serif'],
      },
      colors: {
        // Neutral slate base
        surface: {
          DEFAULT: '#F8F8F7',
          50: '#FAFAF9',
          100: '#F4F4F2',
          200: '#E8E8E5',
          300: '#D1D1CB',
          400: '#A8A89F',
          500: '#7A7A72',
          600: '#5A5A53',
          700: '#3D3D38',
          800: '#252521',
          900: '#131310',
          950: '#0A0A08',
        },
        // Accent — sharp amber-gold
        accent: {
          DEFAULT: '#D4A847',
          50: '#FDF8EC',
          100: '#FAEFC9',
          200: '#F5DC90',
          300: '#EFC55A',
          400: '#E8B030',
          500: '#D4A847',
          600: '#B8891A',
          700: '#8F6A14',
          800: '#664C0F',
          900: '#3D2D09',
        },
        // Status colors
        status: {
          draft: '#7A7A72',
          sent: '#3B82F6',
          paid: '#22C55E',
          overdue: '#EF4444',
        }
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.04)',
        'card-hover': '0 4px 12px 0 rgba(0,0,0,0.10), 0 2px 4px -1px rgba(0,0,0,0.06)',
        'panel': '0 8px 32px 0 rgba(0,0,0,0.12)',
      },
      animation: {
        'slide-in-right': 'slideInRight 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-up': 'fadeUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
      },
      keyframes: {
        slideInRight: {
          from: { transform: 'translateX(100%)', opacity: '0' },
          to: { transform: 'translateX(0)', opacity: '1' },
        },
        fadeUp: {
          from: { transform: 'translateY(8px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        }
      }
    },
  },
  plugins: [],
}