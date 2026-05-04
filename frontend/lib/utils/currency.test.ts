import { describe, it, expect } from "vitest";
import { currencySymbol } from "./currency";

describe("currencySymbol", () => {
  it("maps USD to $", () => expect(currencySymbol("USD")).toBe("$"));
  it("maps EUR to €", () => expect(currencySymbol("EUR")).toBe("€"));
  it("maps GBP to £", () => expect(currencySymbol("GBP")).toBe("£"));
  it("falls back to the code itself for unknown currencies", () =>
    expect(currencySymbol("JPY")).toBe("JPY"));
  it("is case-insensitive", () =>
    expect(currencySymbol("usd")).toBe("$"));
});
