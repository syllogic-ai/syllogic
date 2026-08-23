import Constants from 'expo-constants';

// The Next.js web app (frontend/) hosts better-auth's HTTP routes
// (/api/auth/*) — sign-in/out and session issuance happen against this
// origin. Override at build/run time with EXPO_PUBLIC_AUTH_URL.
export const AUTH_URL =
  process.env.EXPO_PUBLIC_AUTH_URL ??
  Constants.expoConfig?.extra?.authUrl ??
  'http://localhost:3000';

// Data endpoints (/api/analytics, /api/investments, /api/saved-views).
//
// In local dev this points straight at the FastAPI backend on :8000. In
// production it must point at the Next.js origin instead — FastAPI is NOT
// publicly reachable (Coolify exposes only app.syllogic.ai and
// mcp.syllogic.ai; the backend is an internal Docker address,
// BACKEND_URL=http://backend:8000). frontend/app/api/[...path]/route.ts is a
// catch-all that authenticates the session cookie and re-signs the request
// with HMAC internal-auth headers before forwarding, so pointing this at the
// Next.js origin works unchanged:
//
//   EXPO_PUBLIC_API_URL=https://app.syllogic.ai
//
// NOTE the widget reads its own copy of this from Info.plist, baked at
// PREBUILD time by mobile/plugins/with-widget-api-url.js. Export the variable
// for `expo prebuild`, not just the JS build, or the app talks to production
// while the widget talks to localhost. Override at build/run time with
// EXPO_PUBLIC_API_URL.
export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  Constants.expoConfig?.extra?.apiUrl ??
  'http://localhost:8000';
