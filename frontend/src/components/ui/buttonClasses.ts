export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'default' | 'sm'

// Primary buttons sit on the solid accent background. White label text only
// clears WCAG AA there at >=18.7px bold (computed 3.34:1 fails AA-normal,
// passes AA-large at that size/weight) - so `default` uses white, and `sm`
// (dense rows, toolbars) uses the near-black accent-foreground-small, which
// passes AA at any size instead of depending on a font-size threshold.
const VARIANT_SIZE_TEXT_COLOR: Record<ButtonVariant, Record<ButtonSize, string>> = {
  primary: { default: 'text-accent-foreground', sm: 'text-accent-foreground-small' },
  secondary: { default: 'text-text', sm: 'text-text' },
  ghost: { default: 'text-text-muted', sm: 'text-text-muted' },
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-accent shadow-sharp hover:brightness-110 active:shadow-pressed active:translate-y-px',
  secondary: 'bg-foreground shadow-sharp hover:brightness-110 active:shadow-pressed active:translate-y-px',
  ghost: 'bg-transparent hover:bg-[var(--foreground-translucent)] active:bg-foreground',
}

const SIZE_CLASSES: Record<ButtonSize, string> = {
  default: 'h-12 px-5 text-xl gap-2',
  sm: 'h-12 px-3 text-xs gap-1.5',
}

// Shared with non-<button> consumers that need Button's exact look (e.g. a
// react-router <Link> styled as a button, which can't literally be a
// <button>) so the recipe only ever lives in one place. Lives in its own
// file (not Button.tsx) because a file mixing a component export with a
// plain function export trips react-refresh/only-export-components.
export function buttonClasses(variant: ButtonVariant = 'primary', size: ButtonSize = 'default', className = ''): string {
  return `inline-flex min-w-[48px] items-center justify-center rounded-lg font-bold uppercase tracking-wide transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100 disabled:active:translate-y-0 disabled:active:shadow-sharp ${VARIANT_CLASSES[variant]} ${VARIANT_SIZE_TEXT_COLOR[variant][size]} ${SIZE_CLASSES[size]} ${className}`
}
