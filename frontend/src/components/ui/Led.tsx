import type { HTMLAttributes } from 'react'

// LEDs pair with real state, not a static color - callers pass the actual
// status they're tracking (e.g. an SSE connection's open/error state),
// never a decorative always-on green dot.
export type LedStatus = 'online' | 'connecting' | 'offline' | 'error'

const STATUS_DOT_CLASSES: Record<LedStatus, string> = {
  online: 'bg-emerald-400 shadow-[0_0_8px_2px_rgba(var(--success-rgb),0.65)]',
  connecting: 'animate-pulse bg-amber-400 shadow-[0_0_8px_2px_rgba(251,191,36,0.6)]',
  offline: 'bg-[var(--text-muted-dim)]',
  error: 'bg-accent shadow-glow',
}

const STATUS_LABEL: Record<LedStatus, string> = {
  online: 'Live',
  connecting: 'Connecting…',
  offline: 'Offline',
  error: 'Error',
}

export type LedProps = HTMLAttributes<HTMLSpanElement> & {
  status: LedStatus
  label?: string
}

export function Led({ status, label, className = '', ...props }: Readonly<LedProps>) {
  const text = label ?? STATUS_LABEL[status]
  return (
    <span
      className={`inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-text-muted ${className}`}
      {...props}
    >
      <span
        role="status"
        aria-label={text}
        className={`h-2.5 w-2.5 shrink-0 rounded-full transition-colors duration-300 ${STATUS_DOT_CLASSES[status]}`}
      />
      {text}
    </span>
  )
}
