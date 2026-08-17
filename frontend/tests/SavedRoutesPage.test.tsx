import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SavedRoutesPage from '../src/pages/SavedRoutesPage'
import type { SavedRoute } from '../src/lib/api'

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    listSavedRoutes: vi.fn(),
    deleteSavedRoute: vi.fn(),
  },
}))

vi.mock('../src/lib/api', () => apiMocks)

const routes: SavedRoute[] = [
  {
    id: 'r1',
    name: 'Commute',
    origin: { lat: 47.6, lng: -122.3 },
    dest: { lat: 47.7, lng: -122.4 },
    waypoints: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
]

describe('SavedRoutesPage', () => {
  it('lists saved routes and deletes one', async () => {
    apiMocks.listSavedRoutes.mockResolvedValueOnce(routes)
    apiMocks.deleteSavedRoute.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()

    render(<SavedRoutesPage />)

    await waitFor(() => expect(screen.getByText('Commute')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /delete/i }))

    await waitFor(() => expect(screen.queryByText('Commute')).not.toBeInTheDocument())
    expect(apiMocks.deleteSavedRoute).toHaveBeenCalledWith('r1')
  })

  it('shows an empty state with no saved routes', async () => {
    apiMocks.listSavedRoutes.mockResolvedValueOnce([])

    render(<SavedRoutesPage />)

    await waitFor(() => expect(screen.getByText('No saved routes yet.')).toBeInTheDocument())
  })

  it('shows an error banner when listing saved routes fails', async () => {
    apiMocks.listSavedRoutes.mockRejectedValueOnce(new Error('HTTP 500 Internal Server Error'))

    render(<SavedRoutesPage />)

    await waitFor(() => expect(screen.getByText('HTTP 500 Internal Server Error')).toBeInTheDocument())
  })

  it('shows an error banner and keeps the row when deleting fails', async () => {
    apiMocks.listSavedRoutes.mockResolvedValueOnce(routes)
    apiMocks.deleteSavedRoute.mockRejectedValueOnce(new Error('HTTP 404 Not Found — Saved route not found'))
    const user = userEvent.setup()

    render(<SavedRoutesPage />)

    await waitFor(() => expect(screen.getByText('Commute')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /delete/i }))

    await waitFor(() => expect(screen.getByText(/saved route not found/i)).toBeInTheDocument())
    expect(screen.getByText('Commute')).toBeInTheDocument()
  })
})
