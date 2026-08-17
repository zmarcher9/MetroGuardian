import { useEffect, useState } from 'react'
import { deleteSavedRoute, listSavedRoutes, type SavedRoute } from '../lib/api'

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
      <h1 className="mb-4 text-lg font-semibold text-slate-100">Saved routes</h1>

      {error ? (
        <div className="mb-4 rounded-md border border-rose-900/50 bg-rose-950/40 p-3 text-sm text-rose-200">{error}</div>
      ) : null}

      {loading ? (
        <div className="text-sm text-slate-400">Loading…</div>
      ) : routes.length === 0 ? (
        <div className="text-sm text-slate-400">No saved routes yet.</div>
      ) : (
        <ul className="divide-y divide-slate-800 rounded-xl border border-slate-800 bg-slate-950/40">
          {routes.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-200">{r.name}</div>
                <div className="text-xs text-slate-500">
                  {r.origin.lat.toFixed(4)}, {r.origin.lng.toFixed(4)} &rarr; {r.dest.lat.toFixed(4)},{' '}
                  {r.dest.lng.toFixed(4)}
                </div>
              </div>
              <button
                onClick={() => void handleDelete(r.id)}
                className="shrink-0 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
