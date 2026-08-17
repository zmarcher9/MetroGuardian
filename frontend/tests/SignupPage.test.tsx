import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SignupPage from '../src/pages/SignupPage'
import { AuthProvider } from '../src/lib/AuthContext'

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    getMe: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('../src/lib/api', () => apiMocks)

function renderSignup() {
  return render(
    <MemoryRouter initialEntries={['/signup']}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<div>Dashboard page</div>} />
          <Route path="/signup" element={<SignupPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('SignupPage', () => {
  beforeEach(() => {
    apiMocks.getMe.mockRejectedValue(new Error('HTTP 401 Unauthorized'))
  })

  it('signs up with the entered email and password', async () => {
    apiMocks.signup.mockResolvedValueOnce({
      id: 'u1',
      email: 'newdriver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    const user = userEvent.setup()

    renderSignup()
    await user.type(screen.getByLabelText(/email/i), 'newdriver@example.com')
    await user.type(screen.getByLabelText(/password/i), 'password1')
    await user.click(screen.getByRole('button', { name: /sign up/i }))

    await waitFor(() => expect(apiMocks.signup).toHaveBeenCalledWith('newdriver@example.com', 'password1'))
    await waitFor(() => expect(screen.getByText('Dashboard page')).toBeInTheDocument())
  })

  it('shows an error message when signup fails', async () => {
    apiMocks.signup.mockRejectedValueOnce(new Error('HTTP 409 Conflict — An account with this email already exists'))
    const user = userEvent.setup()

    renderSignup()
    await user.type(screen.getByLabelText(/email/i), 'newdriver@example.com')
    await user.type(screen.getByLabelText(/password/i), 'password1')
    await user.click(screen.getByRole('button', { name: /sign up/i }))

    await waitFor(() => expect(screen.getByText(/already exists/i)).toBeInTheDocument())
  })
})
