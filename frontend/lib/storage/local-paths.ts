import { existsSync } from "fs";
import path from "path";

const DEFAULT_STORAGE_ROOT = "uploads";

function resolvePublicDir(): string {
  const cwd = process.cwd();
  const directPublic = path.join(cwd, "public");
  const nestedPublic = path.join(cwd, "frontend", "public");
  if (existsSync(directPublic)) return directPublic;
  if (existsSync(nestedPublic)) return nestedPublic;
  return directPublic;
}

/**
 * Resolves the on-disk root for local file storage.
 *
 * - Absolute `LOCAL_STORAGE_PATH` (e.g. `/data/uploads`) is used as-is. This is
 *   the recommended setup: mount a persistent volume there and serve files via
 *   the `/uploads/*` route handler instead of the `public/` directory.
 * - Relative values are resolved under the Next.js `public/` directory for
 *   backwards compatibility. `public/` and leading slashes are stripped.
 */
export function resolveLocalStorageRoot(): string {
  const raw = (process.env.LOCAL_STORAGE_PATH || DEFAULT_STORAGE_ROOT).trim();

  if (path.isAbsolute(raw)) {
    return path.resolve(raw);
  }

  let normalized = raw;
  if (normalized.startsWith("public/")) {
    normalized = normalized.slice("public/".length);
  }
  if (!normalized) normalized = DEFAULT_STORAGE_ROOT;
  return path.resolve(resolvePublicDir(), normalized);
}
