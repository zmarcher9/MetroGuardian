# Mobile app readiness notes

Not a commitment or a schedule — just capturing the design analysis from when
this was discussed, so it isn't lost before mobile becomes a real, scheduled
piece of work.

## Already in place (backend, auth only)

`get_current_user` ([backend/app/core/deps.py](backend/app/core/deps.py)) accepts either transport:
- Web: the httpOnly `mg_at` cookie.
- Mobile/native (no cookie jar): an `Authorization: Bearer <token>` header.

Signup/login/refresh ([backend/app/api/v1/routes_auth.py](backend/app/api/v1/routes_auth.py)) branch on an
`X-Client-Type: mobile` request header:
- Absent/`web` (default): tokens set as httpOnly cookies, never in the response body.
- `mobile`: tokens returned in the JSON body (`TokenResponse`), no cookies set. The client
  is responsible for storing them in secure native storage (iOS Keychain / Android Keystore)
  and sending the refresh token back explicitly in the body on `/auth/refresh` and `/auth/logout`
  (no cookie to rely on).

`CSRFMiddleware` ([backend/app/core/middleware.py](backend/app/core/middleware.py)) skips the CSRF check for
any request carrying an `Authorization` header or `X-Client-Type: mobile` — CSRF is a
cookie-specific attack (a browser auto-attaching credentials to a forged cross-site request);
it doesn't apply to a client that isn't using a cookie jar in the first place.

The refresh-token architecture itself (DB-backed opaque tokens, rotation-on-use, reuse
detection + family revocation) needs no changes for mobile — it's already transport-agnostic.

## Not started - real work when mobile becomes a scheduled task

- **Real-time alerts.** The `/alerts/stream` endpoint uses Server-Sent Events (`EventSource`),
  a browser-only API. Neither React Native nor native iOS/Android have it built in. Likely
  right call: switch the live-alerts transport to WebSockets, which has much more mature,
  consistent support across native mobile than SSE/polyfills do. This is a backend endpoint
  rewrite, not just a client-side change.
- **Push notifications** (already on the roadmap for v2, "notifications"). Needs new backend
  infrastructure that doesn't exist yet: storing a device push token per user, and a service
  that sends an APNs (iOS) / FCM (Android) push when a relevant alert fires.
- **CORS is irrelevant for native clients** (URLSession/OkHttp don't enforce it) - only
  matters for the web app running in parallel.

## Tech stack choice, when it's time

- **React Native**: reuses the `fetch()`-based logic in `frontend/src/lib/api.ts` almost as-is
  (swap cookie-attachment for secure-storage token attachment). Everything UI-related does
  not carry over: `MapView.tsx` (react-leaflet has no RN equivalent - would use
  `react-native-maps`) and all TailwindCSS styling (would need NativeWind or plain
  `StyleSheet`) need rewriting.
- **Fully native (Swift/Kotlin)**: zero code reuse with the existing TypeScript frontend -
  effectively a second app in a different ecosystem.

## Also worth knowing before treating this as "just an engineering task"

App Store / Play Store submission is a real operational process independent of any of the
above: developer accounts ($99/yr Apple, $25 one-time Google), app review, privacy policy,
screenshots/metadata, TestFlight/internal testing tracks.
