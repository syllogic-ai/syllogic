# Handover: Syllogic iOS/macOS MVP

Read `docs/mobile-mvp-spec.md` first for the full spec and phased plan. This
doc is the "pick up here" state as of the end of this session.

## Where things stand

All of Phase 1–4 (foundations, accounts+filtering, saved views, portfolio,
biometric lock) are built and typecheck cleanly. Phase 5 (macOS Catalyst +
EAS build/distribution) is in progress and currently **blocked on Apple**,
not on us — see "Current blocker" below.

Task list (from this session's TaskCreate/TaskUpdate, for reference):
1. ✅ Clean up Expo scaffold (pnpm, removed template demo files)
2. ✅ Wire up better-auth Expo client
3. ✅ Port shared types/API client into mobile/src
4. ✅ Build accounts list + filter sheet screens
5. ✅ Add saved-views backend endpoint (Redis-backed)
6. ✅ Build saved-views UI + portfolio screen
7. ✅ Add Face ID/Touch ID app-lock gate
8. 🔶 Enable Mac Catalyst target + EAS build config — **in progress, blocked**

## Current blocker

The user (johnkotsas@me.com, Expo account `gianniskotsas`) enrolled in the
Apple Developer Program, but as of session end **the Program membership was
still "Processing"** on developer.apple.com — `eas build` failed with:

```
Authentication with Apple Developer Portal failed!
You have no team associated with your Apple account, cannot proceed.
```

This is expected until Apple finishes activating the membership (can take
minutes to ~48h). **Next step: ask the user whether
developer.apple.com/account now shows the membership as Active with a Team
ID.** If yes, resume with the build command below. If still processing,
there's nothing to do but wait.

## Resuming the iOS build once Apple is Active

EAS project is already linked: `@gianniskotsas/clogic-mobile`
(projectId `c84663e0-c9b3-4860-a5e0-524b6f1c185a`, see `mobile/app.json`
`extra.eas.projectId`). Note the EAS *slug* is still `clogic-mobile` even
though the app was renamed to Syllogic mid-session — renaming the slug now
would risk detaching it from the already-created EAS project, so it was
deliberately left alone. Purely cosmetic; doesn't affect functionality.

To build, from `mobile/`:

```bash
export EXPO_TOKEN=<a valid token from expo.dev account settings>
npx eas-cli build --platform ios --profile preview
```

Expect these interactive prompts (this needs a real terminal / an
interactive tool like the paseo terminal MCP tools — `eas build` cannot run
fully non-interactively for a first-time credentials setup):
- "Install expo-updates / configure EAS Update now?" → **no** (not needed
  for MVP)
- "Do you want to log in to your Apple account?" → **yes**
- Apple ID email, then an **app-specific password** (generate fresh at
  appleid.apple.com → Sign-In and Security → App-Specific Passwords —
  do NOT use the real Apple ID password)
- 2FA code (device/SMS) if prompted

If it succeeds, EAS will generate a distribution certificate + provisioning
profile for bundle ID `ai.syllogic.mobile` and start the cloud build. Once
that finishes:

```bash
npx eas-cli submit --platform ios --latest
```

to push it to TestFlight.

### Security note on credentials used this session

An `EXPO_TOKEN` and an Apple app-specific password were both pasted directly
into the chat transcript during this session (the user made an informed
call to do this after I flagged the risk, since app-specific passwords are
scoped/revocable). **Recommend rotating both before/when resuming**: revoke
the old app-specific password and generate a new one at appleid.apple.com,
and generate a fresh `EXPO_TOKEN` at expo.dev if the old one is still
sitting in shell history anywhere.

## macOS / Mac Catalyst — still unstarted, needs a real Mac

EAS Build's cloud service does **not** have a Catalyst build profile — it
only builds iOS binaries. Enabling Catalyst requires, on an actual Mac with
Xcode installed:

```bash
npx expo prebuild -p ios
```

then in Xcode, open the generated `ios/*.xcworkspace`, enable "Mac
Catalyst" under the target's "General → Supported Destinations," and
archive/run from there. This can't be done from this (Linux, no Xcode)
environment — it's a manual step for whoever has Mac + Xcode access.

## Architecture decisions made this session (important context)

1. **Framework**: Expo/React Native for iOS, with macOS via Mac Catalyst
   later (not `react-native-macos`) — one codebase, one EAS pipeline.
2. **No monorepo restructuring**: `frontend/` is already its own
   self-contained pnpm workspace (`frontend/pnpm-workspace.yaml`, used
   directly as the Docker build context for Railway/CasaOS deploys per
   `frontend/Dockerfile`). Restructuring it into a root monorepo to share
   code with `mobile/` would risk breaking those deploy pipelines, so
   `mobile/` is a fully independent Expo app with its own
   `pnpm-workspace.yaml` (`packages: [.]`). Reusable types/API-client logic
   were **ported** (copied and adapted), not symlinked/shared via a
   workspace package.
3. **Auth — the important correction**: FastAPI's `get_user_id()`
   (`backend/app/db_helpers.py`) originally only accepted two auth forms:
   an MCP bearer/API-key, or an HMAC-signed "internal auth" header set by
   the Next.js server (`INTERNAL_AUTH_SECRET`, server-side only — must
   never ship in a mobile bundle, since anyone could extract it from the
   IPA and impersonate any user). The mobile app can't produce that
   signature. Fix: `backend/app/main.py`'s `internal_auth_middleware` now
   checks for the `x-syllogic-user-id` header first (existing Next.js
   path, unchanged); if absent, it falls back to
   `get_user_id_from_session_cookie()` (new, in `db_helpers.py`), which
   reads the better-auth session cookie directly off the request and looks
   the token up against the existing `sessions` table (same Postgres DB
   better-auth already writes to — no new auth system, no shared secret
   exposed to the client). This is why the mobile app's `api/client.ts`
   attaches the better-auth cookie via `Cookie` header rather than a Bearer
   token — matches what `@better-auth/expo`'s `authClient.getCookie()`
   actually returns (a `name=value` cookie string, signed as
   `token.signature`; the DB lookup splits on the first `.` to get the raw
   token).
4. **Two separate origins**: the mobile app talks to **two different
   backend services** — better-auth's HTTP routes (`/api/auth/*`) live on
   the **Next.js frontend** origin (`AUTH_URL`, default
   `http://localhost:3000`), while all data endpoints
   (`/api/accounts`, `/api/analytics/*`, `/api/investments/*`,
   `/api/saved-views`) live on the **FastAPI backend** origin (`API_URL`,
   default `http://localhost:8000`). Both are configurable via
   `EXPO_PUBLIC_AUTH_URL` / `EXPO_PUBLIC_API_URL` — see `mobile/src/config.ts`.
   **These still point at localhost** — before a real device build is
   useful, set both to deployed URLs (via `eas env:create` per build
   profile, or hardcoded per-profile in `eas.json`).
5. **Saved views storage**: Redis-backed (`backend/app/routes/saved_views.py`),
   keyed `saved_views:{user_id}`, not a new Postgres table — reuses
   existing Redis infra (`REDIS_URL`, already deployed for Celery/events).
   Tradeoff: Redis isn't currently a system-of-record for user data
   elsewhere in this repo; if that Redis instance is ever flushed without
   care, saved views are lost (low blast radius — users just re-apply
   filters). Migrating to Postgres later is a small, isolated follow-up;
   the route contract (`GET/POST/DELETE /api/saved-views`) wouldn't change.
6. **App renamed mid-session**: originally scaffolded as "C-logic" /
   `ai.syllogic.clogic`, corrected to "Syllogic" / `ai.syllogic.mobile`
   partway through (see `mobile/app.json`, `mobile/src/auth/client.ts` —
   scheme is now `syllogic`, matching the bundle ID rename). Double-check
   no stray "clogic"/"C-logic" references before shipping (a
   `grep -rn "clogic\|C-logic" mobile/` was clean at last check, other than
   the deliberately-unchanged EAS slug noted above).

## Known rough edges / follow-ups (not blockers)

- `mobile/expo-env.d.ts` is gitignored by Expo convention (regenerated by
  `expo start`/`expo prebuild`) but a fresh generation **won't** include
  the `declare module '*.css';` line this session added to fix a
  `tsc --noEmit` error on `@/global.css` (imported by
  `src/constants/theme.ts` for web support). If a fresh clone hits that
  same tsc error, just re-add that one line to the regenerated file.
- Lint (`npx expo lint`) was never actually run successfully — it tried to
  auto-install eslint deps via a bare `pnpm` binary that isn't on PATH in
  this environment (`spawn pnpm ENOENT`; had to use `npx pnpm` throughout
  instead). Worth running properly once on a normal dev machine with pnpm
  installed globally.
- No simulator/device/browser testing was done at all this session (no
  Xcode, no iOS simulator, no way to run the Next.js+FastAPI backend
  locally in this environment). Typecheck-clean only. First real
  end-to-end login/data-fetch test is still outstanding.
- CORS origins (`_get_cors_origins()` in `backend/app/main.py`) may need
  the Expo dev server / Catalyst app's origin added once you're testing
  against a real deployed backend from the Expo web target specifically
  (native iOS/Mac app requests aren't subject to browser CORS, so this
  only matters for `expo start --web`).

## Files touched this session

- `backend/app/db_helpers.py` — added `get_user_id_from_session_cookie()`,
  `SESSION_COOKIE_NAMES`, `SessionModel` import
- `backend/app/main.py` — middleware fallback to session-cookie auth
- `backend/app/routes/__init__.py` — registered `saved_views` router
- `backend/app/routes/saved_views.py` — new, Redis-backed CRUD
- `mobile/` — new Expo app, entire tree (see spec doc for structure)
- `docs/mobile-mvp-spec.md` — the spec/plan (read this first)
- `docs/mobile-mvp-handover.md` — this file
