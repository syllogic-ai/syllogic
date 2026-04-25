import { describe, it, expect } from "vitest";
import {
  getAssetCategory,
  ASSET_CATEGORY_LABELS,
  ASSET_CATEGORY_COLORS,
  ASSET_CATEGORY_ORDER,
} from "./asset-category";

describe("getAssetCategory", () => {
  it("maps checking to cash", () => {
    expect(getAssetCategory("checking")).toBe("cash");
  });

  it("maps savings to savings (its own asset class)", () => {
    expect(getAssetCategory("savings")).toBe("savings");
  });

  it("maps credit to other", () => {
    expect(getAssetCategory("credit")).toBe("other");
  });

  it("maps investment and brokerage to investment", () => {
    expect(getAssetCategory("investment")).toBe("investment");
    expect(getAssetCategory("brokerage")).toBe("investment");
  });

  it("maps investment_brokerage and investment_manual to investment", () => {
    // IBKR sync and manual investments use these account_type values.
    expect(getAssetCategory("investment_brokerage")).toBe("investment");
    expect(getAssetCategory("investment_manual")).toBe("investment");
  });

  it("maps credit_card to other", () => {
    expect(getAssetCategory("credit_card")).toBe("other");
  });

  it("maps cash to cash", () => {
    expect(getAssetCategory("cash")).toBe("cash");
  });

  it("maps crypto / property / vehicle to themselves", () => {
    expect(getAssetCategory("crypto")).toBe("crypto");
    expect(getAssetCategory("property")).toBe("property");
    expect(getAssetCategory("vehicle")).toBe("vehicle");
  });

  it("is case-insensitive", () => {
    expect(getAssetCategory("SAVINGS")).toBe("savings");
    expect(getAssetCategory("Checking")).toBe("cash");
  });

  it("falls back to other for unknown types", () => {
    expect(getAssetCategory("zzz")).toBe("other");
  });

  it("returns other for null or undefined input", () => {
    expect(getAssetCategory(null)).toBe("other");
    expect(getAssetCategory(undefined)).toBe("other");
  });
});

describe("ASSET_CATEGORY_ORDER", () => {
  it("places savings immediately after cash", () => {
    const cashIdx = ASSET_CATEGORY_ORDER.indexOf("cash");
    const savingsIdx = ASSET_CATEGORY_ORDER.indexOf("savings");
    expect(savingsIdx).toBe(cashIdx + 1);
  });

  it("includes all 7 asset classes exactly once", () => {
    expect(ASSET_CATEGORY_ORDER).toEqual([
      "cash",
      "savings",
      "investment",
      "crypto",
      "property",
      "vehicle",
      "other",
    ]);
  });
});

describe("display metadata", () => {
  it("provides a label and color for every key in the order", () => {
    for (const key of ASSET_CATEGORY_ORDER) {
      expect(ASSET_CATEGORY_LABELS[key]).toBeTruthy();
      expect(ASSET_CATEGORY_COLORS[key]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it("uses distinct colors for cash and savings", () => {
    expect(ASSET_CATEGORY_COLORS.cash).not.toBe(ASSET_CATEGORY_COLORS.savings);
  });

  it("labels savings as 'Savings'", () => {
    expect(ASSET_CATEGORY_LABELS.savings).toBe("Savings");
  });
});
