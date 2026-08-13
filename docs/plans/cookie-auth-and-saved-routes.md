# Cookie-based auth + refresh tokens + saved routes

> **Status (2026-08-13):** Phase A shipped in [e08d1cb](../../) ("Add cookie-based auth with refresh tokens, admin role, and rate limiting"). The actual implementation ended up broader than section 1 below describes: it's **dual-transport** — web clients use the `mg_at`/`mg_rt`/`mg_csrf` cookies as planned, but mobile/native clients authenticate via `Authorization: Bearer` + `X-Client-Type: mobile` and are exempt from CSRF (see `backend/app/core/middleware.py`'s `CSRFMiddleware`). It also added an admin role, auth-specific rate limiting, and background cleanup jobs — see [MOBILE.md](../../MOBILE.md) and the README roadmap. Section 1-3 below are kept as-written for historical context on the original design rationale; treat the code as authoritative over the prose where they diverge.
>
> **Phase B (saved routes) was reviewed by a 3-agent council on 2026-08-13** (security/correctness, architectural consistency, test-plan completeness) before implementation started. Sections 4-6 below already incorporate that review's amendments; a summary of what changed and why is inline at each amendment point.
>
> **Phase B is now implemented and done-bar met** (2026-08-13): `backend/app/models/saved_route.py`, `backend/app/schemas/saved_routes.py`, `backend/app/api/v1/routes_saved_routes.py`, the `saved_routes_max_per_user` config field, and `backend/tests/test_saved_routes_api.py` (16 tests). A second council pass reviewed the actual code afterward and found: a TOCTOU race in the per-user cap check (accepted as a documented soft backstop, not fixed with locking), a missing module logger (fixed), an `order_by` tiebreaker gap that could nondeterministically order same-instant rows (fixed), and two test-coverage gaps - a limit-truncation test that only checked count not which rows, and no test proving the per-user cap is per-user rather than global (both fixed). Full suite: 87 passed, pyright clean.
>
> **Phase C (OSRM route-cache TTL) was added 2026-08-13** (section 7) — the frontend phase that used to be "Phase C" is now **Phase D** (unchanged in content, renumbered only).
>
> **Phase C's design was reviewed by a 3-agent committee on 2026-08-13** (cache-type choice, correctness/edge-cases, implementation-plan consistency) before any code was written, and the plan in section 7 was amended in response. Key change: switched from a hand-rolled FIFO `dict` to `cachetools.TTLCache` with LRU eviction (the committee found a real expiry-vs-capacity-cap bug in the original hand-rolled design, and FIFO was a mismatch for the "popular routes get rechecked" access pattern this cache exists for) — this is the one new pip dependency in the whole plan so far. Also fixed: the 4-decimal cache-key precision is now justified on its own terms (OSRM road-snapping) rather than by borrowing `_location_key()`'s unrelated alert-dedup rationale; the "mirrors `_RateBucket`" comparison was corrected to the actual matching pattern (`rate_limit.py`'s module-level dict + `reset_rate_limits()`); the per-instance/multi-deployment cache-scope limitation is now named explicitly; and the done-bar now enumerates every test case instead of just one. `compute_impact()` never being cached (only `get_routes()`'s geometry lookup is) was reviewed and confirmed sound — no change there.
>
> **Phase C is now implemented and done-bar met** (2026-08-13): `cachetools` added to `backend/requirements.txt`; `osrm_cache_ttl_seconds`/`osrm_cache_max_entries` in `config.py`; a module-level `TTLCache` in `backend/app/services/routing_service.py` wrapping `get_routes()` only; an autouse `_reset_osrm_cache` fixture in `conftest.py`; and new tests in `test_routing_service.py` covering cache-hit, distinct-key-miss, TTL expiry, LRU eviction order, error responses never being cached, and — the case that matters most — `compute_impact()` reflecting a `PipelineAlert` inserted between two `check_route()` calls even when the second call's route geometry came from cache.
>
> **A second council pass reviewed the actual code afterward** and found one thing worth changing: the first implementation used a lazy-rebuild-on-settings-change scheme (`_get_osrm_cache()` + a `global`-reassigned cache + a tracked config tuple) to let tests monkeypatch ttl/maxsize - the committee correctly called this unrequested complexity that diverged from both the plan's literal design and the only comparable existing pattern in the codebase (`rate_limit.py`'s plain module-level dict, mutated in place, never reassigned, no `global`). Simplified to a single `TTLCache` instance built once at import time, mutated in place (`.clear()`/`.get()`/`__setitem__`, no `global` anywhere); tests that need a different ttl/maxsize now `monkeypatch.setattr(routing_service, "_osrm_cache", TTLCache(...))` directly instead of going through settings. Also added: a defensive shallow copy on cache hit (closes a latent-but-currently-inert landmine where every caller sharing a cache key got the exact same mutable list object) and a new test proving a failed OSRM lookup is never cached (a gap the original test suite missed). Confirmed clean: no multi-worker deployment gap (Dockerfile runs a single uvicorn process), no async-interleaving corruption window (no `await` between cache read and write), and `compute_impact()` verified by direct code reading to have zero caching anywhere in its path. Full suite: 93 passed (was 87 before Phase C), pyright clean. Only Phase D (frontend) remains.

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

## 7. OSRM route-cache TTL (Phase C)

`get_routes()` in [backend/app/services/routing_service.py](../../backend/app/services/routing_service.py) calls the public OSRM demo server (`router.project-osrm.org`) on every `POST /route/check`, uncached. Two problems: that public server has no SLA and enforces usage limits, so repeated identical lookups needlessly burn against that budget and add latency; and now that saved routes exist (Phase B), a natural next frontend feature is "recheck this saved route," which will generate many requests for the exact same origin/destination in quick succession.

**What gets cached, and what doesn't.** Only `get_routes()`'s result (`list[OsrmRoute]` — geometry/distance/duration, i.e. the road-network answer) is cached. `compute_impact()` (which scores live pipeline alerts near the route) is **never** cached — it's deliberately re-run against current DB state on every call, since the road network doesn't change in 5 minutes but which alerts count as "recent" (`route_impact_lookback_minutes=45`) does. Caching the whole `/route/check` response would silently serve stale alert data; caching only the geometry lookup doesn't.

**Cache type — `cachetools.TTLCache`, not a hand-rolled dict.** The original draft of this section proposed a plain `dict` with FIFO eviction, reasoning it "mirrors" `SimpleRateLimitMiddleware`'s `_RateBucket` in [backend/app/core/middleware.py](../../backend/app/core/middleware.py). Committee review rejected that: `_RateBucket` is a single counter+window, not a TTL-plus-capacity cache, so it isn't actually the same shape of problem — the "avoid a dependency" reasoning didn't hold up. The committee also caught a concrete bug in the original design: nothing in it purged *expired* entries before applying the FIFO *capacity* cap, so a burst of one-off lookups could evict live, still-useful entries while already-expired garbage kept occupying slots. And FIFO itself fights this workload — the whole motivation for this cache is "the same popular routes get rechecked repeatedly," and FIFO evicts by insertion order regardless of hit frequency, so a hot route cached early can be evicted while cold one-off entries added later survive.

`cachetools` (pure Python, zero transitive dependencies, purpose-built for exactly this) gets both of these right out of the box and is a much smaller risk than reimplementing TTL/eviction interaction by hand — a notoriously easy category of code to get subtly wrong. Adding it to [backend/requirements.txt](../../backend/requirements.txt) as the one new pip dependency for this phase (breaking Phase A's "stdlib is enough" precedent deliberately, not by oversight — that precedent held for hashing/tokens, not for cache-eviction semantics).

- `_osrm_cache: TTLCache = TTLCache(maxsize=settings.osrm_cache_max_entries, ttl=settings.osrm_cache_ttl_seconds)` as a module-level object in `routing_service.py`; `TTLCache` handles expiry-vs-capacity interaction and least-recently-used eviction on overflow internally.
- **Key**: `(round(origin.lat, 4), round(origin.lng, 4), round(destination.lat, 4), round(destination.lng, 4))`. The original draft justified the 4-decimal (~11m) precision by pointing at `_location_key()`'s existing use of the same rounding — committee review flagged that as borrowed reasoning: `_location_key()` exists to deduplicate *alert detections* at roughly the same physical spot, a different "sameness" question from "should two people's route requests be treated as the same trip." The precision is kept at 4 decimals (~11m) but on its own merits for *this* use: OSRM snaps input coordinates to the nearest road segment before routing, so two origins ~11m apart (GPS jitter between two of the same user's requests, or two nearby-but-distinct addresses on the same road) will overwhelmingly snap to the same segment and get the same route — and the cache is explicitly a "close enough, road-snapped" answer by design, not a guarantee of the caller's literal coordinates. This is stated here explicitly so it doesn't need re-deriving later.
- **Concurrency**: no per-key lock. Two concurrent requests for the same not-yet-cached key can both miss and both call OSRM once each — same accepted-tradeoff shape as the saved-routes per-user-cap TOCTOU from Phase B (simplicity over perfect efficiency); revisit only if OSRM rate-limiting is actually observed.
- **Known limitation, not fixed here**: this cache is in-memory and per-process. If the backend ever runs as multiple instances (e.g. Railway/Render horizontal scaling), each instance keeps an independent cache — effective OSRM load then scales with instance count rather than with genuinely-unique request volume, and hit rates become inconsistent across instances. Not a correctness bug (worst case degrades toward today's fully-uncached behavior), but worth naming now rather than rediscovering later; a shared cache (Redis) would be the fix if this is ever observed to matter.

**New `Settings` fields** (`config.py`): `osrm_cache_ttl_seconds: int = Field(default=300, description="How long a cached OSRM route lookup stays valid")` (5 min — long enough to absorb repeated checks in one sitting, short enough that a genuinely new road closure isn't hidden for long; note this TTL has zero bearing on alert freshness, since alerts are never cached), `osrm_cache_max_entries: int = Field(default=500, description="Max distinct origin/destination pairs held in the OSRM cache (cachetools.TTLCache, LRU eviction on overflow)")`.

**Implementation location**: [backend/app/services/routing_service.py](../../backend/app/services/routing_service.py) itself — the cache wraps `get_routes()` directly (module-level `TTLCache` instance), not a new `core/` module, since nothing else needs it yet and it's tightly coupled to this one function.

**Testability.** A `_clear_osrm_cache()` test-only helper (`_osrm_cache.clear()`), wired into an autouse conftest fixture. The original draft compared this to `SimpleRateLimitMiddleware`'s per-instance `_buckets` dict — committee review corrected that too: the actual structural and testability match is [backend/app/core/rate_limit.py](../../backend/app/core/rate_limit.py)'s **module-level** dict + `reset_rate_limits()`, which is what `conftest.py`'s existing `_reset_rate_limits` autouse fixture already resets between every test.

**This fixture is load-bearing for the *existing* test suite, not just new tests.** `backend/tests/test_routing_service.py` already has four tests (`test_get_routes_parses_successful_osrm_response`, `test_get_routes_raises_on_no_route`, `test_get_routes_raises_on_upstream_http_error`, `test_get_routes_raises_when_server_unreachable`) that all reuse the same module-level `ORIGIN`/`DESTINATION` constants. Once a cache keyed on rounded origin/destination exists, whichever of those tests runs first and succeeds would poison the cache for the error-path tests that follow, unless `_clear_osrm_cache()` genuinely runs before every one of them — this is a correctness requirement for Phase C to not silently break Phase A/B-era tests, not an optional nicety.

**Test plan additions to** `backend/tests/test_routing_service.py`:
- second call with the same (rounded) origin/destination within the TTL does not re-invoke the mocked OSRM HTTP client.
- a call with a different origin/destination does invoke it (cache is actually keyed, not global).
- after `osrm_cache_ttl_seconds` elapses (mock time or monkeypatch the TTL to ~0), a repeat call re-invokes OSRM.
- **the four pre-existing `get_routes()` tests still each independently hit the mock** (i.e. the new autouse fixture is verified to actually isolate them, not just asserted to exist).
- `compute_impact()` is still called fresh on every `check_route()` invocation even when `get_routes()` is served from cache — the case that actually protects against the "silently stale alerts" failure mode, so the most important one to pin. This needs a test pattern not used elsewhere in this file: `@pytest.mark.db` (real `db_session`) *combined with* a mocked OSRM HTTP client in the same test. Concretely: call `check_route()` once to populate the geometry cache, insert a new `PipelineAlert` near that route directly via `db_session`, call `check_route()` again with the identical origin/destination, and assert `impacted_alerts` reflects the newly-inserted alert even though the OSRM mock was not called a second time.
- cache respects `osrm_cache_max_entries` (fill past the cap, confirm the least-recently-used entry — not necessarily the oldest-inserted one — was evicted; re-access an early entry before overflowing to distinguish LRU behavior from FIFO).

## 8. Execution phases

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

**Phase C — OSRM route-cache TTL** (depends only on the existing routing service; not yet started — design in section 7 above, amended after committee review, ready to implement):
1. `requirements.txt` — add `cachetools`.
2. `config.py` — add `osrm_cache_ttl_seconds` and `osrm_cache_max_entries`.
3. `routing_service.py` — module-level `cachetools.TTLCache` instance wrapping `get_routes()`; `_clear_osrm_cache()` test helper.
4. `conftest.py` — autouse fixture calling `_clear_osrm_cache()` between tests, matching the existing `_reset_rate_limits` fixture (and required for the *existing* `test_routing_service.py` tests to keep passing independently, per section 7).
5. `test_routing_service.py` — the six cases listed in section 7 above (cache hit/miss/TTL-expiry/LRU-eviction, pre-existing tests still isolated, impact-stays-fresh-on-cache-hit).

**Done bar for Phase C**: full `pytest` green (Phase A + B + C together), including every case listed in section 7's test plan — cache hit avoids a re-call, a different key doesn't, TTL expiry forces a re-call, LRU (not FIFO) eviction under the max-entries cap, the four pre-existing `get_routes()` tests remain isolated from each other, and — the one that actually matters most — `compute_impact()` still reflects a newly-inserted `PipelineAlert` on a second `check_route()` call even when the route geometry itself was served from cache.

Frontend work does not start until the Phase A, B, and C done-bars are all met.

**Phase D — frontend** (design only for now, not started this round):
- Add `react-router-dom` (only mainstream router that fits a handful of static routes with no need for its data-loader features); wrap `main.tsx`'s `<App />` in `<BrowserRouter>`.
- `lib/AuthContext.tsx` + `lib/useAuth.ts` — fetches `GET /auth/me` on mount, exposes `login`/`signup`/`logout`/state. No token to store client-side (it's an httpOnly cookie).
- `lib/api.ts`: `credentials: 'include'` on every fetch; read `mg_csrf` from `document.cookie`, attach `X-CSRF-Token` on non-GET requests; a 401 → single `/auth/refresh` attempt → retry-once interceptor in `http()`, with in-flight-refresh deduplication (so `Promise.all`-style concurrent calls in `App.tsx` don't each trigger their own refresh) and a `_retried` guard so a hard-failed refresh surfaces as a normal error instead of looping.
- New pages: `LoginPage`, `SignupPage`, `SavedRoutesPage`; a `ProtectedRoute` wrapper; routes at `/`, `/login`, `/signup`, `/saved-routes`.
- `RouteCheckPanel.tsx`: a "Save this route" button next to results, visible only when authenticated.
- Test updates: wrap `App.test.tsx` renders in `MemoryRouter` + a mocked auth provider, extend `api.test.ts` for credentials/CSRF/retry behavior, new tests for auth pages and the saved-routes page — following the existing `vi.mock('../src/lib/api', ...)` pattern already used throughout `frontend/tests/`.

## Verification

- Backend: `cd backend && venv/Scripts/python.exe -m pytest -v` (real Supabase DB, rollback-per-test as already established) — Phase A, B, and C done-bars above.
- Manual smoke check with no frontend: `curl -c cookies.txt -b cookies.txt` (or an httpx script) through signup → refresh → logout, inspecting `Set-Cookie` headers directly, as an independent sanity check beyond the automated tests.
- `pyright` clean (`venv/Scripts/pyright-python.exe`), matching the standard already held everywhere else in this backend.
- Frontend (Phase D, later): `npm test` (Vitest) + `npm run build` + a manual browser check that login persists across a refresh and that an expired-then-refreshed session keeps working without a visible logout.

## Known limitation carried over from Phase A (not fixed here)

`get_client_ip()` ([backend/app/core/rate_limit.py](../../backend/app/core/rate_limit.py)) trusts `X-Forwarded-For` unconditionally with no proxy-trust check, so `SimpleRateLimitMiddleware`'s IP-based limits (including the auth-specific login/signup limiters) are spoofable by any client that sets the header itself when not actually behind a trusted reverse proxy. This was flagged during the Phase B council review but is out of scope for saved routes specifically — worth a standalone fix (validate `X-Forwarded-For` only when a trusted proxy is configured, else use the direct connecting IP) before this app is exposed publicly behind a real proxy.
