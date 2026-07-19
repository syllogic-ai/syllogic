import Constants from 'expo-constants';

// The Next.js web app (frontend/) hosts better-auth's HTTP routes
// (/api/auth/*) — sign-in/out and session issuance happen against this
// origin. Override at build/run time with EXPO_PUBLIC_AUTH_URL.
export const AUTH_URL =
  process.env.EXPO_PUBLIC_AUTH_URL ??
  Constants.expoConfig?.extra?.authUrl ??
  'http://localhost:3000';

// The FastAPI backend (backend/) serves all data endpoints
// (/api/accounts, /api/analytics, /api/investments, /api/saved-views) on a
// separate port. Override at build/run time with EXPO_PUBLIC_API_URL.
export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  Constants.expoConfig?.extra?.apiUrl ??
  'http://localhost:8000';
