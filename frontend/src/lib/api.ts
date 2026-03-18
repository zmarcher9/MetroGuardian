const DEFAULT_BASE = '/api/v1'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_BASE

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? undefined),
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const suffix = text ? ` — ${text}` : ''
    throw new Error(`HTTP ${res.status} ${res.statusText}${suffix}`)
  }
  return (await res.json()) as T
}

export type PipelineAlert = {
  id: string
  type: string
  message: string
  severity: number
  confidence: number | null
  related_traffic_event_id: string | null
  related_construction_event_id: string | null
  created_at: string
}

export type TrafficEvent = {
  id: string
  source: string
  road_name: string
  segment_key: string
  lat: number
  lng: number
  speed_kph: number
  observed_at: string
}

export type ConstructionEvent = {
  id: string
  source: string
  road_name: string
  lat: number
  lng: number
  description: string
  keyword: string | null
  start_time: string
  end_time: string | null
  ingested_at: string
}

export async function listAlerts(limit = 50) {
  return http<PipelineAlert[]>(`/alerts?limit=${limit}`)
}

export async function listTrafficEvents(limit = 50) {
  return http<TrafficEvent[]>(`/traffic-events?limit=${limit}`)
}

export async function listConstructionEvents(limit = 50) {
  return http<ConstructionEvent[]>(`/construction-events?limit=${limit}`)
}

export async function ingestTraffic() {
  return http<{ inserted_events: number; generated_alerts: number }>(`/ingest/traffic`, { method: 'POST' })
}

export async function ingestConstruction() {
  return http<{ inserted_events: number; generated_alerts: number }>(`/ingest/construction`, { method: 'POST' })
}

export function alertsEventSource(): EventSource {
  const url = `${API_BASE_URL}/alerts/stream`
  return new EventSource(url)
}

