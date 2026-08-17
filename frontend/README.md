# MetroGuardian frontend

React + TypeScript + Vite dashboard for MetroGuardian: live traffic/construction
alerts, a traffic-aware route checker, and cookie-based auth with saved routes.

## Features

- **Live alert dashboard** — traffic anomalies and construction events, updated
  in real time over Server-Sent Events (`/alerts/stream`), with a connection-status
  LED reflecting the actual `EventSource` state (not a static indicator).
- **Route check** — pick a preset or enter coordinates, see ranked route options
  with distance/duration and any active incidents along each one.
- **Auth** — signup/login/logout via httpOnly cookies (`lib/AuthContext.tsx`,
  `lib/useAuth.ts`); no token ever touches `localStorage` or JS-readable storage.
- **Saved routes** — logged-in users can save a checked route and manage their
  list at `/saved-routes`.
- **Admin-only data ingestion** — "Ingest traffic"/"Ingest construction" buttons
  on the dashboard are only shown to admin users (`user.is_admin`); the backend
  independently enforces this regardless of what the frontend shows.

## Stack

- React 19 + TypeScript, Vite, `react-router-dom`
- Tailwind CSS on a custom dark-chassis "Industrial Skeuomorphism" design
  system — CSS custom-property tokens in `src/index.css`, primitives in
  `src/components/ui/` (`Button`, `Card`, `Input`, `Led`, `IconBadge`)
- `react-leaflet` for the live map, `lucide-react` for icons,
  `@fontsource/inter` + `@fontsource/jetbrains-mono` for type
- Vitest + Testing Library for tests

## Getting started

Requires the backend running locally (see `../backend`) — this app proxies
`/api` to `http://127.0.0.1:8000` in dev (`vite.config.ts`).

```bash
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to the local backend
npm run dev
```

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) and build for production |
| `npm test` | Run the Vitest suite once |
| `npm run test:watch` | Run tests in watch mode |
| `npm run lint` | ESLint |
| `npm run preview` | Preview a production build locally |

## Project layout

```
src/
  components/       Dashboard-specific components (MapView, RouteCheckPanel, ProtectedRoute)
  components/ui/    Design-system primitives, reused by every page
  pages/            Route-level pages (Login, Signup, SavedRoutes)
  lib/              api.ts (fetch wrapper + CSRF/refresh interceptor), auth context/hook
tests/              Mirrors src/, plus tests/ui/ for the design-system primitives
```

## Design system

The dark-chassis look is token-driven: every color/shadow lives once as a CSS
custom property in `src/index.css`, and `tailwind.config.js` references those
tokens via `var(--token)` rather than restating values. One gotcha worth
knowing if you touch this: Tailwind's `/NN` opacity-modifier syntax (e.g.
`bg-foreground/60`) silently produces **no CSS at all** when the base color is
one of these `var()`-based tokens (Tailwind can't decompose it into RGB
channels pre-v4). Use one of the pre-mixed tokens instead (`--accent-tint`,
`--foreground-translucent`, `--text-muted-dim`) via `bg-[var(--token)]`, or add
a new one, rather than reaching for a `/NN` suffix on a custom color.
