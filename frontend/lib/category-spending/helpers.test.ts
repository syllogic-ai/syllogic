import { describe, expect, it } from "vitest";
import {
  computePreviousWindow,
  formatIsoDate,
  getTouchedMonthKeys,
  resolveCategoryColor,
} from "@/lib/category-spending/helpers";

describe("category-spending helpers", () => {
  it("computes previous same-length comparison window", () => {
    const start = new Date(2026, 1, 10, 0, 0, 0, 0);
    const end = new Date(2026, 1, 19, 23, 59, 59, 999);

    const { comparisonStart, comparisonEnd, spanDays } = computePreviousWindow(start, end);

    expect(spanDays).toBe(10);
    expect(formatIsoDate(comparisonStart)).toBe("2026-01-31");
    expect(formatIsoDate(comparisonEnd)).toBe("2026-02-09");
  });

  it("returns touched month keys inclusive", () => {
    const keys = getTouchedMonthKeys(new Date(2026, 0, 20), new Date(2026, 2, 2));
    expect(keys).toEqual(["2026-01", "2026-02", "2026-03"]);
  });

  it("uses category color if provided and fallback palette when missing", () => {
    expect(resolveCategoryColor("#123456", 2)).toBe("#123456");
    expect(resolveCategoryColor(null, 0)).toBe("#92400E");
  });
});
