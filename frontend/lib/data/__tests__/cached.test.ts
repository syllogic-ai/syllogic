import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/db", () => ({
  db: {
    select: vi.fn(),
    query: { categories: { findMany: vi.fn() } },
  },
}));

vi.mock("@/lib/auth-helpers", () => ({
  getAuthenticatedSession: vi.fn(),
}));

vi.mock("next/cache", () => ({
  unstable_cache: <T extends (...args: any[]) => any>(fn: T) => fn,
  revalidateTag: vi.fn(),
}));

vi.mock("@/lib/actions/account-logos", () => ({
  resolveMissingAccountLogos: (rows: any) => rows,
  resolveMissingAccountLogo: (row: any) => row,
}));

describe("cached data layer", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("dedupes getCachedUserCategories within a single request via React.cache", async () => {
    const { getAuthenticatedSession } = await import("@/lib/auth-helpers");
    (getAuthenticatedSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { id: "user-1" },
    });

    const { getCachedUserCategories } = await import("../cached");

    const a = await getCachedUserCategories();
    const b = await getCachedUserCategories();

    expect(a).toBe(b);
  });
});
