/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        muted: 'var(--muted)',
        text: 'var(--text)',
        'text-muted': 'var(--text-muted)',
        accent: 'var(--accent)',
        'accent-foreground': 'var(--accent-foreground)',
        'accent-foreground-small': 'var(--accent-foreground-small)',
        border: 'var(--border)',
        'border-light': 'var(--border-light)',
        'border-dark': 'var(--border-dark)',
      },
      // Neumorphic dual-shadow recipes. Colors are CSS custom properties
      // (--border/--border-light are the shadow-dark/shadow-light halves),
      // never restated as literal values here - see index.css :root.
      boxShadow: {
        card: '8px 8px 16px var(--border), -8px -8px 16px var(--border-light)',
        floating:
          '12px 12px 24px var(--border), -12px -12px 24px var(--border-light), inset 1px 1px 0 rgba(255,255,255,0.06)',
        pressed: 'inset 6px 6px 12px var(--border), inset -6px -6px 12px var(--border-light)',
        recessed: 'inset 4px 4px 8px var(--border), inset -4px -4px 8px var(--border-light)',
        sharp: '4px 4px 8px rgba(0,0,0,0.5), -1px -1px 1px rgba(255,255,255,0.12)',
        glow: '0 0 10px 2px rgba(255,71,87,0.6)',
      },
      borderRadius: {
        chassis: '1.25rem',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
