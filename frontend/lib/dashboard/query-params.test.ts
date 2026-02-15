import { describe, expect, it } from "vitest";
import {
  parseDashboardSearchParams,
  parseHorizonParam,
  parseIsoDateParam,
} from "@/lib/dashboard/query-params";

describe("query-params helpers", () => {
  it("accepts only strict yyyy-MM-dd dates", () => {
    expect(parseIsoDateParam("2026-02-05")).toBe("2026-02-05");
    expect(parseIsoDateParam("2026-2-5")).toBeUndefined();
    expect(parseIsoDateParam("2026-13-01")).toBeUndefined();
    expect(parseIsoDateParam("not-a-date")).toBeUndefined();
  });

  it("parses only supported horizon values", () => {
    expect(parseHorizonParam("7")).toBe(7);
    expect(parseHorizonParam("30")).toBe(30);
    expect(parseHorizonParam("365")).toBe(365);
    expect(parseHorizonParam("12")).toBeUndefined();
    expect(parseHorizonParam("abc")).toBeUndefined();
  });

  it("parses repeated and comma-separated account params", () => {
    const parsed = parseDashboardSearchParams({
      account: ["acc-1,acc-2", "acc-3"],
      horizon: "30",
    });
    expect(parsed.accountIds).toEqual(["acc-1", "acc-2", "acc-3"]);
  });

  it("drops invalid date range where to < from", () => {
    const parsed = parseDashboardSearchParams({
      from: "2026-02-10",
      to: "2026-02-05",
      horizon: "7",
    });
    expect(parsed.dateFrom).toBe("2026-02-10");
    expect(parsed.dateTo).toBeUndefined();
  });

  it("falls back to horizon=30 for invalid horizon values", () => {
    const parsed = parseDashboardSearchParams({
      horizon: "999",
    });
    expect(parsed.horizon).toBe(30);
    expect(parsed.effectiveHorizon).toBe(30);
  });
});
