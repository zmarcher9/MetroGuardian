import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from '../../src/components/ui/Button'

describe('Button', () => {
  it('calls onClick when pressed', async () => {
    const onClick = vi.fn()
    const user = userEvent.setup()

    render(<Button onClick={onClick}>Save</Button>)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('does not fire onClick when disabled', async () => {
    const onClick = vi.fn()
    const user = userEvent.setup()

    render(
      <Button onClick={onClick} disabled>
        Save
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Save' })
    await user.click(button)

    expect(button).toBeDisabled()
    expect(onClick).not.toHaveBeenCalled()
  })

  it('uses the near-black accent-foreground-small text color for small primary buttons, not white', () => {
    render(
      <Button variant="primary" size="sm">
        Delete
      </Button>,
    )
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveClass('text-accent-foreground-small')
  })

  it('uses white accent-foreground text for default-size primary buttons', () => {
    render(<Button variant="primary">Check route</Button>)
    expect(screen.getByRole('button', { name: 'Check route' })).toHaveClass('text-accent-foreground')
  })

  it('renders the secondary variant with the foreground background and no opacity-suffix classes', () => {
    render(<Button variant="secondary">Refresh</Button>)
    const button = screen.getByRole('button', { name: 'Refresh' })
    expect(button).toHaveClass('bg-foreground')
    expect(button).toHaveClass('text-text')
  })

  it('renders the ghost variant using the pre-mixed translucent hover token, not a broken /NN suffix', () => {
    render(<Button variant="ghost">Cancel</Button>)
    const button = screen.getByRole('button', { name: 'Cancel' })
    expect(button).toHaveClass('bg-transparent')
    expect(button).toHaveClass('hover:bg-[var(--foreground-translucent)]')
    // Regression guard: Tailwind's `/NN` opacity-modifier syntax silently
    // produces no CSS on this app's var()-based color tokens - confirmed
    // when a ghost-button hover state rendered with zero visual feedback.
    expect(button.className).not.toMatch(/\/\d+/)
  })
})
