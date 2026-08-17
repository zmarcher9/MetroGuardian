import type { HTMLAttributes, ReactNode } from 'react'

function CornerScrew({ className = '' }: Readonly<{ className?: string }>) {
  return (
    <span
      aria-hidden="true"
      className={`chassis-decoration absolute h-2 w-2 rounded-full bg-muted shadow-pressed ${className}`}
    />
  )
}

export function VentSlots({ className = '' }: Readonly<{ className?: string }>) {
  return (
    <span aria-hidden="true" className={`chassis-decoration inline-flex items-center gap-1 ${className}`}>
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className="h-3 w-0.5 rounded-full bg-muted shadow-pressed" />
      ))}
    </span>
  )
}

export type CardProps = HTMLAttributes<HTMLDivElement> & {
  decorated?: boolean
  floating?: boolean
  padded?: boolean
  children?: ReactNode
}

export function Card({
  decorated = true,
  floating = false,
  padded = true,
  className = '',
  children,
  ...props
}: Readonly<CardProps>) {
  return (
    <div
      className={`relative rounded-chassis bg-foreground ${padded ? 'p-5' : ''} ${floating ? 'shadow-floating' : 'shadow-card'} ${className}`}
      {...props}
    >
      {decorated ? (
        <>
          <CornerScrew className="left-2 top-2" />
          <CornerScrew className="right-2 top-2" />
          <CornerScrew className="bottom-2 left-2" />
          <CornerScrew className="bottom-2 right-2" />
        </>
      ) : null}
      {children}
    </div>
  )
}

export function CardHeader({ children, className = '' }: Readonly<{ children?: ReactNode; className?: string }>) {
  return <div className={`mb-3 flex items-center justify-between border-b border-border pb-3 ${className}`}>{children}</div>
}

export function CardTitle({ children, className = '' }: Readonly<{ children?: ReactNode; className?: string }>) {
  return <h2 className={`text-emboss text-sm font-semibold text-text ${className}`}>{children}</h2>
}
