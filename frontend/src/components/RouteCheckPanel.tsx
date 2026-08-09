import { useState } from 'react'
import { checkRoute, type LatLng, type RouteOption } from '../lib/api'

type Preset = { label: string; origin: LatLng; destination: LatLng }

const PRESETS: Preset[] = [
  {
    label: 'I-90 → SR-520',
    origin: { lat: 47.612, lng: -122.337 },
    destination: { lat: 47.643, lng: -122.3 },
  },
  {
    label: '1st Ave → I-5',
    origin: { lat: 47.604, lng: -122.3375 },
    destination: { lat: 47.6205, lng: -122.323 },
  },
]

function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  return `${minutes} min`
}

function formatDistance(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}

export default function RouteCheckPanel(props: Readonly<{
  onResult: (routes: RouteOption[], recommendedIndex: number) => void
}>) {
  const [origin, setOrigin] = useState<LatLng>(PRESETS[0].origin)
  const [destination, setDestination] = useState<LatLng>(PRESETS[0].destination)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [routes, setRoutes] = useState<RouteOption[]>([])
  const [recommendedIndex, setRecommendedIndex] = useState(0)

  async function runCheck(o: LatLng = origin, d: LatLng = destination) {
    setLoading(true)
    setError(null)
    try {
      const res = await checkRoute(o, d)
      setRoutes(res.routes)
      setRecommendedIndex(res.recommended_index)
      props.onResult(res.routes, res.recommended_index)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRoutes([])
      props.onResult([], 0)
    } finally {
      setLoading(false)
    }
  }

  function applyPreset(preset: Preset) {
    setOrigin(preset.origin)
    setDestination(preset.destination)
    void runCheck(preset.origin, preset.destination)
  }

  const recommended = routes[recommendedIndex]

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
      <div>
        <div className="mb-2 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              onClick={() => applyPreset(preset)}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800"
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="flex flex-col gap-1 text-slate-400">
            Origin lat, lng
            <div className="flex gap-1">
              <input
                type="number"
                value={origin.lat}
                onChange={(e) => setOrigin({ ...origin, lat: Number(e.target.value) })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
              <input
                type="number"
                value={origin.lng}
                onChange={(e) => setOrigin({ ...origin, lng: Number(e.target.value) })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
            </div>
          </label>
          <label className="flex flex-col gap-1 text-slate-400">
            Destination lat, lng
            <div className="flex gap-1">
              <input
                type="number"
                value={destination.lat}
                onChange={(e) => setDestination({ ...destination, lat: Number(e.target.value) })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
              <input
                type="number"
                value={destination.lng}
                onChange={(e) => setDestination({ ...destination, lng: Number(e.target.value) })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
            </div>
          </label>
        </div>

        <button
          onClick={() => void runCheck()}
          disabled={loading}
          className="mt-3 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? 'Checking…' : 'Check route'}
        </button>

        {error ? (
          <div className="mt-3 rounded-md border border-rose-900/50 bg-rose-950/40 p-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}
      </div>

      <div className="text-sm">
        {routes.length === 0 ? (
          <div className="text-slate-400">Pick a preset or enter coordinates, then check a route.</div>
        ) : (
          <div className="space-y-3">
            {routes.map((route, i) => (
              <div
                key={i}
                className={`rounded-md border p-3 ${
                  i === recommendedIndex ? 'border-emerald-700 bg-emerald-950/30' : 'border-slate-800 bg-slate-950/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-medium text-slate-200">
                    {i === recommendedIndex ? 'Recommended route' : `Alternate ${i}`}
                  </div>
                  <div className="text-xs text-slate-400">
                    {formatDistance(route.distance_meters)} &middot; {formatDuration(route.duration_seconds)}
                  </div>
                </div>
                {route.impacted_alerts.length === 0 ? (
                  <div className="mt-1 text-xs text-slate-500">No active incidents on this route.</div>
                ) : (
                  <ul className="mt-1 space-y-1 text-xs text-amber-300">
                    {route.impacted_alerts.map((a) => (
                      <li key={a.id}>
                        {a.message} ({Math.round(a.distance_meters)}m away)
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {recommended && routes.length > 1 ? (
              <div className="text-xs text-slate-500">
                Recommended route has the lowest total incident severity of the {routes.length} options found.
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
