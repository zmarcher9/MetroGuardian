import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProtectedRoute from '../src/components/ProtectedRoute'
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

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/saved-routes']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route
            path="/saved-routes"
            element={
              <ProtectedRoute>
                <div>Secret saved routes</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('shows a loading state and neither redirects nor renders children before auth resolves', async () => {
    let resolveGetMe!: (user: unknown) => void
    apiMocks.getMe.mockReturnValueOnce(new Promise((resolve) => (resolveGetMe = resolve)))

    renderProtected()

    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.queryByText('Secret saved routes')).not.toBeInTheDocument()

    resolveGetMe({
      id: 'u1',
      email: 'driver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    await waitFor(() => expect(screen.getByText('Secret saved routes')).toBeInTheDocument())
  })

  it('redirects to /login when not authenticated', async () => {
    apiMocks.getMe.mockRejectedValueOnce(new Error('HTTP 401 Unauthorized'))

    renderProtected()

    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
    expect(screen.queryByText('Secret saved routes')).not.toBeInTheDocument()
  })

  it('renders the protected content when authenticated', async () => {
    apiMocks.getMe.mockResolvedValueOnce({
      id: 'u1',
      email: 'driver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })

    renderProtected()

    await waitFor(() => expect(screen.getByText('Secret saved routes')).toBeInTheDocument())
  })
})
