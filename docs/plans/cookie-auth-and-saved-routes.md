# Cookie-based auth + refresh tokens + saved routes

> **Status (2026-08-13):** Phase A shipped in [e08d1cb](../../) ("Add cookie-based auth with refresh tokens, admin role, and rate limiting"). The actual implementation ended up broader than section 1 below describes: it's **dual-transport** — web clients use the `mg_at`/`mg_rt`/`mg_csrf` cookies as planned, but mobile/native clients authenticate via `Authorization: Bearer` + `X-Client-Type: mobile` and are exempt from CSRF (see `backend/app/core/middleware.py`'s `CSRFMiddleware`). It also added an admin role, auth-specific rate limiting, and background cleanup jobs — see [MOBILE.md](../../MOBILE.md) and the README roadmap. Section 1-3 below are kept as-written for historical context on the original design rationale; treat the code as authoritative over the prose where they diverge.
>
> **Phase B (saved routes) was reviewed by a 3-agent council on 2026-08-13** (security/correctness, architectural consistency, test-plan completeness) before implementation started. Sections 4-6 below already incorporate that review's amendments; a summary of what changed and why is inline at each amendment point.

## Context

MetroGuardian's auth today is 100% bearer-token: `POST /auth/signup`/`/auth/login` return a JWT in the response body, the frontend would have had to store it in `localStorage` and send `Authorization: Bearer <token>`. No frontend auth UI has been built yet, so this is the right moment to change the transport before any client code depends on it.

Two things are driving this change:
1. **Security**: storing the token in `localStorage` (or any JS-readable place) exposes it to any XSS bug in the app or a dependency. An httpOnly cookie is invisible to JavaScript entirely.
2. **Session longevity without re-login**: the current JWT has no refresh mechanism — once it expires (30 min), the user is just logged out. A refresh-token flow lets short-lived access tokens roll over silently, without the security cost of also making the *long-lived* credential JS-readable or non-revocable.

The user has explicitly chosen to build the refresh-token machinery now rather than defer it, accepting the added complexity for the security/UX benefit, and wants the backend fully built and tested before any frontend work starts (the app isn't live yet, so there's no rush pressure). This also folds in the previously-scoped **v1.2 "saved routes"** feature, which depends on working auth to be meaningful (routes must be owned by a user) — its `SavedRoute` model existed once, was deleted as unreferenced dead code, and is being reintroduced now that it has a real purpose.

Intended outcome: a backend that a completely frontend-less test suite (and a manual curl/httpx flow) can prove end-to-end — signup, login, silent refresh, refresh-token rotation, theft/reuse detection, logout, CSRF protection, and full saved-routes CRUD — before a single line of frontend auth code is written.

---

## 1. Token / cookie architecture

Three cookies:

| Cookie | Contents | HttpOnly | Secure | SameSite | Path | Max-Age |
|---|---|---|---|---|---|---|
| `mg_at` | access-token JWT | Yes | Yes | Lax | `/` | 15 min |
| `mg_rt` | opaque refresh token | Yes | Yes | Lax | `/api/v1/auth` | 30 days |
| `mg_csrf` | CSRF double-submit value | No | Yes | Lax | `/` | 30 days |

- **Access token stays a JWT**, carried in `mg_at` instead of the response body / `Authorization` header. Reuses `create_access_token`/`decode_access_token` in [backend/app/core/security.py](../../backend/app/core/security.py) almost unchanged — only the transport moves. Default TTL drops from 30 → **15 min** in `Settings.jwt_access_token_expire_minutes` (a refresh flow now exists, so the exposure window can shrink).
- **Refresh token is DB-backed and opaque**, not a JWT — this is the decisive choice given "revocation must actually work": a stateless JWT refresh token can't be revoked before its own expiry without a server-side blocklist anyway, which is just this table with extra steps.
  - Raw token: `secrets.token_urlsafe(32)`, sent to the client only via the `mg_rt` cookie.
  - DB stores only `sha256(raw_token)` — no HMAC secret needed, the entropy alone makes brute force infeasible, and it keeps refresh-token hashing decoupled from `jwt_secret_key` rotation.
  - Every refresh token belongs to a `family_id` (new UUID per login/signup; rotation keeps the same family).
- **Rotation-on-use**: `POST /auth/refresh` looks up the presented token by hash. If valid: mark it `revoked_at = now()`, insert a new row (same `family_id`, new hash/expiry, `replaced_by_id` pointing at it), issue a new access JWT, set both cookies.
- **Reuse detection**: if the presented token's row is found but already `revoked_at IS NOT NULL`, that's a replay signal — revoke the **entire family** (`UPDATE ... WHERE family_id = :fid AND revoked_at IS NULL`), clear cookies, `401`. (Family-scoped, not "all devices for this user" — a family is one login lineage; escalating further is a clean future addition if ever wanted, not needed now.)
- **No absolute session cap** in this pass — the 30-day sliding window + reuse detection already satisfies "revocation actually works" without extra complexity.
- **`get_current_user`** ([backend/app/core/deps.py](../../backend/app/core/deps.py)) drops `HTTPBearer()` entirely. New version takes `request: Request`, reads `request.cookies.get(settings.access_token_cookie_name)`, same decode → UUID → `User` lookup as today, `401` on any failure. It stays a pure/simple dependency — it does **not** attempt an inline refresh; that's the frontend interceptor's job (section 8).
- **Drop `Authorization: Bearer` support entirely.** No non-browser client exists today (confirmed: only the frontend calls this API). One auth transport is simpler to build, test, and reason about than two; a machine client later is a small, separate addition (e.g. an API key scheme), not a reason to keep bearer-in-body now.

  > *(As shipped, this last point changed: bearer support was kept and extended for mobile/native clients rather than dropped. See the status note at the top of this doc.)*

## 2. CSRF mitigation

Moving to cookies reintroduces CSRF risk that bearer-in-header never had (a cross-site page can make the browser attach cookies automatically; it never could attach a custom `Authorization` header).

**Double-submit cookie pattern**: a new `CSRFMiddleware` in [backend/app/core/middleware.py](../../backend/app/core/middleware.py) (same `BaseHTTPMiddleware` style as the existing `SecurityHeadersMiddleware`/`SimpleRateLimitMiddleware` there), wired into [backend/app/main.py](../../backend/app/main.py)'s `create_app()` right before `CORSMiddleware` (which is deliberately added last already — see the `# Step 7: CORS (add last)` comment):
1. If no `mg_csrf` cookie is present on the request, mint one (`secrets.token_urlsafe(32)`) and set it on the response — regardless of method/outcome, so even an anonymous `GET /auth/me` mints it before any form is ever submitted.
2. For any non-`GET/HEAD/OPTIONS/TRACE` request under the API prefix, require an `X-CSRF-Token` header matching the `mg_csrf` cookie via `hmac.compare_digest` — else `403`.

Applies uniformly to **every** mutating route, including `/auth/signup` and `/auth/login` (protects against login-CSRF — tricking a victim into authenticating as an attacker's account) — one uniform rule is simpler than a per-route exception list and costs nothing extra since the cookie is already minted pre-login.

## 3. CORS / cookie config for dev

`backend/.env` currently sets no `CORS_*` vars, so the app runs on `cors_allow_origins="*"` + `cors_allow_credentials=True` — a combination browsers reject outright for credentialed (cookie) requests, and one the existing production guard in `get_settings()` ([backend/app/core/config.py](../../backend/app/core/config.py)) already refuses to boot with. Add to `backend/.env`:

```
CORS_ALLOW_ORIGINS=http://localhost:5173
CORS_ALLOW_CREDENTIALS=true
```

In practice `frontend/vite.config.ts`'s dev proxy (`/api → 127.0.0.1:8000`) makes the browser see everything as same-origin already, so this mostly matters for hitting `/docs` directly and for keeping dev config honest with what production will require.

**`SameSite` is made configurable, not hardcoded**: add `cookie_samesite: str = Field(default="lax")` to `Settings`. Default `Lax` assumes frontend and backend end up same-site in production (e.g. behind one reverse-proxied domain, mirroring the dev proxy). If frontend (Vercel) and backend (Railway/Render) ever end up on genuinely separate domains with no unifying proxy, `Lax` cookies won't be sent on cross-site fetches — the fix at that point is flipping this one setting to `none` (which requires `Secure=true`, already the default). Not blocking this plan on a deployment-topology decision that doesn't need to be made yet.

Extend the existing production guard in `get_settings()` with one more clause, consistent with the existing weak-JWT-secret and wildcard-CORS checks: refuse to boot if `app_env == "production"` and `cookie_secure` is `False`.

## 4. New backend models

Both are picked up automatically by the existing `Base.metadata.create_all()` in `main.py`'s `test_database_connectivity()` — this project has no Alembic, every model already works this way.

**[backend/app/models/refresh_token.py](../../backend/app/models/refresh_token.py)** (new):
- `id` (UUID pk), `user_id` (FK → `users.id`, `ondelete=CASCADE`, indexed), `family_id` (UUID, indexed), `token_hash` (String(64), unique, indexed — sha256 hex), `created_at`, `expires_at`, `revoked_at` (nullable), `replaced_by_id` (nullable FK → `refresh_tokens.id`), `user_agent`/`ip_address` (nullable, informational).
- No `relationship()` to `User` — matches `User`'s current style (zero relationships already, since the earlier dead-schema cleanup removed them). FK + cascade is enough.

**[backend/app/models/saved_route.py](../../backend/app/models/saved_route.py)** (new — reusing the exact shape from the deleted version at `git show dddb2e2^:backend/app/models/saved_route.py`, minus its two `relationship()` calls which pointed at the also-deleted `Alert` model and a `User.saved_routes` that no longer exists — confirmed this matches every current model's convention, none of which have any `relationship()`):
- `id`, `user_id` (FK cascade, indexed), `name` (String(255)), `origin_lat`/`origin_lng`/`dest_lat`/`dest_lng` (Float), `waypoints` (JSONB, nullable), `created_at`, `updated_at`.

Register both in [backend/app/models/__init__.py](../../backend/app/models/__init__.py)'s imports/`__all__`, same as `TrafficEvent`/`ConstructionEvent`/`PipelineAlert` already are.

**New `Settings` fields** (`config.py`): `access_token_cookie_name="mg_at"`, `refresh_token_cookie_name="mg_rt"`, `csrf_cookie_name="mg_csrf"`, `csrf_header_name="X-CSRF-Token"`, `refresh_token_expire_days=30`, `cookie_secure=True`, `cookie_samesite="lax"`; `jwt_access_token_expire_minutes` default `30 → 15`.

**Added by council review:** `saved_routes_max_per_user: int = Field(default=50, description="Max saved routes a single user may hold")`. *Why:* the general IP rate limiter (`SimpleRateLimitMiddleware`) is per-IP, not per-user, and `get_client_ip()` trusts `X-Forwarded-For` unconditionally — an authenticated user (or attacker with a spoofed header) could otherwise create unbounded `saved_routes` rows. A per-user cap enforced in the create endpoint (section 5) closes this independent of the IP limiter. 50 is a generous default for a "usual routes" feature; not meant to be a hard product decision, just a backstop.

No new pip dependency — `secrets`/`hashlib`/`hmac` are stdlib; [backend/requirements.txt](../../backend/requirements.txt) needs no changes.

## 5. New / changed backend endpoints

Rewritten [backend/app/api/v1/routes_auth.py](../../backend/app/api/v1/routes_auth.py) + new `backend/app/api/v1/routes_saved_routes.py` (local `DbDep`/`CurrentUserDep` `Annotated` aliases and per-endpoint `Depends(...)`, matching how `routes_pipeline.py` and `routes_route.py` already do it — no shared alias module, no router-level `dependencies=[...]`):

| Endpoint | Auth | CSRF | Notes |
|---|---|---|---|
| `POST /auth/signup` | no | yes | sets `mg_at`+`mg_rt` (new family), returns `UserResponse` |
| `POST /auth/login` | no | yes | same, new family each login |
| `GET /auth/me` | cookie | — | unchanged behavior, new transport |
| `POST /auth/refresh` | `mg_rt` cookie | yes | rotates both cookies; `401` + clears cookies on missing/expired/reused |
| `POST /auth/logout` | best-effort | yes | revokes current refresh row if present, always clears all 3 cookies |
| `POST /saved-routes` | yes | yes | `201`; rejects with `422` if the user already has `saved_routes_max_per_user` rows |
| `GET /saved-routes` | yes | — | own rows only, newest-first (`order_by(desc(created_at))` — matches the convention every other list endpoint in this codebase already uses), `?limit=` (default 100, max 500 — same `Annotated[int, Query(ge=1, le=500)]` pattern already used in [backend/app/api/v1/routes_pipeline.py](../../backend/app/api/v1/routes_pipeline.py)) |
| `GET /saved-routes/{id}` | yes | — | `404` (not `403`) if missing or owned by another user |
| `DELETE /saved-routes/{id}` | yes | yes | same ownership scoping, `204` |

Ownership scoping is a single `WHERE id = :id AND user_id = :current_user_id` — another user's row is indistinguishable from a nonexistent one, which is exactly why it's `404`.

`TokenResponse` in [backend/app/schemas/auth.py](../../backend/app/schemas/auth.py) is removed — no endpoint ever returns a token in the body again. New `backend/app/schemas/saved_routes.py` holds:

```python
class SavedRouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    origin: LatLng
    dest: LatLng
    waypoints: list[LatLng] | None = Field(default=None, max_length=50)

class SavedRouteResponse(BaseModel):
    id: UUID
    name: str
    origin: LatLng
    dest: LatLng
    waypoints: list[LatLng] | None
    created_at: datetime
    updated_at: datetime
```

**Amended by council review — this is a real design decision, not "just reuse `LatLng`":** unlike every other current response schema (which mirrors its model's flat columns 1:1 — `TrafficEventResponse`, `PipelineAlertResponse`, etc.), `SavedRoute` has flat `origin_lat`/`origin_lng`/`dest_lat`/`dest_lng` columns but a nested `LatLng` in the schema. The endpoint is responsible for the conversion both ways:
- On create: `SavedRoute(origin_lat=body.origin.lat, origin_lng=body.origin.lng, dest_lat=body.dest.lat, dest_lng=body.dest.lng, waypoints=[w.model_dump() for w in body.waypoints] if body.waypoints else None, ...)`.
- On read: `SavedRouteResponse(origin=LatLng(lat=row.origin_lat, lng=row.origin_lng), dest=LatLng(lat=row.dest_lat, lng=row.dest_lng), waypoints=[LatLng(**w) for w in row.waypoints] if row.waypoints else None, ...)` (or a small `@classmethod from_model()` helper on the response schema to keep this out of the route handler body).

This also fixes the original plan's unvalidated `waypoints: JSONB` — typing it as `list[LatLng]` with `max_length=50` gives it the same `ge=-90/le=90`/`ge=-180/le=180` bounds as origin/dest and caps payload size, instead of accepting arbitrary JSON.

## 6. Backend test plan

Existing fixtures in [backend/tests/conftest.py](../../backend/tests/conftest.py) need no new infra — httpx's `AsyncClient` (used by the `client` fixture) already persists cookies across requests within one test, and a `csrf_headers(client)` helper already exists there (built during Phase A):

```python
def csrf_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies.get(settings.csrf_cookie_name) or ""}
```

**[backend/tests/test_auth_api.py](../../backend/tests/test_auth_api.py)** — rewritten (current version asserts a body token + sends `Authorization: Bearer`, both gone):
- signup/login set cookies, body is `UserResponse`.
- `/auth/me` works via the cookie jar alone; `401` without prior login.
- refresh rotates both cookie values (capture before/after, assert changed).
- reuse detection: replay the pre-rotation `mg_rt` value after a rotation → `401`, and confirm the family is fully dead (the rotated-to token also now fails).
- expired refresh token: mutate a `RefreshToken` row's `expires_at` into the past via `db_session` (same transaction as `client`), confirm `401`.
- missing refresh cookie → `401`.
- logout clears cookies, kills the refresh token, subsequent `/auth/me` and `/auth/refresh` both `401`.
- CSRF: mutating auth routes reject a missing/mismatched `X-CSRF-Token` → `403`; succeed with `csrf_headers(client)`.
- one end-to-end smoke test chaining signup → me → refresh → reuse-rejected → logout → me-401 — this is also the "backend is done" proof described below.

**`backend/tests/test_saved_routes_api.py`** (new):
- unauthenticated CRUD → `401`.
- create + list returns the caller's own route.
- **[added by council review] `GET /saved-routes/{id}` happy path**: owner fetches their own route by id → `200`, field-for-field match. *Why:* the original plan only tested the cross-user `404` case on `{id}`, never the basic success path — the single biggest coverage hole a reviewer found.
- **[added] list ordering**: create 2+ routes for one user, assert `GET /saved-routes` returns them newest-first. *Why:* every other list endpoint in this codebase (`routes_pipeline.py`, `routes_realtime.py`) orders newest-first; nothing pinned this for saved routes.
- **[added] multi-row listing correctness**: user A creates 2 routes, user B creates 2 routes; assert A's list is exactly A's 2 by id set. *Why:* the original plan only ever created one route per user in tests, so a query missing its `WHERE user_id = ...` clause could still pass.
- **[added] `limit` boundaries**: create more than `limit` rows, assert `GET ?limit=N` returns exactly `N`; assert `limit=0` and `limit=501` are rejected (`422`).
- **[added] `waypoints` round-trip**: create with a waypoints list, retrieve, assert shape matches; separately assert omitting it yields `null`.
- **[added] per-user cap**: create `saved_routes_max_per_user` routes, assert the next `POST` is rejected (`422`).
- cross-user isolation: log in as user A, create a route, log in as user B on the *same* client (overwrites the cookie jar), confirm `GET`/`DELETE` on user A's route id → `404`.
- **[added] double-delete idempotency**: delete a route, delete the same id again → `404`.
- **[added] non-UUID path parameter**: `GET /saved-routes/not-a-uuid` → `422` (FastAPI's path-type validation, pinned explicitly so it's a documented contract rather than incidental behavior — distinct from the `404` used for "valid id, wrong owner").
- delete removes the row from a subsequent list.
- CSRF missing/mismatched on `POST`/`DELETE` → `403`.
- validation: empty `name` → `422`; out-of-range lat/lng → `422` (reuses `LatLng`'s existing `Field(ge=..., le=...)`).

## 7. Execution phases

**Phase A — cookies + refresh tokens** (no saved routes yet): ✅ **Shipped** in [e08d1cb](../../) — see the status note at the top of this doc for how the implementation ended up broader than originally planned (dual cookie+bearer transport, admin role, rate limiting, background cleanup).

1. `config.py` — new `Settings` fields, extended production guard, TTL default change.
2. `models/refresh_token.py` + register in `models/__init__.py`.
3. `security.py` — `generate_refresh_token()` / `hash_refresh_token()`.
4. `core/cookies.py` (new) — `set_auth_cookies()`, `clear_auth_cookies()`, `ensure_csrf_cookie()`, shared by routes + middleware.
5. `middleware.py` — `CSRFMiddleware`; `main.py` — wire it in before `CORSMiddleware`.
6. `deps.py` — cookie-based `get_current_user`.
7. `schemas/auth.py` — drop `TokenResponse`.
8. `routes_auth.py` — rewritten signup/login, new `/auth/refresh`, `/auth/logout`.
9. `backend/.env` — set `CORS_ALLOW_ORIGINS`.
10. `conftest.py` helper + rewritten `test_auth_api.py`.

**Done bar for Phase A**: full `pytest` green, including the lifecycle smoke test — zero frontend involvement. *(Met.)*

**Phase B — saved routes CRUD** (depends only on Phase A; **not yet started** — reviewed by council 2026-08-13, amendments above already folded in):
1. `config.py` — add `saved_routes_max_per_user`.
2. `models/saved_route.py` + register.
3. `schemas/saved_routes.py` — `SavedRouteCreate`/`SavedRouteResponse` with nested `LatLng`, `waypoints: list[LatLng] | None` (`max_length=50`), plus the flatten/unflatten conversion described in section 5.
4. `routes_saved_routes.py`, wired into `main.py` — includes the per-user-cap check on create and `order_by(desc(created_at))` on list.
5. `test_saved_routes_api.py`, including all council-added cases above.

**Done bar for Phase B**: full `pytest` green (Phase A + B together), including cross-user `404` isolation, the own-id happy path, ordering, multi-row listing, limit boundaries, waypoints round-trip, the per-user cap, and double-delete idempotency.

Frontend work does not start until both done-bars are met.

**Phase C — frontend** (design only for now, not started this round):
- Add `react-router-dom` (only mainstream router that fits a handful of static routes with no need for its data-loader features); wrap `main.tsx`'s `<App />` in `<BrowserRouter>`.
- `lib/AuthContext.tsx` + `lib/useAuth.ts` — fetches `GET /auth/me` on mount, exposes `login`/`signup`/`logout`/state. No token to store client-side (it's an httpOnly cookie).
- `lib/api.ts`: `credentials: 'include'` on every fetch; read `mg_csrf` from `document.cookie`, attach `X-CSRF-Token` on non-GET requests; a 401 → single `/auth/refresh` attempt → retry-once interceptor in `http()`, with in-flight-refresh deduplication (so `Promise.all`-style concurrent calls in `App.tsx` don't each trigger their own refresh) and a `_retried` guard so a hard-failed refresh surfaces as a normal error instead of looping.
- New pages: `LoginPage`, `SignupPage`, `SavedRoutesPage`; a `ProtectedRoute` wrapper; routes at `/`, `/login`, `/signup`, `/saved-routes`.
- `RouteCheckPanel.tsx`: a "Save this route" button next to results, visible only when authenticated.
- Test updates: wrap `App.test.tsx` renders in `MemoryRouter` + a mocked auth provider, extend `api.test.ts` for credentials/CSRF/retry behavior, new tests for auth pages and the saved-routes page — following the existing `vi.mock('../src/lib/api', ...)` pattern already used throughout `frontend/tests/`.

## Verification

- Backend: `cd backend && venv/Scripts/python.exe -m pytest -v` (real Supabase DB, rollback-per-test as already established) — Phase A and B done-bars above.
- Manual smoke check with no frontend: `curl -c cookies.txt -b cookies.txt` (or an httpx script) through signup → refresh → logout, inspecting `Set-Cookie` headers directly, as an independent sanity check beyond the automated tests.
- `pyright` clean (`venv/Scripts/pyright-python.exe`), matching the standard already held everywhere else in this backend.
- Frontend (Phase C, later): `npm test` (Vitest) + `npm run build` + a manual browser check that login persists across a refresh and that an expired-then-refreshed session keeps working without a visible logout.

## Known limitation carried over from Phase A (not fixed here)

`get_client_ip()` ([backend/app/core/rate_limit.py](../../backend/app/core/rate_limit.py)) trusts `X-Forwarded-For` unconditionally with no proxy-trust check, so `SimpleRateLimitMiddleware`'s IP-based limits (including the auth-specific login/signup limiters) are spoofable by any client that sets the header itself when not actually behind a trusted reverse proxy. This was flagged during the Phase B council review but is out of scope for saved routes specifically — worth a standalone fix (validate `X-Forwarded-For` only when a trusted proxy is configured, else use the direct connecting IP) before this app is exposed publicly behind a real proxy.
