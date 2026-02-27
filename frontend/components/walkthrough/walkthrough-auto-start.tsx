"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";
import { useWalkthroughStore, getPageConfig } from "./walkthrough-store";

/**
 * Auto-starts the walkthrough on first visit to each page.
 * - With ?tour=1: always start (e.g. after Get Started from onboarding)
 * - Without ?tour=1: start when user hasn't completed the tour for this page
 * Syncs completed state with current user so new signups get a fresh tour.
 */
export function WalkthroughAutoStart() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: session } = useSession();
  const { startWalkthrough, hasCompletedPage, syncWithUser } = useWalkthroughStore();
  const hasAutoStartedForPage = useRef<string | null>(null);

  // Sync completed state with current user (clears when user changes)
  useEffect(() => {
    if (session?.user?.id) {
      syncWithUser(session.user.id);
    }
  }, [session?.user?.id, syncWithUser]);

  useEffect(() => {
    const config = getPageConfig(pathname);
    if (!config) return;

    const tourParam = searchParams.get("tour");

    // (1) ?tour=1: explicit request (e.g. Get Started) - always start
    // (2) First visit to this page - auto-start when tour not yet completed
    const shouldAutoStart = tourParam === "1" || !hasCompletedPage(config.page);

    if (shouldAutoStart && hasAutoStartedForPage.current !== config.page) {
      hasAutoStartedForPage.current = config.page;
      // Small delay so DOM targets are ready after navigation
      const t = setTimeout(() => {
        startWalkthrough(config.page);
        if (tourParam === "1") router.replace(pathname, { scroll: false });
      }, 100);
      return () => clearTimeout(t);
    }
  }, [pathname, searchParams, startWalkthrough, hasCompletedPage]);

  return null;
}
