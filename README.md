# MetroGuardian

MetroGuardian is a full-stack web application that helps urban drivers avoid unexpected delays due to traffic incidents and road construction. It detects probable incidents from traffic speed data, ingests construction/closure information, and provides route impact analysis and alternate routing with one-click navigation via Google and Apple Maps.

---

## Features

- Traffic incident detection using simple moving-average anomaly detection
- Construction and road closure ingestion (feed or mock data)
- Interactive map dashboard with incidents and closures
- User-defined saved routes (e.g., Home ↔ Work)
- Route impact checking (delay estimate, incident/closure list)
- Alternate route suggestions via OSRM
- Deep linking to:
  - Google Maps: `https://www.google.com/maps/dir/?api=1&destination=LAT,LNG`
  - Apple Maps: `maps://?daddr=LAT,LNG`

---

## Tech Stack

**Frontend**
- React + Vite
- TailwindCSS
- Leaflet for map rendering

**Backend**
- Python + FastAPI
- HTTPX for external API calls
- Pydantic for request/response models

**Infrastructure**
- PostgreSQL (Supabase)
- Backend hosting: Railway / Render
- Frontend hosting: Vercel
- Routing: OSRM API

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
# set environment variables in .env
# e.g. DATABASE_URL, OSRM_BASE_URL
uvicorn app.main:app --reload
Backend should now be running at http://localhost:8000.

Frontend Setup
bash
Copy code
cd frontend
npm install
npm run dev
Frontend should now be running at http://localhost:5173.

Environment Variables
Backend .env example:

env
Copy code
DATABASE_URL=postgresql://user:password@host:5432/metroguardian
OSRM_BASE_URL=https://router.project-osrm.org
TRAFFIC_API_KEY=your_traffic_api_key_or_leave_blank_for_mock
Frontend .env example:

env
Copy code
VITE_API_BASE_URL=http://localhost:8000/api
Project Structure (Proposed)
text
Copy code
metroguardian/
  backend/
    app/
      main.py
      api/
        routes_incidents.py
        routes_closures.py
        routes_saved_routes.py
        routes_routing.py
      core/
        config.py
        database.py
      models/
        incident.py
        closure.py
        saved_route.py
        alert.py
      services/
        traffic_ingestion.py
        closure_ingestion.py
        routing_service.py
        alert_service.py
      tests/
  frontend/
    src/
      components/
      pages/
      hooks/
      api/
      styles/
Roadmap
 v1: Incident detection + construction ingestion + basic map

 v1.1: Route checking and alternate route suggestions

 v1.2: User saved routes and alert history

 v2: Authentication + notifications

 v2+: Analytics dashboard and trend heatmaps

markdown
Copy code

