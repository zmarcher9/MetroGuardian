# MetroGuardian

MetroGuardian is a full-stack web application that helps urban drivers avoid unexpected delays due to traffic incidents and road construction. It detects probable incidents from traffic speed data, ingests construction/closure information, and provides an interactive map plus route impact analysis and alternate routing via OSRM.

---

## Features

- Traffic incident detection via speed-drop threshold detection (>40% drop within a 5-minute window) — currently runs against **simulated** data for 3 fixed road segments, not a live traffic feed
- Construction and road closure ingestion (built-in sample feed, or a JSON file via `CONSTRUCTION_FEED_PATH`)
- Live alert feed (Server-Sent Events) and dashboard showing recent alerts, traffic events, and construction events
- Interactive Leaflet map showing traffic/construction markers
- Route impact checking: given an origin/destination, fetches driving route(s) from OSRM and flags any recent alerts within ~250m of the route, scored by severity
- Alternate route suggestions via OSRM, ranked by lowest impact score

Not yet built (see Roadmap): user-defined saved routes, delay-minutes estimates, one-click deep links to Google/Apple Maps, authentication-gated features.

---

## Tech Stack

**Frontend**
- React + Vite
- TailwindCSS
- Leaflet / react-leaflet for map rendering

**Backend**
- Python + FastAPI
- HTTPX for external API calls (OSRM)
- Pydantic for request/response models
- SQLAlchemy (async) + asyncpg

**Infrastructure**
- PostgreSQL (Supabase)
- Backend hosting: Railway
- Frontend hosting: Cloudflare Pages
- Domain: Porkbun (registrar) + Cloudflare (DNS)
- Routing: OSRM API (defaults to the public demo instance)

---

## Local Development

### Prerequisites

- Node.js (LTS)
- Python 3.10+
- PostgreSQL database (or Supabase project)
- OSRM endpoint (public demo or self-hosted)

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
# set environment variables in .env (see below)
uvicorn app.main:app --reload
```

Backend should now be running at http://localhost:8000. API docs at http://localhost:8000/docs.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend should now be running at http://localhost:5173.

### Environment Variables

Backend `.env` example:

```env
DATABASE_URL=postgresql://user:password@host:5432/metroguardian
OSRM_BASE_URL=https://router.project-osrm.org
# Optional tuning for route impact checking (defaults shown)
ROUTE_IMPACT_RADIUS_METERS=250
ROUTE_IMPACT_LOOKBACK_MINUTES=45
```

Frontend `.env` example:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

### Project Structure

```text
metroguardian/
  backend/
    app/
      main.py
      api/v1/
        routes_health.py
        routes_auth.py
        routes_pipeline.py      # ingestion triggers, alert/event listing
        routes_realtime.py      # SSE alert stream
        routes_route.py         # route check (OSRM + impact analysis)
      core/
        config.py
        security.py
        deps.py
        middleware.py
      db/
        session.py
      models/
        user.py, saved_route.py, incident.py, closure.py, alert.py,
        traffic_event.py, construction_event.py, pipeline_alert.py
      schemas/
        auth.py, pipeline.py, routing.py
      services/
        ingestion.py            # traffic/construction ingestion + alerting
        routing_service.py      # OSRM client + route impact scoring
  frontend/
    src/
      components/
        MapView.tsx             # Leaflet map: markers + route polylines
        RouteCheckPanel.tsx     # origin/destination inputs, presets, results
      lib/
        api.ts
      App.tsx
```

## Roadmap

- [x] v1: Incident detection + construction ingestion + basic map
- [x] v1.1: Route checking and alternate route suggestions
- [ ] v1.2: User saved routes, alert history, Google/Apple Maps deep links
- [ ] v2: Authentication-gated features (cookie-based auth, refresh-token rotation, and an admin
      role are implemented on the backend; no frontend UI yet) + notifications + two-factor
      authentication (2FA) - not started, planned for sometime after the frontend auth UI ships
- [ ] v2+: Analytics dashboard, trend heatmaps, and a real (non-simulated) traffic data source
- [ ] Hardening (no urgency): the login/signup rate limiter (`backend/app/core/rate_limit.py`) is
      an in-memory, single-instance, fixed-window IP+email limiter - it stops single-IP brute
      force but not a distributed/IP-rotating attacker targeting one account. Potential future
      upgrade: an additional per-email-only limiter (catches the distributed case) and/or
      switching to a sliding-window or token-bucket algorithm (avoids the fixed-window boundary-
      burst edge case, where a client can get ~2x the intended attempts right at a window
      rollover)

---

## License

MIT — see [LICENSE](LICENSE).
