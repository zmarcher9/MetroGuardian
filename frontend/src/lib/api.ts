const DEFAULT_BASE = '/api/v1'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_BASE

const CSRF_COOKIE_NAME = 'mg_csrf'
const CSRF_HEADER_NAME = 'X-CSRF-Token'

function getCsrfToken(): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE_NAME}=([^;]*)`))
  if (!match) return ''
  try {
    return decodeURIComponent(match[1])
  } catch {
    return match[1]
  }
}

async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (method !== 'GET' && method !== 'HEAD') {
    headers[CSRF_HEADER_NAME] = getCsrfToken()
  }
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })
}

async function throwForStatus(res: Response): Promise<never> {
  const text = await res.text().catch(() => '')
  const suffix = text ? ` — ${text}` : ''
  throw new Error(`HTTP ${res.status} ${res.statusText}${suffix}`)
}

// A 401 from any endpoint other than /auth/refresh itself triggers a single
// silent refresh attempt, then retries the original request once. Concurrent
// 401s share one in-flight refresh instead of each firing their own.
let refreshPromise: Promise<void> | null = null

async function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const res = await rawFetch('/auth/refresh', { method: 'POST' })
      if (!res.ok) await throwForStatus(res)
    })().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function http<T>(path: string, init?: RequestInit, _retried = false): Promise<T> {
  const res = await rawFetch(path, init)
  if (res.status === 401 && !_retried && path !== '/auth/refresh') {
    try {
      await refreshSession()
    } catch {
      return throwForStatus(res)
    }
    return http<T>(path, init, true)
  }
  if (!res.ok) return throwForStatus(res)
  if (res.status === 204) return undefined as T
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

export type LatLng = {
  lat: number
  lng: number
}

export type ImpactedAlert = {
  id: string
  type: string
  message: string
  severity: number
  created_at: string
  lat: number
  lng: number
  distance_meters: number
}

export type RouteOption = {
  geometry: LatLng[]
  distance_meters: number
  duration_seconds: number
  impact_score: number
  impacted_alerts: ImpactedAlert[]
}

export type RouteCheckResponse = {
  routes: RouteOption[]
  recommended_index: number
}

export async function checkRoute(origin: LatLng, destination: LatLng) {
  return http<RouteCheckResponse>(`/route/check`, {
    method: 'POST',
    body: JSON.stringify({ origin, destination }),
  })
}

export type User = {
  id: string
  email: string
  is_admin: boolean
  created_at: string
  updated_at: string
}

export async function signup(email: string, password: string) {
  return http<User>(`/auth/signup`, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function login(email: string, password: string) {
  return http<User>(`/auth/login`, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function getMe() {
  return http<User>(`/auth/me`)
}

export async function logout() {
  await http<void>(`/auth/logout`, { method: 'POST' })
}

export type SavedRoute = {
  id: string
  name: string
  origin: LatLng
  dest: LatLng
  waypoints: LatLng[] | null
  created_at: string
  updated_at: string
}

export async function createSavedRoute(name: string, origin: LatLng, dest: LatLng, waypoints?: LatLng[] | null) {
  return http<SavedRoute>(`/saved-routes`, {
    method: 'POST',
    body: JSON.stringify({ name, origin, dest, waypoints: waypoints ?? null }),
  })
}

export async function listSavedRoutes(limit = 100) {
  return http<SavedRoute[]>(`/saved-routes?limit=${limit}`)
}

export async function deleteSavedRoute(id: string) {
  await http<void>(`/saved-routes/${id}`, { method: 'DELETE' })
}

