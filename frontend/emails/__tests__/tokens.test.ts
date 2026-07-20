import { describe, expect, it } from "vitest";
import { dark, fmtMoney, fontStack, light, radius } from "../components/report/tokens";

describe("email tokens", () => {
  it("pins light tokens to the stone ramp", () => {
    expect(light.background).toBe("#FFFFFF");
    expect(light.foreground).toBe("#0C0A09");
    expect(light.muted).toBe("#F5F5F4");
    expect(light.mutedForeground).toBe("#78716C");
    expect(light.border).toBe("#E7E5E4");
    expect(light.secondary).toBe("#F5F5F4");
    expect(light.destructive).toBe("#DC2626");
  });

  it("pins dark tokens", () => {
    expect(dark.background).toBe("#121110");
    expect(dark.foreground).toBe("#FAFAF9");
    expect(dark.card).toBe("#1C1917");
    expect(dark.muted).toBe("#292524");
    expect(dark.mutedForeground).toBe("#A8A29E");
    expect(dark.destructive).toBe("#F87171");
  });

  it("is square-cornered and monospace", () => {
    expect(radius).toBe("0px");
    expect(fontStack).toContain("JetBrains Mono");
    expect(fontStack).toContain("monospace");
  });

  it("contains no green", () => {
    const all = [...Object.values(light), ...Object.values(dark)].join(",");
    expect(all).not.toContain("#10B981");
  });
});

describe("fmtMoney", () => {
  it("formats to two decimals with a thousands separator", () => {
    expect(fmtMoney("3394.04", "EUR")).toBe("3,394.04 EUR");
    expect(fmtMoney("0", "EUR")).toBe("0.00 EUR");
  });

  it("passes through unparseable values rather than printing NaN", () => {
    expect(fmtMoney("n/a", "EUR")).toBe("n/a EUR");
  });
});
