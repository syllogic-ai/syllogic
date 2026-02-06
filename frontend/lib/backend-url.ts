/**
 * Normalize backend base URL.
 *
 * In some environments (e.g. Render Blueprints), `fromService` provides a
 * `hostport` value like `my-backend:10000` without a URL scheme. This helper
 * makes sure we always end up with a valid absolute base URL.
 */
export function getBackendBaseUrl(): string {
  const raw = process.env.BACKEND_URL || "http://localhost:8000";
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw;
  }
  return `http://${raw}`;
}

