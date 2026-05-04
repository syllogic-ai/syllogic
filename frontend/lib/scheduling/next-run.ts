import { Cron } from "croner";

/**
 * Compute the next firing time in UTC for a cron expression in the given timezone.
 * Returns null if the cron is invalid (caller should handle by leaving next_run_at null).
 */
export function nextFireAfter(cron: string, timezone: string, after: Date = new Date()): Date | null {
  try {
    const c = new Cron(cron, { timezone });
    const next = c.nextRun(after);
    return next ?? null;
  } catch {
    return null;
  }
}
