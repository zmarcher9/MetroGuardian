import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import type { ConstructionEvent, PipelineAlert, TrafficEvent } from '../src/lib/api'
import { MockEventSource } from './setup'

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    listAlerts: vi.fn(),
    listTrafficEvents: vi.fn(),
    listConstructionEvents: vi.fn(),
    ingestTraffic: vi.fn(),
    ingestConstruction: vi.fn(),
    alertsEventSource: vi.fn(),
  },
}))

vi.mock('../src/lib/api', () => apiMocks)

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
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads and displays alerts, traffic, and construction counts', async () => {
    render(<App />)

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

    render(<App />)

    await waitFor(() => expect(screen.getByText('HTTP 500 Internal Server Error')).toBeInTheDocument())
  })

  it('prepends alerts pushed over the live SSE stream', async () => {
    render(<App />)
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
})
