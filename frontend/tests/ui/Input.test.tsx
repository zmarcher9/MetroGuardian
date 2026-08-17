import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Input } from '../../src/components/ui/Input'

describe('Input', () => {
  it('associates its label via htmlFor/id', () => {
    render(<Input id="email" label="Email" />)
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
  })

  it('renders without a wrapping label when none is given', () => {
    const { container } = render(<Input aria-label="Origin latitude" />)
    expect(container.querySelector('label')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Origin latitude')).toBeInTheDocument()
  })

  it('becomes the active element when focused and reports typed input', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<Input id="email" label="Email" value="" onChange={onChange} />)
    const input = screen.getByLabelText('Email')

    await user.click(input)
    expect(input).toHaveFocus()

    await user.type(input, 'a')
    expect(onChange).toHaveBeenCalled()
  })

  it('is not focusable when disabled', () => {
    render(<Input id="email" label="Email" disabled />)
    expect(screen.getByLabelText('Email')).toBeDisabled()
  })
})
