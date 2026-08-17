import { useState } from 'react'
import { AlertTriangle, MapPin } from 'lucide-react'
import { checkRoute, createSavedRoute, type LatLng, type RouteOption } from '../lib/api'
import { useAuth } from '../lib/useAuth'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { Led } from './ui/Led'

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
  const { user } = useAuth()
  const [origin, setOrigin] = useState<LatLng>(PRESETS[0].origin)
  const [destination, setDestination] = useState<LatLng>(PRESETS[0].destination)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [routes, setRoutes] = useState<RouteOption[]>([])
  const [recommendedIndex, setRecommendedIndex] = useState(0)
  const [checkedOrigin, setCheckedOrigin] = useState<LatLng | null>(null)
  const [checkedDestination, setCheckedDestination] = useState<LatLng | null>(null)
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function runCheck(o: LatLng = origin, d: LatLng = destination) {
    setLoading(true)
    setError(null)
    try {
      const res = await checkRoute(o, d)
      setRoutes(res.routes)
      setRecommendedIndex(res.recommended_index)
      setCheckedOrigin(o)
      setCheckedDestination(d)
      setSaved(false)
      props.onResult(res.routes, res.recommended_index)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRoutes([])
      props.onResult([], 0)
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!checkedOrigin || !checkedDestination) return
    setSaving(true)
    setSaveError(null)
    try {
      await createSavedRoute(saveName.trim() || 'Untitled route', checkedOrigin, checkedDestination)
      setSaved(true)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
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
            <Button key={preset.label} variant="secondary" size="sm" onClick={() => applyPreset(preset)}>
              <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
              {preset.label}
            </Button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-text-muted">
              Origin lat, lng
            </span>
            <div className="flex gap-1">
              <Input
                type="number"
                aria-label="Origin latitude"
                value={origin.lat}
                onChange={(e) => setOrigin({ ...origin, lat: Number(e.target.value) })}
              />
              <Input
                type="number"
                aria-label="Origin longitude"
                value={origin.lng}
                onChange={(e) => setOrigin({ ...origin, lng: Number(e.target.value) })}
              />
            </div>
          </div>
          <div>
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-text-muted">
              Destination lat, lng
            </span>
            <div className="flex gap-1">
              <Input
                type="number"
                aria-label="Destination latitude"
                value={destination.lat}
                onChange={(e) => setDestination({ ...destination, lat: Number(e.target.value) })}
              />
              <Input
                type="number"
                aria-label="Destination longitude"
                value={destination.lng}
                onChange={(e) => setDestination({ ...destination, lng: Number(e.target.value) })}
              />
            </div>
          </div>
        </div>

        <Button className="mt-3" onClick={() => void runCheck()} disabled={loading}>
          {loading ? 'Checking…' : 'Check route'}
        </Button>

        {error ? (
          <div className="mt-3 rounded-lg border border-accent bg-[var(--accent-tint)] p-3 text-sm text-text">{error}</div>
        ) : null}
      </div>

      <div className="text-sm">
        {routes.length === 0 ? (
          <div className="text-text-muted">Pick a preset or enter coordinates, then check a route.</div>
        ) : (
          <div className="space-y-3">
            {routes.map((route, i) => (
              <Card
                key={i}
                decorated={false}
                className={i === recommendedIndex ? 'shadow-[0_0_10px_2px_rgba(var(--success-rgb),0.35)]' : ''}
              >
                <div className="flex items-center justify-between">
                  {i === recommendedIndex ? (
                    <Led status="online" label="Recommended route" />
                  ) : (
                    <div className="font-medium text-text">Alternate {i}</div>
                  )}
                  <div className="font-mono text-xs text-text-muted">
                    {formatDistance(route.distance_meters)} &middot; {formatDuration(route.duration_seconds)}
                  </div>
                </div>
                {route.impacted_alerts.length === 0 ? (
                  <div className="mt-1 text-xs text-text-muted">No active incidents on this route.</div>
                ) : (
                  <ul className="mt-2 space-y-1 text-xs text-amber-300">
                    {route.impacted_alerts.map((a) => (
                      <li key={a.id} className="flex items-start gap-1.5">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                        <span>
                          {a.message} ({Math.round(a.distance_meters)}m away)
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
            {recommended && routes.length > 1 ? (
              <div className="text-xs text-text-muted">
                Recommended route has the lowest total incident severity of the {routes.length} options found.
              </div>
            ) : null}

            {user ? (
              <div className="flex items-center gap-2">
                <Input
                  type="text"
                  placeholder="Route name"
                  value={saveName}
                  onChange={(e) => {
                    setSaveName(e.target.value)
                    setSaved(false)
                  }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  className="shrink-0"
                  onClick={() => void handleSave()}
                  disabled={saving || saved}
                >
                  {saving ? 'Saving…' : saved ? 'Saved' : 'Save this route'}
                </Button>
              </div>
            ) : null}
            {saveError ? <div className="text-xs text-accent">{saveError}</div> : null}
          </div>
        )}
      </div>
    </div>
  )
}
