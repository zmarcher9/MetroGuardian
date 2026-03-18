import { useEffect, useMemo, useState } from 'react'
import {
  alertsEventSource,
  ingestConstruction,
  ingestTraffic,
  listAlerts,
  listConstructionEvents,
  listTrafficEvents,
  type ConstructionEvent,
  type PipelineAlert,
  type TrafficEvent,
} from './lib/api'

function alertTypeClass(type: string) {
  if (type === 'traffic') return 'text-amber-300'
  if (type === 'construction') return 'text-sky-300'
  return 'text-slate-200'
}

function App() {
  const [alerts, setAlerts] = useState<PipelineAlert[]>([])
  const [traffic, setTraffic] = useState<TrafficEvent[]>([])
  const [construction, setConstruction] = useState<ConstructionEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(true)

  async function refresh() {
    setError(null)
    setLoading(true)
    try {
      const [a, t, c] = await Promise.all([listAlerts(50), listTrafficEvents(50), listConstructionEvents(50)])
      setAlerts(a)
      setTraffic(t)
      setConstruction(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  useEffect(() => {
    if (!live) return
    const es = alertsEventSource()
    const onAlert = (ev: MessageEvent) => {
      try {
        const a = JSON.parse(ev.data) as PipelineAlert
        setAlerts((prev) => [a, ...prev].slice(0, 50))
      } catch {
        // ignore
      }
    }
    es.addEventListener('alert', onAlert as EventListener)
    return () => {
      es.removeEventListener('alert', onAlert as EventListener)
      es.close()
    }
  }, [live])

  const counts = useMemo(
    () => ({
      alerts: alerts.length,
      traffic: traffic.length,
      construction: construction.length,
    }),
    [alerts.length, traffic.length, construction.length],
  )

  const alertsBody = useMemo(() => {
    if (loading) return <div className="text-sm text-slate-400">Loading…</div>
    if (alerts.length === 0) return <div className="text-sm text-slate-400">No alerts yet.</div>
    return (
      <ul className="divide-y divide-slate-800">
        {alerts.slice(0, 20).map((a) => (
          <li key={a.id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium">
                  <span className={alertTypeClass(a.type)}>{a.type.toUpperCase()}</span>{' '}
                  <span className="text-slate-200">{a.message}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">{new Date(a.created_at).toLocaleString()}</div>
              </div>
              <div className="shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200">
                Sev {a.severity}
              </div>
            </div>
          </li>
        ))}
      </ul>
    )
  }, [alerts, loading])

  return (
    <div className="min-h-full">
      <header className="border-b border-slate-800 bg-slate-950/50 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <div>
            <div className="text-sm text-slate-400">MetroGuardian</div>
            <div className="text-lg font-semibold tracking-tight">Alert Dashboard</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void refresh()}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800"
            >
              Refresh
            </button>
            <button
              onClick={() => void ingestTraffic().then(refresh)}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800"
            >
              Ingest traffic
            </button>
            <button
              onClick={() => void ingestConstruction().then(refresh)}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800"
            >
              Ingest construction
            </button>
            <label className="ml-2 flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={live}
                onChange={(e) => setLive(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-900"
              />
              <span>Live</span>
            </label>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {error ? (
          <div className="mb-4 rounded-md border border-rose-900/50 bg-rose-950/40 p-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <Stat title="Alerts" value={counts.alerts} />
          <Stat title="Traffic events" value={counts.traffic} />
          <Stat title="Construction events" value={counts.construction} />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Panel title="Latest alerts">
            {alertsBody}
          </Panel>

          <div className="grid grid-cols-1 gap-6">
            <Panel title="Traffic events">
              {loading ? (
                <div className="text-sm text-slate-400">Loading…</div>
              ) : (
                <ul className="divide-y divide-slate-800">
                  {traffic.slice(0, 10).map((e) => (
                    <li key={e.id} className="py-2 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-slate-200">{e.road_name}</div>
                          <div className="text-xs text-slate-500">{new Date(e.observed_at).toLocaleTimeString()}</div>
                        </div>
                        <div className="shrink-0 font-mono text-slate-200">{e.speed_kph.toFixed(1)} kph</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Construction events">
              {loading ? (
                <div className="text-sm text-slate-400">Loading…</div>
              ) : (
                <ul className="divide-y divide-slate-800">
                  {construction.slice(0, 10).map((e) => (
                    <li key={e.id} className="py-2 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-slate-200">{e.road_name}</div>
                          <div className="text-xs text-slate-500">{e.description}</div>
                        </div>
                        <div className="shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200">
                          {e.keyword ?? '—'}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App

function Panel(props: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/40">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-200">{props.title}</h2>
      </div>
      <div className="px-4 py-3">{props.children}</div>
    </section>
  )
}

function Stat(props: Readonly<{ title: string; value: number }>) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 px-4 py-4">
      <div className="text-xs text-slate-400">{props.title}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-100">{props.value}</div>
    </div>
  )
}
