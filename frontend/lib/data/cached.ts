// Cached read layer. NOT a "use server" module.
// Two cache layers:
// - React.cache: per-request dedup (no TTL, scoped to a single render).
// - unstable_cache: cross-request, keyed by userId, invalidated by tag.
// Mutations MUST call revalidateTag(...) for the relevant tag below.

import { cache } from "react";
import { unstable_cache } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, categories, users } from "@/lib/db/schema";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { resolveMissingAccountLogos } from "@/lib/actions/account-logos";
import type { OnboardingStatus, OnboardingStatusResult } from "@/lib/actions/onboarding";

export const CACHE_TAGS = {
  categories: (userId: string) => `categories:${userId}`,
  accounts: (userId: string) => `accounts:${userId}`,
  onboarding: (userId: string) => `onboarding:${userId}`,
} as const;

export const getCachedSession = cache(async () => {
  return getAuthenticatedSession();
});

// ---------- Categories ----------

async function fetchCategoriesForUser(userId: string) {
  return db.query.categories.findMany({
    where: eq(categories.userId, userId),
    orderBy: (c, { asc }) => [asc(c.name)],
  });
}

const getCachedCategoriesByUser = (userId: string) =>
  unstable_cache(
    () => fetchCategoriesForUser(userId),
    ["categories", userId],
    { tags: [CACHE_TAGS.categories(userId)] },
  )();

export const getCachedUserCategories = cache(async () => {
  const session = await getCachedSession();
  const userId = session?.user?.id;
  if (!userId) return [];
  return getCachedCategoriesByUser(userId);
});

// ---------- Accounts (slim, for filter dropdowns) ----------

async function fetchAccountsForUser(userId: string) {
  return db
    .select({
      id: accounts.id,
      name: accounts.name,
      institution: accounts.institution,
      accountType: accounts.accountType,
      currency: accounts.currency,
    })
    .from(accounts)
    .where(and(eq(accounts.userId, userId), eq(accounts.isActive, true)))
    .orderBy(accounts.name);
}

const getCachedAccountsByUser = (userId: string) =>
  unstable_cache(
    () => fetchAccountsForUser(userId),
    ["accounts", userId],
    { tags: [CACHE_TAGS.accounts(userId)] },
  )();

export const getCachedUserAccounts = cache(async () => {
  const session = await getCachedSession();
  const userId = session?.user?.id;
  if (!userId) return [];
  return getCachedAccountsByUser(userId);
});

// ---------- Accounts (full, with logos — superset for getAccounts) ----------

async function fetchFullAccountsForUser(userId: string) {
  const accountRows = await db.query.accounts.findMany({
    where: and(eq(accounts.userId, userId), eq(accounts.isActive, true)),
    orderBy: (accounts, { asc }) => [asc(accounts.name)],
    with: {
      logo: {
        columns: {
          id: true,
          logoUrl: true,
          updatedAt: true,
        },
      },
    },
  });
  return resolveMissingAccountLogos(accountRows);
}

const getCachedFullAccountsByUser = (userId: string) =>
  unstable_cache(
    () => fetchFullAccountsForUser(userId),
    ["accounts:full", userId],
    { tags: [CACHE_TAGS.accounts(userId)] },
  )();

export const getCachedFullUserAccounts = cache(async () => {
  const session = await getCachedSession();
  const userId = session?.user?.id;
  if (!userId) return [];
  return getCachedFullAccountsByUser(userId);
});

// ---------- Onboarding status ----------
// Inlined DB lookup (mirrors lib/actions/onboarding.ts#getOnboardingStatus) to
// avoid a circular import: that module is "use server" and pulls in storage,
// constants, and other action modules.

async function fetchOnboardingStatusForUser(
  userId: string,
): Promise<OnboardingStatusResult | null> {
  try {
    const user = await db.query.users.findFirst({
      where: eq(users.id, userId),
    });

    if (!user) {
      console.warn(`[Onboarding] User not found: ${userId}`);
      return null;
    }

    const status = (user.onboardingStatus as OnboardingStatus) || "pending";

    return {
      status,
      isCompleted: status === "completed",
    };
  } catch (error: any) {
    console.error("[Onboarding] Failed to get onboarding status:", {
      error: error?.message || String(error),
      stack: error?.stack,
      userId,
      databaseUrl: process.env.DATABASE_URL ? "set" : "not set",
    });
    return {
      status: "pending",
      isCompleted: false,
    };
  }
}

const getCachedOnboardingStatusByUser = (userId: string) =>
  unstable_cache(
    () => fetchOnboardingStatusForUser(userId),
    ["onboarding", userId],
    { tags: [CACHE_TAGS.onboarding(userId)] },
  )();

export const getCachedOnboardingStatus = cache(async () => {
  const session = await getCachedSession();
  const userId = session?.user?.id;
  if (!userId) return null;
  return getCachedOnboardingStatusByUser(userId);
});
