import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Led } from '../../src/components/ui/Led'

describe('Led', () => {
  it('shows the Live label and a green dot when online', () => {
    render(<Led status="online" />)
    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Live' })).toHaveClass('bg-emerald-400')
  })

  it('shows the Connecting label and an amber dot when connecting', () => {
    render(<Led status="connecting" />)
    expect(screen.getByText('Connecting…')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Connecting…' })).toHaveClass('bg-amber-400')
  })

  it('shows the Error label and the accent-colored dot on error', () => {
    render(<Led status="error" />)
    expect(screen.getByText('Error')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Error' })).toHaveClass('bg-accent')
  })

  it('shows the Offline label and a dimmed dot when offline', () => {
    render(<Led status="offline" />)
    expect(screen.getByText('Offline')).toBeInTheDocument()
    // Not `bg-text-muted/40`: Tailwind's opacity-modifier syntax silently
    // produces no CSS when the base color is a var()-based custom token
    // (confirmed the hard way - this dot rendered fully invisible). The
    // fix is a dedicated pre-mixed --text-muted-dim token instead.
    const dot = screen.getByRole('status', { name: 'Offline' })
    expect(dot).toHaveClass('bg-[var(--text-muted-dim)]')
    expect(dot.className).not.toMatch(/\/\d+/)
  })

  it('accepts a custom label overriding the default status text', () => {
    render(<Led status="online" label="Recommended route" />)
    expect(screen.getByText('Recommended route')).toBeInTheDocument()
  })
})
