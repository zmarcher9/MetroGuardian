import { useEffect, useMemo, useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { Construction, Database, Gauge, LogIn, LogOut, Radio, RadioOff, RefreshCw, UserPlus } from 'lucide-react'
import {
  alertsEventSource,
  ingestConstruction,
  ingestTraffic,
  listAlerts,
  listConstructionEvents,
  listTrafficEvents,
  type ConstructionEvent,
  type PipelineAlert,
  type RouteOption,
  type TrafficEvent,
} from './lib/api'
import { AuthProvider } from './lib/AuthContext'
import { useAuth } from './lib/useAuth'
import ProtectedRoute from './components/ProtectedRoute'
import MapView from './components/MapView'
import RouteCheckPanel from './components/RouteCheckPanel'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import SavedRoutesPage from './pages/SavedRoutesPage'
import { Button } from './components/ui/Button'
import { buttonClasses } from './components/ui/buttonClasses'
import { Card, CardHeader, CardTitle } from './components/ui/Card'
import { IconBadge } from './components/ui/IconBadge'
import { Led, type LedStatus } from './components/ui/Led'

function AlertTypeBadge({ type }: Readonly<{ type: string }>) {
  if (type === 'traffic') {
    return (
      <IconBadge icon={Gauge} tone="warning">
        Traffic
      </IconBadge>
    )
  }
  if (type === 'construction') {
    return (
      <IconBadge icon={Construction} tone="info">
        Construction
      </IconBadge>
    )
  }
  return <IconBadge tone="neutral">{type}</IconBadge>
}

function App() {
  return (
    <AuthProvider>
      <div className="min-h-full">
        <NavHeader />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route
            path="/saved-routes"
            element={
              <ProtectedRoute>
                <SavedRoutesPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </div>
    </AuthProvider>
  )
}

function NavHeader() {
  const { user, logout } = useAuth()

  return (
    <header className="border-b border-border-light bg-[var(--foreground-translucent)] backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4">
        <div className="flex flex-wrap items-center gap-4 sm:gap-6">
          <div>
            <div className="text-xs uppercase tracking-widest text-text-muted">MetroGuardian</div>
            <div className="text-emboss text-lg font-bold tracking-tight text-text">Alert Dashboard</div>
          </div>
          <nav className="flex items-center gap-4 text-sm font-medium text-text-muted">
            <Link to="/" className="transition-colors hover:text-text">
              Dashboard
            </Link>
            {user ? (
              <Link to="/saved-routes" className="transition-colors hover:text-text">
                Saved routes
              </Link>
            ) : null}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <span className="hidden text-sm text-text-muted sm:inline">{user.email}</span>
              <Button variant="secondary" size="sm" onClick={() => void logout()}>
                <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link to="/login" className={buttonClasses('secondary', 'sm')}>
                <LogIn className="h-3.5 w-3.5" aria-hidden="true" />
                Log in
              </Link>
              <Link to="/signup" className={buttonClasses('primary', 'sm')}>
                <UserPlus className="h-3.5 w-3.5" aria-hidden="true" />
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}

function Dashboard() {
  const [alerts, setAlerts] = useState<PipelineAlert[]>([])
  const [traffic, setTraffic] = useState<TrafficEvent[]>([])
  const [construction, setConstruction] = useState<ConstructionEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(true)
  const [connectionStatus, setConnectionStatus] = useState<LedStatus>('offline')
  const [routeOptions, setRouteOptions] = useState<RouteOption[]>([])
  const [recommendedRouteIndex, setRecommendedRouteIndex] = useState(0)

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
    if (!live) {
      setConnectionStatus('offline')
      return
    }
    setConnectionStatus('connecting')
    const es = alertsEventSource()
    const onAlert = (ev: MessageEvent) => {
      try {
        const a = JSON.parse(ev.data) as PipelineAlert
        setAlerts((prev) => [a, ...prev].slice(0, 50))
      } catch {
        // ignore
      }
    }
    const onOpen = () => setConnectionStatus('online')
    const onError = () => setConnectionStatus('error')
    es.addEventListener('alert', onAlert as EventListener)
    es.addEventListener('open', onOpen)
    es.addEventListener('error', onError)
    return () => {
      es.removeEventListener('alert', onAlert as EventListener)
      es.removeEventListener('open', onOpen)
      es.removeEventListener('error', onError)
      es.close()
      setConnectionStatus('offline')
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
    if (loading) return <div className="text-sm text-text-muted">Loading…</div>
    if (alerts.length === 0) return <div className="text-sm text-text-muted">No alerts yet.</div>
    return (
      <ul className="divide-y divide-border-light">
        {alerts.slice(0, 20).map((a) => (
          <li key={a.id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mb-1">
                  <AlertTypeBadge type={a.type} />
                </div>
                <div className="text-sm text-text">{a.message}</div>
                <div className="mt-1 text-xs text-text-muted">{new Date(a.created_at).toLocaleString()}</div>
              </div>
              <IconBadge tone="neutral" className="shrink-0">
                Sev {a.severity}
              </IconBadge>
            </div>
          </li>
        ))}
      </ul>
    )
  }, [alerts, loading])

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => void refresh()}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Refresh
        </Button>
        <Button variant="secondary" size="sm" onClick={() => void ingestTraffic().then(refresh)}>
          <Database className="h-3.5 w-3.5" aria-hidden="true" />
          Ingest traffic
        </Button>
        <Button variant="secondary" size="sm" onClick={() => void ingestConstruction().then(refresh)}>
          <Construction className="h-3.5 w-3.5" aria-hidden="true" />
          Ingest construction
        </Button>
        <Button
          variant={live ? 'primary' : 'secondary'}
          size="sm"
          onClick={() => setLive((v) => !v)}
          aria-pressed={live}
        >
          {live ? (
            <Radio className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <RadioOff className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Live
        </Button>
        <Led status={connectionStatus} />
      </div>

      {error ? (
        <div className="mb-4 rounded-lg border border-accent bg-[var(--accent-tint)] p-3 text-sm text-text">{error}</div>
      ) : null}

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Stat title="Alerts" value={counts.alerts} />
        <Stat title="Traffic events" value={counts.traffic} />
        <Stat title="Construction events" value={counts.construction} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Latest alerts</CardTitle>
          </CardHeader>
          {alertsBody}
        </Card>

        <div className="grid grid-cols-1 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Traffic events</CardTitle>
            </CardHeader>
            {loading ? (
              <div className="text-sm text-text-muted">Loading…</div>
            ) : (
              <ul className="divide-y divide-border-light">
                {traffic.slice(0, 10).map((e) => (
                  <li key={e.id} className="py-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-text">{e.road_name}</div>
                        <div className="text-xs text-text-muted">{new Date(e.observed_at).toLocaleTimeString()}</div>
                      </div>
                      <div className="shrink-0 font-mono text-text">{e.speed_kph.toFixed(1)} kph</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Construction events</CardTitle>
            </CardHeader>
            {loading ? (
              <div className="text-sm text-text-muted">Loading…</div>
            ) : (
              <ul className="divide-y divide-border-light">
                {construction.slice(0, 10).map((e) => (
                  <li key={e.id} className="py-2 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-text">{e.road_name}</div>
                        <div className="text-xs text-text-muted">{e.description}</div>
                      </div>
                      <IconBadge tone="neutral" className="shrink-0">
                        {e.keyword ?? '—'}
                      </IconBadge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <Card floating>
          <CardHeader>
            <CardTitle>Live map & route check</CardTitle>
          </CardHeader>
          <div className="space-y-4">
            <RouteCheckPanel
              onResult={(routes, recommendedIndex) => {
                setRouteOptions(routes)
                setRecommendedRouteIndex(recommendedIndex)
              }}
            />
            <MapView
              trafficEvents={traffic}
              constructionEvents={construction}
              routes={routeOptions}
              recommendedIndex={recommendedRouteIndex}
            />
          </div>
        </Card>
      </div>
    </main>
  )
}

export default App

function Stat(props: Readonly<{ title: string; value: number }>) {
  return (
    <Card className="px-4 py-4" decorated={false} padded={false}>
      <div className="text-xs uppercase tracking-wide text-text-muted">{props.title}</div>
      <div className="text-emboss mt-1 font-mono text-2xl font-semibold text-text">{props.value}</div>
    </Card>
  )
}
