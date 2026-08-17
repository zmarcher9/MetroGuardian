import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  API_BASE_URL,
  checkRoute,
  deleteSavedRoute,
  getMe,
  ingestConstruction,
  ingestTraffic,
  listAlerts,
  listConstructionEvents,
  listTrafficEvents,
  login,
} from '../src/lib/api'

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('lib/api', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listAlerts calls the correct URL and returns parsed JSON', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: '1', type: 'traffic' }]))

    const result = await listAlerts(25)

    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/alerts?limit=25`, expect.any(Object))
    expect(result).toEqual([{ id: '1', type: 'traffic' }])
  })

  it('listTrafficEvents defaults limit to 50', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    await listTrafficEvents()
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/traffic-events?limit=50`, expect.any(Object))
  })

  it('listConstructionEvents hits the construction-events endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    await listConstructionEvents(10)
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/construction-events?limit=10`, expect.any(Object))
  })

  it('ingestTraffic POSTs with no body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ inserted_events: 3, generated_alerts: 1 }))
    const result = await ingestTraffic()
    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ method: 'POST' })
    expect(result).toEqual({ inserted_events: 3, generated_alerts: 1 })
  })

  it('ingestConstruction POSTs to the construction ingestion endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ inserted_events: 2, generated_alerts: 0 }))
    await ingestConstruction()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/ingest/construction`)
    expect(init).toMatchObject({ method: 'POST' })
  })

  it('checkRoute POSTs origin/destination as JSON', async () => {
    const origin = { lat: 47.6, lng: -122.3 }
    const destination = { lat: 47.7, lng: -122.4 }
    fetchMock.mockResolvedValueOnce(jsonResponse({ routes: [], recommended_index: 0 }))

    await checkRoute(origin, destination)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/route/check`)
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse(init.body as string)).toEqual({ origin, destination })
  })

  it('throws a descriptive error when the response is not ok', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('Alert not found', { status: 404, statusText: 'Not Found' }),
    )

    await expect(listAlerts()).rejects.toThrow('HTTP 404 Not Found — Alert not found')
  })
})

function unauthorized() {
  return new Response('Unauthorized', { status: 401, statusText: 'Unauthorized' })
}

const sampleUser = {
  id: 'u1',
  email: 'driver@example.com',
  is_admin: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('lib/api credentials, CSRF, and refresh interceptor', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    document.cookie = 'mg_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends credentials: include and the CSRF header (read from the cookie) on mutating requests', async () => {
    document.cookie = 'mg_csrf=test-csrf-token'
    fetchMock.mockResolvedValueOnce(jsonResponse(sampleUser))

    await login('driver@example.com', 'password1')

    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ credentials: 'include' })
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBe('test-csrf-token')
  })

  it('omits the CSRF header on GET requests', async () => {
    document.cookie = 'mg_csrf=test-csrf-token'
    fetchMock.mockResolvedValueOnce(jsonResponse(sampleUser))

    await getMe()

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined()
  })

  it('retries once after a silent refresh on a 401', async () => {
    fetchMock
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(jsonResponse({}))
      .mockResolvedValueOnce(jsonResponse(sampleUser))

    const result = await getMe()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_BASE_URL}/auth/refresh`)
    expect(result).toEqual(sampleUser)
  })

  it('retries a mutating request with a freshly-read CSRF header after a refresh', async () => {
    document.cookie = 'mg_csrf=stale-token'
    fetchMock
      .mockResolvedValueOnce(unauthorized())
      .mockImplementationOnce(async () => {
        // The refresh rotates the CSRF cookie, mirroring the real backend.
        document.cookie = 'mg_csrf=fresh-token'
        return jsonResponse({})
      })
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await deleteSavedRoute('r1')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const [, retryInit] = fetchMock.mock.calls[2]
    expect((retryInit.headers as Record<string, string>)['X-CSRF-Token']).toBe('fresh-token')
  })

  it('surfaces the original 401 when refresh also fails, without looping', async () => {
    fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(unauthorized())

    await expect(getMe()).rejects.toThrow('HTTP 401 Unauthorized')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('deduplicates concurrent refreshes triggered by simultaneous 401s', async () => {
    fetchMock
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(jsonResponse({}))
      .mockResolvedValueOnce(jsonResponse(sampleUser))
      .mockResolvedValueOnce(jsonResponse(sampleUser))

    const [a, b] = await Promise.all([getMe(), getMe()])

    expect(a).toEqual(sampleUser)
    expect(b).toEqual(sampleUser)
    expect(fetchMock).toHaveBeenCalledTimes(5)
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => url === `${API_BASE_URL}/auth/refresh`)
    expect(refreshCalls).toHaveLength(1)
  })
})
