import type { HTMLAttributes } from 'react'
import type { LucideIcon } from 'lucide-react'

export type IconBadgeTone = 'neutral' | 'accent' | 'info' | 'warning' | 'success'

// `accent` tone uses accent-foreground-small (near-black), not white - these
// badges render well under 18.7px, so they must use the contrast-safe-at-any-size
// text color rather than the large-text-only white variant (see Button.tsx).
const TONE_CLASSES: Record<IconBadgeTone, string> = {
  neutral: 'bg-muted text-text-muted',
  accent: 'bg-accent text-accent-foreground-small',
  info: 'bg-sky-500/15 text-sky-300',
  warning: 'bg-amber-500/15 text-amber-300',
  success: 'bg-emerald-500/15 text-emerald-300',
}

export type IconBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  icon?: LucideIcon
  tone?: IconBadgeTone
}

export function IconBadge({ icon: Icon, tone = 'neutral', className = '', children, ...props }: Readonly<IconBadgeProps>) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold uppercase tracking-wide shadow-sharp ${TONE_CLASSES[tone]} ${className}`}
      {...props}
    >
      {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
      {children}
    </span>
  )
}
