import { describe, expect, it } from "vitest";
import {
  buildCategorySpendingQuery,
  parseCategorySpendingSearchParams,
} from "@/lib/category-spending/query-params";

describe("category-spending query params", () => {
  it("parses valid date range and multi-category params", () => {
    const parsed = parseCategorySpendingSearchParams({
      account: ["acc-1", "acc-2"],
      from: "2026-01-01",
      to: "2026-01-31",
      category: ["cat-1", "cat-2"],
      page: "3",
      pageSize: "50",
      sort: "amount",
      order: "asc",
      horizon: "365",
    });

    expect(parsed.accountIds).toEqual(["acc-1", "acc-2"]);
    expect(parsed.dateFrom).toBe("2026-01-01");
    expect(parsed.dateTo).toBe("2026-01-31");
    expect(parsed.categoryIds).toEqual(["cat-1", "cat-2"]);
    expect(parsed.page).toBe(3);
    expect(parsed.pageSize).toBe(50);
    expect(parsed.sort).toBe("amount");
    expect(parsed.order).toBe("asc");
    expect(parsed.effectiveHorizon).toBe(undefined);
  });

  it("defaults to 30-day horizon when no from date is present", () => {
    const parsed = parseCategorySpendingSearchParams({
      to: "2026-01-31",
    });

    expect(parsed.dateFrom).toBe(undefined);
    expect(parsed.dateTo).toBe(undefined);
    expect(parsed.horizon).toBe(undefined);
    expect(parsed.effectiveHorizon).toBe(30);
    expect(parsed.page).toBe(1);
    expect(parsed.pageSize).toBe(20);
    expect(parsed.sort).toBe("bookedAt");
    expect(parsed.order).toBe("desc");
  });

  it("builds query with date range precedence", () => {
    const query = buildCategorySpendingQuery({
      accountIds: ["acc-1", "acc-2"],
      categoryIds: ["cat-1", "cat-2"],
      dateFrom: "2026-02-01",
      dateTo: "2026-02-15",
      horizon: 30,
    });

    const params = new URLSearchParams(query);
    expect(params.getAll("account")).toEqual(["acc-1", "acc-2"]);
    expect(params.getAll("category")).toEqual(["cat-1", "cat-2"]);
    expect(params.get("from")).toBe("2026-02-01");
    expect(params.get("to")).toBe("2026-02-15");
    expect(params.has("horizon")).toBe(false);
  });

  it("builds query with horizon when date range is missing", () => {
    const query = buildCategorySpendingQuery({
      categoryId: "cat-2",
      horizon: "365",
    });

    const params = new URLSearchParams(query);
    expect(params.getAll("category")).toEqual(["cat-2"]);
    expect(params.get("horizon")).toBe("365");
  });

  it("omits default pagination and sorting params", () => {
    const query = buildCategorySpendingQuery({
      page: 1,
      pageSize: 20,
      sort: "bookedAt",
      order: "desc",
      horizon: 30,
    });

    const params = new URLSearchParams(query);
    expect(params.has("page")).toBe(false);
    expect(params.has("pageSize")).toBe(false);
    expect(params.has("sort")).toBe(false);
    expect(params.has("order")).toBe(false);
    expect(params.has("horizon")).toBe(false);
  });
});
