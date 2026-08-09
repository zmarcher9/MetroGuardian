import { CircleMarker, MapContainer, Polyline, Popup, TileLayer } from 'react-leaflet'
import L from 'leaflet'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import 'leaflet/dist/leaflet.css'
import type { ConstructionEvent, RouteOption, TrafficEvent } from '../lib/api'

// Vite doesn't resolve Leaflet's default marker icon URLs the way webpack does;
// point them at the bundled asset URLs instead.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const DEFAULT_CENTER: [number, number] = [47.618, -122.325]

function speedColor(speedKph: number): string {
  if (speedKph >= 50) return '#34d399' // emerald-400
  if (speedKph >= 25) return '#fbbf24' // amber-400
  return '#f87171' // red-400
}

const ROUTE_COLORS = ['#38bdf8', '#a78bfa', '#f472b6', '#fb923c']

export default function MapView(props: Readonly<{
  trafficEvents: TrafficEvent[]
  constructionEvents: ConstructionEvent[]
  routes?: RouteOption[]
  recommendedIndex?: number
}>) {
  const { trafficEvents, constructionEvents, routes = [], recommendedIndex = 0 } = props

  return (
    <div className="h-[420px] w-full overflow-hidden rounded-lg border border-slate-800">
      <MapContainer center={DEFAULT_CENTER} zoom={13} className="h-full w-full" scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {trafficEvents.map((e) => (
          <CircleMarker
            key={e.id}
            center={[e.lat, e.lng]}
            radius={7}
            pathOptions={{ color: speedColor(e.speed_kph), fillColor: speedColor(e.speed_kph), fillOpacity: 0.85 }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-semibold">{e.road_name}</div>
                <div>{e.speed_kph.toFixed(1)} kph</div>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {constructionEvents.map((e) => (
          <CircleMarker
            key={e.id}
            center={[e.lat, e.lng]}
            radius={7}
            pathOptions={{ color: '#38bdf8', fillColor: '#38bdf8', fillOpacity: 0.85 }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-semibold">{e.road_name}</div>
                <div>{e.description}</div>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {routes.map((route, i) => (
          <Polyline
            key={i}
            positions={route.geometry.map((p) => [p.lat, p.lng])}
            pathOptions={{
              color: ROUTE_COLORS[i % ROUTE_COLORS.length],
              weight: i === recommendedIndex ? 5 : 3,
              opacity: i === recommendedIndex ? 0.95 : 0.5,
              dashArray: i === recommendedIndex ? undefined : '6 6',
            }}
          />
        ))}
      </MapContainer>
    </div>
  )
}
