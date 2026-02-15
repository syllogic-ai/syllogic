import { describe, expect, it } from "vitest";
import { buildTransactionsDrilldownQuery } from "@/lib/dashboard/drilldown-query";

describe("buildTransactionsDrilldownQuery", () => {
  it("serializes explicit date range and repeated accounts", () => {
    const query = buildTransactionsDrilldownQuery({
      categoryId: "cat-1",
      accountIds: ["acc-1", "acc-2"],
      dateFrom: "2026-01-01",
      dateTo: "2026-01-31",
      horizon: 7,
    });

    const params = new URLSearchParams(query);
    expect(params.get("category")).toBe("cat-1");
    expect(params.getAll("account")).toEqual(["acc-1", "acc-2"]);
    expect(params.get("from")).toBe("2026-01-01");
    expect(params.get("to")).toBe("2026-01-31");
    expect(params.has("horizon")).toBe(false);
  });

  it("serializes explicit horizon when no date range exists", () => {
    const query = buildTransactionsDrilldownQuery({
      categoryId: "cat-1",
      accountIds: ["acc-1"],
      horizon: 365,
    });

    const params = new URLSearchParams(query);
    expect(params.get("category")).toBe("cat-1");
    expect(params.getAll("account")).toEqual(["acc-1"]);
    expect(params.get("horizon")).toBe("365");
    expect(params.has("from")).toBe(false);
    expect(params.has("to")).toBe(false);
  });

  it("defaults horizon=30 when no date/horizon is provided", () => {
    const query = buildTransactionsDrilldownQuery({
      categoryId: "cat-1",
    });

    const params = new URLSearchParams(query);
    expect(params.get("horizon")).toBe("30");
  });
});
