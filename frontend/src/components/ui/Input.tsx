import { forwardRef, type InputHTMLAttributes } from 'react'

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(({ label, id, className = '', ...props }, ref) => {
  const input = (
    <input
      ref={ref}
      id={id}
      className={`h-12 w-full rounded-lg bg-muted px-3 font-mono text-text shadow-recessed outline-none transition-shadow duration-150 placeholder:text-text-muted focus:shadow-glow disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    />
  )
  if (!label) return input
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
      {label}
      {input}
    </label>
  )
})
Input.displayName = 'Input'
