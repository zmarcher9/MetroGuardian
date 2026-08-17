import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import type { ConstructionEvent, PipelineAlert, TrafficEvent, User } from '../src/lib/api'
import { MockEventSource } from './setup'

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    listAlerts: vi.fn(),
    listTrafficEvents: vi.fn(),
    listConstructionEvents: vi.fn(),
    ingestTraffic: vi.fn(),
    ingestConstruction: vi.fn(),
    alertsEventSource: vi.fn(),
    getMe: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    checkRoute: vi.fn(),
    createSavedRoute: vi.fn(),
    listSavedRoutes: vi.fn(),
    deleteSavedRoute: vi.fn(),
  },
}))

vi.mock('../src/lib/api', () => apiMocks)

function renderApp() {
  return render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  )
}

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Polyline: () => null,
  Popup: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))

const alerts: PipelineAlert[] = [
  {
    id: 'a1',
    type: 'traffic',
    message: 'Speed dropped on I-90',
    severity: 3,
    confidence: 0.75,
    related_traffic_event_id: null,
    related_construction_event_id: null,
    created_at: new Date().toISOString(),
  },
]

const trafficEvents: TrafficEvent[] = [
  {
    id: 't1',
    source: 'simulated',
    road_name: 'I-90',
    segment_key: 'i90:wb:1',
    lat: 47.612,
    lng: -122.337,
    speed_kph: 42.5,
    observed_at: new Date().toISOString(),
  },
]

const constructionEvents: ConstructionEvent[] = []

describe('App', () => {
  beforeEach(() => {
    apiMocks.listAlerts.mockResolvedValue(alerts)
    apiMocks.listTrafficEvents.mockResolvedValue(trafficEvents)
    apiMocks.listConstructionEvents.mockResolvedValue(constructionEvents)
    apiMocks.alertsEventSource.mockImplementation(() => new MockEventSource('/api/v1/alerts/stream'))
    apiMocks.getMe.mockRejectedValue(new Error('HTTP 401 Unauthorized'))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads and displays alerts, traffic, and construction counts', async () => {
    renderApp()

    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0)

    await waitFor(() => expect(screen.getByText('Speed dropped on I-90')).toBeInTheDocument())
    // "Traffic events" / "Construction events" appear twice: once as a Stat
    // tile title, once as a Panel heading. The Stat tiles render first.
    expect(screen.getAllByText('Alerts')[0].parentElement).toHaveTextContent('1')
    expect(screen.getAllByText('Traffic events')[0].parentElement).toHaveTextContent('1')
    expect(screen.getAllByText('Construction events')[0].parentElement).toHaveTextContent('0')
  })

  it('shows an error banner when loading fails', async () => {
    apiMocks.listAlerts.mockRejectedValueOnce(new Error('HTTP 500 Internal Server Error'))

    renderApp()

    await waitFor(() => expect(screen.getByText('HTTP 500 Internal Server Error')).toBeInTheDocument())
  })

  it('prepends alerts pushed over the live SSE stream', async () => {
    renderApp()
    await waitFor(() => expect(screen.getByText('Speed dropped on I-90')).toBeInTheDocument())

    const source = apiMocks.alertsEventSource.mock.results[0]!.value as MockEventSource
    source.dispatch('alert', {
      id: 'a2',
      type: 'construction',
      message: 'New live alert',
      severity: 2,
      confidence: 0.6,
      related_traffic_event_id: null,
      related_construction_event_id: null,
      created_at: new Date().toISOString(),
    })

    await waitFor(() => expect(screen.getByText('New live alert')).toBeInTheDocument())
  })

  it('reflects the real SSE connection status via the Led, not a static indicator', async () => {
    renderApp()

    // Asserted synchronously, before MockEventSource's queued 'open' event
    // has a chance to fire: proves the Led starts at 'connecting' rather
    // than being hardcoded to show "Live" from the moment it mounts.
    expect(screen.getByRole('status', { name: 'Connecting…' })).toBeInTheDocument()

    await waitFor(() => expect(screen.getByText('Speed dropped on I-90')).toBeInTheDocument())

    // MockEventSource auto-fires 'open' on construction (see tests/setup.ts).
    await waitFor(() => expect(screen.getByRole('status', { name: 'Live' })).toBeInTheDocument())

    const source = apiMocks.alertsEventSource.mock.results[0]!.value as MockEventSource
    source.dispatch('error')

    await waitFor(() => expect(screen.getByRole('status', { name: 'Error' })).toBeInTheDocument())
  })

  it('shows Offline once the Live toggle is switched off', async () => {
    const user = userEvent.setup()
    renderApp()
    await waitFor(() => expect(screen.getByRole('status', { name: 'Live' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /^live$/i }))

    await waitFor(() => expect(screen.getByRole('status', { name: 'Offline' })).toBeInTheDocument())
  })

  it('shows login/signup links when logged out', async () => {
    renderApp()
    await waitFor(() => expect(apiMocks.getMe).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('link', { name: /log in/i })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /sign up/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /saved routes/i })).not.toBeInTheDocument()
  })

  it('shows the user email and a saved-routes link when logged in', async () => {
    apiMocks.getMe.mockResolvedValue({
      id: 'u1',
      email: 'driver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    renderApp()
    await waitFor(() => expect(screen.getByText('driver@example.com')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /saved routes/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument()
  })

  it('hides the admin-only ingest buttons for logged-out users', async () => {
    renderApp()
    await waitFor(() => expect(apiMocks.getMe).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('link', { name: /log in/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /ingest traffic/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ingest construction/i })).not.toBeInTheDocument()
  })

  it('hides the admin-only ingest buttons for a logged-in non-admin user', async () => {
    apiMocks.getMe.mockResolvedValue({
      id: 'u2',
      email: 'driver@example.com',
      is_admin: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    renderApp()
    await waitFor(() => expect(screen.getByText('driver@example.com')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /ingest traffic/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ingest construction/i })).not.toBeInTheDocument()
  })

  it('hides the admin-only ingest buttons when is_admin is missing from the user response', async () => {
    apiMocks.getMe.mockResolvedValue({
      id: 'u4',
      email: 'driver@example.com',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as Omit<User, 'is_admin'> as User)
    renderApp()
    await waitFor(() => expect(screen.getByText('driver@example.com')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /ingest traffic/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ingest construction/i })).not.toBeInTheDocument()
  })

  it('shows the admin-only ingest buttons for admin users', async () => {
    apiMocks.getMe.mockResolvedValue({
      id: 'u3',
      email: 'admin@example.com',
      is_admin: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    renderApp()
    await waitFor(() => expect(screen.getByText('admin@example.com')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /ingest traffic/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ingest construction/i })).toBeInTheDocument()
  })
})
