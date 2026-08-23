import { authClient } from './client';

// better-auth's Expo client keeps the session cookie in SecureStore (RN has
// no cookie jar). authClient.getCookie() returns it synchronously once the
// session has loaded, for attaching to our own backend requests manually.
export async function getSessionToken(): Promise<string | null> {
  const cookie = authClient.getCookie();
  return cookie || null;
}

export function getAuthHeader(cookie: string | null): Record<string, string> {
  return cookie ? { Cookie: cookie } : {};
}
