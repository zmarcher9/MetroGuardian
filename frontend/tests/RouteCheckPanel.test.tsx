import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import RouteCheckPanel from '../src/components/RouteCheckPanel'
import type { RouteOption } from '../src/lib/api'

const { checkRouteMock } = vi.hoisted(() => ({ checkRouteMock: vi.fn() }))

vi.mock('../src/lib/api', () => ({
  checkRoute: checkRouteMock,
}))

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
  it('renders route results and impacted alerts on success', async () => {
    checkRouteMock.mockResolvedValueOnce({ routes: [sampleRoute], recommended_index: 0 })
    const onResult = vi.fn()
    const user = userEvent.setup()

    render(<RouteCheckPanel onResult={onResult} />)
    await user.click(screen.getByRole('button', { name: /check route/i }))

    await waitFor(() => expect(screen.getByText(/slowdown on i-90/i)).toBeInTheDocument())
    expect(screen.getByText(/5.0 km/)).toBeInTheDocument()
    expect(onResult).toHaveBeenCalledWith([sampleRoute], 0)
  })

  it('shows an error message and clears results when checkRoute fails', async () => {
    checkRouteMock.mockRejectedValueOnce(new Error('HTTP 502 Bad Gateway'))
    const onResult = vi.fn()
    const user = userEvent.setup()

    render(<RouteCheckPanel onResult={onResult} />)
    await user.click(screen.getByRole('button', { name: /check route/i }))

    await waitFor(() => expect(screen.getByText('HTTP 502 Bad Gateway')).toBeInTheDocument())
    expect(onResult).toHaveBeenCalledWith([], 0)
  })

  it('clicking a preset fills coordinates and triggers a route check', async () => {
    checkRouteMock.mockResolvedValue({ routes: [], recommended_index: 0 })
    const onResult = vi.fn()
    const user = userEvent.setup()

    render(<RouteCheckPanel onResult={onResult} />)
    await user.click(screen.getByRole('button', { name: /1st ave → i-5/i }))

    await waitFor(() =>
      expect(checkRouteMock).toHaveBeenCalledWith({ lat: 47.604, lng: -122.3375 }, { lat: 47.6205, lng: -122.323 }),
    )
  })
})
