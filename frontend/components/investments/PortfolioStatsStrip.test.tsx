import { describe, it, expect } from "vitest";
import { computeBestDay } from "./PortfolioStatsStrip";

describe("computeBestDay", () => {
  it("returns the largest single-day positive delta", () => {
    expect(computeBestDay([100, 90, 130, 120, 200])).toEqual({
      delta: 80,
      index: 4,
    });
  });
  it("returns null for flat or empty series", () => {
    expect(computeBestDay([])).toBeNull();
    expect(computeBestDay([100])).toBeNull();
  });
});
