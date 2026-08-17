import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { deleteSavedRoute, listSavedRoutes, type SavedRoute } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

export default function SavedRoutesPage() {
  const [routes, setRoutes] = useState<SavedRoute[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setError(null)
    setLoading(true)
    try {
      setRoutes(await listSavedRoutes())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function handleDelete(id: string) {
    setError(null)
    try {
      await deleteSavedRoute(id)
      setRoutes((prev) => prev.filter((r) => r.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-emboss mb-4 text-lg font-bold text-text">Saved routes</h1>

      {error ? (
        <div className="mb-4 rounded-lg border border-accent bg-[var(--accent-tint)] p-3 text-sm text-text">{error}</div>
      ) : null}

      {loading ? (
        <div className="text-sm text-text-muted">Loading…</div>
      ) : routes.length === 0 ? (
        <div className="text-sm text-text-muted">No saved routes yet.</div>
      ) : (
        <Card decorated={false} padded={false}>
          <ul className="divide-y divide-border-light">
            {routes.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text">{r.name}</div>
                  <div className="font-mono text-xs text-text-muted">
                    {r.origin.lat.toFixed(4)}, {r.origin.lng.toFixed(4)} &rarr; {r.dest.lat.toFixed(4)},{' '}
                    {r.dest.lng.toFixed(4)}
                  </div>
                </div>
                <Button variant="secondary" size="sm" className="shrink-0" onClick={() => void handleDelete(r.id)}>
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
