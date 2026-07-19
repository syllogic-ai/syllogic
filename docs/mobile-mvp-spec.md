# C-logic iOS + macOS App — MVP Spec & Implementation Plan

## 1. Summary

A companion app for existing C-logic web users, built once with Expo/React Native and
shipped to both iOS and macOS (via Mac Catalyst) from a single codebase. Scope: log in,
view bank account balances, filter which accounts are shown, save a named filter preset,
and view an investment portfolio summary.

**Non-goals for MVP:** transaction history, editing/creating accounts, CSV import,
notifications, offline caching, public App Store listing, Android.

## 2. Decisions locked in

| Area | Decision |
|---|---|
| Audience | Existing web app users; mobile/Mac is a lighter companion view, not a new product |
| Framework | Expo (React Native) for iOS, macOS via Mac Catalyst — one codebase, one EAS pipeline |
| Auth | Email/password via `better-auth`, using `@better-auth/expo` against the existing backend session flow |
| App re-entry security | Face ID / Touch ID gate on app foreground, session token kept in Keychain/Secure Store |
| Account data | Enable Banking-linked accounts + manually created "pocket" accounts, via existing `/accounts` and `/investments` FastAPI routes |
| Saved views | Filter criteria only (account IDs/types/currencies) — no layout/column prefs in MVP |
| Saved views storage | Redis-backed endpoint (reuses existing Redis infra, no new Postgres migration), keyed by user so it syncs across web/iOS/Mac |
| Portfolio screen | Holdings list + total portfolio value, read-only, no charts |
| Offline support | None — online-only, fetch on open, clear loading/error states |
| Distribution | iOS via TestFlight, macOS via a direct signed build shared with the team — no App Store submission in MVP |
| Team/timeline | Solo/small, few weeks — plan is intentionally sequential, not parallelized across a team |
| Apple Developer Program | **Not yet enrolled — this is a Phase 0 blocker**, enroll before any signing/TestFlight work |

## 3. Open technical note to resolve early

No "saved views" concept exists today in `backend/app/routes/accounts.py` or
`investments.py`. We're adding a small new endpoint backed by Redis rather than a
Postgres table, since it avoids a schema migration and Redis is already deployed
(`docker-compose.yml`, `REDIS_URL`, `appendonly yes` persistence). Tradeoff to flag:
Redis is not currently used as a system-of-record for user data elsewhere in this repo —
if Redis is ever flushed/rotated without care, saved views are lost (low blast radius:
users just re-apply filters). If that's unacceptable later, migrating this endpoint to a
real Postgres table is a small, isolated follow-up — the API contract won't change.

## 4. Architecture

```
syllogic/
  backend/            existing FastAPI — add one new route module
  frontend/           existing Next.js web app — untouched
  mobile/             NEW: Expo app (iOS + macOS Catalyst target)
    app/                 screens (expo-router)
    src/
      auth/              better-auth expo client wiring
      api/                typed API client (accounts, investments, saved-views)
      components/        RN UI primitives (account list row, filter sheet, etc.)
      state/              zustand store for active filter/session
  packages/
    shared/            NEW: pnpm workspace package
      types/             Zod schemas / TS types for Account, Investment, SavedView
      api-client/        fetch wrappers + react-query hooks, framework-agnostic
      filters/           filter application logic lifted from frontend/lib
```

`packages/shared` is consumed by both `frontend` and `mobile`. Only pull code into it
that's genuinely Next.js-agnostic (types, fetch calls, pure filter functions) — don't
force-share UI components, since RN and web render differently.

### Backend changes (small, additive)

- `backend/app/routes/saved_views.py` (new):
  - `GET /saved-views` — list current user's saved filter presets
  - `POST /saved-views` — create `{name, filters: {...}}`
  - `DELETE /saved-views/{id}` — remove one
  - Storage: Redis hash keyed `saved_views:{user_id}`, value = JSON list of `{id, name, filters, created_at}`. Reuses the existing `get_user_id` dependency and Redis client already wired for Celery/events.
- No changes needed to `/accounts` or `/investments` — mobile consumes them as-is.
- CORS/allowed-origins config may need the Expo dev origin and the Catalyst app's bundle scheme added for local testing.

### Mobile app auth flow

1. `@better-auth/expo` plugin configured against the backend's existing better-auth instance (same email/password flow as web).
2. On successful login, session token stored via Expo SecureStore (Keychain-backed on iOS/Mac).
3. On app foreground (via `AppState` listener), if a session exists, gate the UI behind `expo-local-authentication` (Face ID/Touch ID) before showing data. Fallback to device passcode per OS default behavior.
4. Logout clears SecureStore and revokes session server-side via existing better-auth sign-out endpoint.

### Core screens (MVP)

1. **Login** — email/password form, error states, "forgot password" deep-links to web (not rebuilt natively).
2. **Accounts list** — fetch `/accounts`, show balance per account (bank + pocket accounts), pull-to-refresh, loading/error/empty states.
3. **Filter sheet** — modal/sheet to select account types/currencies/specific accounts; applies client-side over the fetched list.
4. **Save view** — name the current filter combination, `POST /saved-views`; saved views listed and selectable to re-apply instantly.
5. **Portfolio** — fetch `/investments`, show holdings (name, quantity, value, currency) + total portfolio value.

macOS (Catalyst) reuses all five screens as-is; no separate Mac-only UI in MVP.

## 5. Implementation plan (sequential, solo/small team pace)

### Phase 0 — Prerequisites (before any signed build work)
- [ ] Enroll in Apple Developer Program (can take 1–2 days for approval) — **start this immediately, it's the longest lead time item and gates Phase 5**
- [ ] Confirm Redis persistence/backup policy is acceptable for saved-views data (per note in §3)

### Phase 1 — Foundations
- [ ] Scaffold `mobile/` Expo app (TypeScript, expo-router) inside the existing pnpm workspace
- [ ] Scaffold `packages/shared` workspace package; wire it into both `frontend` and `mobile` via pnpm workspace refs
- [ ] Move/adapt reusable types and pure filter logic from `frontend/lib` into `packages/shared` (audit first — don't move anything Next.js-coupled)
- [ ] Stand up `@better-auth/expo` against the existing backend; verify login/logout against a local backend instance

### Phase 2 — Accounts + filtering
- [ ] Accounts list screen wired to `/accounts` via shared API client + react-query
- [ ] Filter sheet UI + client-side filter application (using shared filter logic)
- [ ] Loading/error/empty states

### Phase 3 — Saved views
- [ ] Backend: `saved_views.py` route + Redis storage
- [ ] Mobile: save-current-filters UI, list/apply/delete saved views

### Phase 4 — Portfolio + security polish
- [ ] Portfolio screen wired to `/investments`
- [ ] Face ID/Touch ID app-foreground gate via `expo-local-authentication`
- [ ] SecureStore session persistence, logout flow

### Phase 5 — macOS target + distribution
- [ ] Enable Mac Catalyst build target in Expo/EAS config for the same app
- [ ] Verify all 5 screens function acceptably under Catalyst (expect some iPad-on-Mac visual rough edges — acceptable for MVP)
- [ ] EAS Build: iOS build → TestFlight internal testing
- [ ] EAS/Xcode: signed Mac build → shared directly with team (no Mac App Store submission)

### Phase 6 — MVP hardening
- [ ] Manual test pass: login, balances, filter, save/apply view, portfolio, on both iOS and Mac builds
- [ ] Error-state pass (no network, expired session, empty accounts)
- [ ] Ship to TestFlight testers + Mac build recipients

## 6. Explicitly deferred (post-MVP candidates)

- Offline caching of last-fetched balances
- Push notifications (balance alerts, sync status)
- Saved-view layout/column/sort preferences (beyond filter criteria)
- Portfolio performance charts / historical gain-loss
- Public App Store + Mac App Store listings
- Native (non-Catalyst) macOS UI via `react-native-macos`
- Android
