/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      colors: {
        // Buddilio brand — sampled from the logo lockup
        brand: {
          coral: '#FF9A62',
          pink: '#F0459B',
          magenta: '#E81E7C',
          violet: '#6B34CD',
          plum: '#52146F',
          ink: '#2A0836'
        },
        // Warm near-neutral scale: keeps a whisper of the plum without turning every page pink
        slate: {
          50: '#FAF9FA',
          100: '#F4F2F4',
          200: '#EAE6EA',
          300: '#D5CFD6',
          400: '#A29AA4',
          500: '#7A727C',
          600: '#5B535E',
          700: '#413A44',
          800: '#2B252E',
          900: '#1A0F1E',
          950: '#120A15'
        },
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(120deg, #FF9A62 0%, #F0459B 42%, #6B34CD 100%)',
        'brand-soft': 'linear-gradient(140deg, rgba(255,154,98,.18) 0%, rgba(240,69,155,.16) 45%, rgba(107,52,205,.18) 100%)'
      },
      boxShadow: {
        glow: '0 12px 34px rgba(232,30,124,.30)',
        'glow-lg': '0 20px 50px rgba(232,30,124,.34)'
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        },
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        marquee: 'marquee 32s linear infinite'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};
