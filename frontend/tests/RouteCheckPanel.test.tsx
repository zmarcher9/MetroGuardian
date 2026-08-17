import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RouteCheckPanel from '../src/components/RouteCheckPanel'
import { AuthProvider } from '../src/lib/AuthContext'
import type { RouteOption } from '../src/lib/api'

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    checkRoute: vi.fn(),
    createSavedRoute: vi.fn(),
    getMe: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('../src/lib/api', () => apiMocks)

function renderPanel(onResult = vi.fn()) {
  return render(
    <AuthProvider>
      <RouteCheckPanel onResult={onResult} />
    </AuthProvider>,
  )
}

const sampleUser = {
  id: 'u1',
  email: 'driver@example.com',
  is_admin: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const sampleRoute: RouteOption = {
  geometry: [
    { lat: 47.612, lng: -122.337 },
    { lat: 47.643, lng: -122.3 },
  ],
  distance_meters: 5000,
  duration_seconds: 720,
  impact_score: 4,
  impacted_alerts: [
    {
      id: 'a1',
      type: 'traffic',
      message: 'Slowdown on I-90',
      severity: 4,
      created_at: new Date().toISOString(),
      lat: 47.612,
      lng: -122.337,
      distance_meters: 42,
    },
  ],
}

describe('RouteCheckPanel', () => {
  beforeEach(() => {
    apiMocks.getMe.mockRejectedValue(new Error('HTTP 401 Unauthorized'))
  })

  it('renders route results and impacted alerts on success', async () => {
    apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
    const onResult = vi.fn()
    const user = userEvent.setup()

    renderPanel(onResult)
    await user.click(screen.getByRole('button', { name: /check route/i }))

    await waitFor(() => expect(screen.getByText(/slowdown on i-90/i)).toBeInTheDocument())
    expect(screen.getByText(/5.0 km/)).toBeInTheDocument()
    expect(onResult).toHaveBeenCalledWith([sampleRoute], 0)
  })

  it('shows an error message and clears results when checkRoute fails', async () => {
    apiMocks.checkRoute.mockRejectedValueOnce(new Error('HTTP 502 Bad Gateway'))
    const onResult = vi.fn()
    const user = userEvent.setup()

    renderPanel(onResult)
    await user.click(screen.getByRole('button', { name: /check route/i }))

    await waitFor(() => expect(screen.getByText('HTTP 502 Bad Gateway')).toBeInTheDocument())
    expect(onResult).toHaveBeenCalledWith([], 0)
  })

  it('clicking a preset fills coordinates and triggers a route check', async () => {
    apiMocks.checkRoute.mockResolvedValue({ routes: [], recommended_index: 0 })
    const onResult = vi.fn()
    const user = userEvent.setup()

    renderPanel(onResult)
    await user.click(screen.getByRole('button', { name: /1st ave → i-5/i }))

    await waitFor(() =>
      expect(apiMocks.checkRoute).toHaveBeenCalledWith({ lat: 47.604, lng: -122.3375 }, { lat: 47.6205, lng: -122.323 }),
    )
  })

  it('hides the save-route control when not authenticated', async () => {
    apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
    const user = userEvent.setup()

    renderPanel()
    await user.click(screen.getByRole('button', { name: /check route/i }))

    await waitFor(() => expect(screen.getByText(/slowdown on i-90/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /save this route/i })).not.toBeInTheDocument()
  })

  describe('when authenticated', () => {
    beforeEach(() => {
      apiMocks.getMe.mockResolvedValue(sampleUser)
    })

    it('saves the checked route', async () => {
      apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
      apiMocks.createSavedRoute.mockResolvedValueOnce({
        id: 'r1',
        name: 'My commute',
        origin: { lat: 47.612, lng: -122.337 },
        dest: { lat: 47.643, lng: -122.3 },
        waypoints: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      const user = userEvent.setup()

      renderPanel()
      await user.click(screen.getByRole('button', { name: /check route/i }))
      await waitFor(() => expect(screen.getByPlaceholderText('Route name')).toBeInTheDocument())

      await user.type(screen.getByPlaceholderText('Route name'), 'My commute')
      await user.click(screen.getByRole('button', { name: /save this route/i }))

      await waitFor(() => expect(screen.getByRole('button', { name: /^saved$/i })).toBeInTheDocument())
      expect(apiMocks.createSavedRoute).toHaveBeenCalledWith(
        'My commute',
        { lat: 47.612, lng: -122.337 },
        { lat: 47.643, lng: -122.3 },
      )
    })

    it('saves the coordinates that were checked, not ones edited afterward', async () => {
      apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
      apiMocks.createSavedRoute.mockResolvedValueOnce({
        id: 'r1',
        name: 'Untitled route',
        origin: { lat: 47.612, lng: -122.337 },
        dest: { lat: 47.643, lng: -122.3 },
        waypoints: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      const user = userEvent.setup()

      renderPanel()
      await user.click(screen.getByRole('button', { name: /check route/i }))
      await waitFor(() => expect(screen.getByPlaceholderText('Route name')).toBeInTheDocument())

      // Edit the origin lat input after checking, without re-checking.
      const originLatInput = screen.getByDisplayValue('47.612')
      await user.clear(originLatInput)
      await user.type(originLatInput, '10')

      await user.click(screen.getByRole('button', { name: /save this route/i }))

      await waitFor(() => expect(apiMocks.createSavedRoute).toHaveBeenCalled())
      expect(apiMocks.createSavedRoute).toHaveBeenCalledWith(
        'Untitled route',
        { lat: 47.612, lng: -122.337 },
        { lat: 47.643, lng: -122.3 },
      )
    })

    it('defaults the saved name to "Untitled route" when left blank', async () => {
      apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
      apiMocks.createSavedRoute.mockResolvedValueOnce({
        id: 'r1',
        name: 'Untitled route',
        origin: { lat: 47.612, lng: -122.337 },
        dest: { lat: 47.643, lng: -122.3 },
        waypoints: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
      const user = userEvent.setup()

      renderPanel()
      await user.click(screen.getByRole('button', { name: /check route/i }))
      await waitFor(() => expect(screen.getByPlaceholderText('Route name')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: /save this route/i }))

      await waitFor(() =>
        expect(apiMocks.createSavedRoute).toHaveBeenCalledWith(
          'Untitled route',
          expect.anything(),
          expect.anything(),
        ),
      )
    })

    it('shows an error when saving the route fails', async () => {
      apiMocks.checkRoute.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
      apiMocks.createSavedRoute.mockRejectedValueOnce(new Error('HTTP 422 Unprocessable Content — Cannot save more than 50 routes'))
      const user = userEvent.setup()

      renderPanel()
      await user.click(screen.getByRole('button', { name: /check route/i }))
      await waitFor(() => expect(screen.getByPlaceholderText('Route name')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: /save this route/i }))

      await waitFor(() => expect(screen.getByText(/cannot save more than 50 routes/i)).toBeInTheDocument())
      expect(screen.getByRole('button', { name: /save this route/i })).toBeInTheDocument()
    })
  })
})
