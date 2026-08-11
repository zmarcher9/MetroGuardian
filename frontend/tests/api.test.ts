import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  API_BASE_URL,
  checkRoute,
  ingestConstruction,
  ingestTraffic,
  listAlerts,
  listConstructionEvents,
  listTrafficEvents,
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
