"use server";

import { headers } from "next/headers";
import { auth } from "@/lib/auth";

/**
 * Get the authenticated session from BetterAuth
 */
export async function getAuthenticatedSession() {
  return auth.api.getSession({ headers: await headers() });
}

/**
 * Get the authenticated user's ID, or null if not authenticated
 */
export async function requireAuth(): Promise<string | null> {
  const session = await getAuthenticatedSession();
  return session?.user?.id ?? null;
}

/**
 * Standard unauthorized response for server actions
 */
export type ActionResult<T = void> =
  | { success: true; data?: T }
  | { success: false; error: string };

/**
 * Wrap an action handler with authentication check
 * Returns a standard error response if not authenticated
 */
export async function withAuth<T>(
  handler: (userId: string) => Promise<T>,
  onUnauthorized?: T
): Promise<T> {
  const userId = await requireAuth();
  if (!userId) {
    return onUnauthorized ?? ({ success: false, error: "Not authenticated" } as T);
  }
  return handler(userId);
}
