import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from '../src/pages/LoginPage'
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

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<div>Dashboard page</div>} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    apiMocks.getMe.mockRejectedValue(new Error('HTTP 401 Unauthorized'))
  })

  it('logs in with the entered email and password', async () => {
    apiMocks.login.mockResolvedValueOnce({
      id: 'u1',
      email: 'driver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    const user = userEvent.setup()

    renderLogin()
    await user.type(screen.getByLabelText(/email/i), 'driver@example.com')
    await user.type(screen.getByLabelText(/password/i), 'password1')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => expect(apiMocks.login).toHaveBeenCalledWith('driver@example.com', 'password1'))
    await waitFor(() => expect(screen.getByText('Dashboard page')).toBeInTheDocument())
  })

  it('shows an error message when login fails', async () => {
    apiMocks.login.mockRejectedValueOnce(new Error('HTTP 401 Unauthorized — Invalid email or password'))
    const user = userEvent.setup()

    renderLogin()
    await user.type(screen.getByLabelText(/email/i), 'driver@example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpass1')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument())
  })
})
