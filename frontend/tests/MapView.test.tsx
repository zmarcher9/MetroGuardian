import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import MapView from '../src/components/MapView'
import type { ConstructionEvent, RouteOption, TrafficEvent } from '../src/lib/api'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  CircleMarker: ({ children }: { children?: ReactNode }) => <div data-testid="circle-marker">{children}</div>,
  Polyline: () => <div data-testid="polyline" />,
  Popup: ({ children }: { children?: ReactNode }) => <div data-testid="popup">{children}</div>,
}))

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

const constructionEvents: ConstructionEvent[] = [
  {
    id: 'c1',
    source: 'sample',
    road_name: 'Pine St',
    lat: 47.61,
    lng: -122.334,
    description: 'Lane closed near 3rd Ave',
    keyword: 'lane_closed',
    start_time: new Date().toISOString(),
    end_time: null,
    ingested_at: new Date().toISOString(),
  },
]

const routes: RouteOption[] = [
  {
    geometry: [
      { lat: 47.612, lng: -122.337 },
      { lat: 47.643, lng: -122.3 },
    ],
    distance_meters: 4200,
    duration_seconds: 600,
    impact_score: 0,
    impacted_alerts: [],
  },
]

describe('MapView', () => {
  it('renders one marker per traffic and construction event', () => {
    render(<MapView trafficEvents={trafficEvents} constructionEvents={constructionEvents} />)
    expect(screen.getAllByTestId('circle-marker')).toHaveLength(2)
  })

  it('renders a polyline per route', () => {
    render(<MapView trafficEvents={[]} constructionEvents={[]} routes={routes} recommendedIndex={0} />)
    expect(screen.getAllByTestId('polyline')).toHaveLength(1)
  })

  it('renders no markers or polylines when there is no data', () => {
    render(<MapView trafficEvents={[]} constructionEvents={[]} />)
    expect(screen.queryByTestId('circle-marker')).not.toBeInTheDocument()
    expect(screen.queryByTestId('polyline')).not.toBeInTheDocument()
  })
})
