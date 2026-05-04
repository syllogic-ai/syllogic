import { describe, it, expect } from "vitest";
import { resolveShares, attributeAmount } from "../attribution";

describe("resolveShares", () => {
  it("returns 1.0 for a single owner with null share", () => {
    expect(resolveShares([{ personId: "a", share: null }])).toEqual({ a: 1 });
  });

  it("splits equally when all shares are null", () => {
    expect(
      resolveShares([
        { personId: "a", share: null },
        { personId: "b", share: null },
        { personId: "c", share: null },
      ])
    ).toEqual({ a: 1 / 3, b: 1 / 3, c: 1 / 3 });
  });

  it("returns explicit shares as-is", () => {
    expect(
      resolveShares([
        { personId: "a", share: 0.6 },
        { personId: "b", share: 0.4 },
      ])
    ).toEqual({ a: 0.6, b: 0.4 });
  });
});

describe("attributeAmount", () => {
  it("attributes 0 when person is not an owner", () => {
    const owners = [{ personId: "a", share: null }];
    expect(attributeAmount(100, owners, "z")).toBe(0);
  });

  it("attributes the full amount to a sole owner", () => {
    const owners = [{ personId: "a", share: null }];
    expect(attributeAmount(100, owners, "a")).toBe(100);
  });

  it("attributes half to each in a 50/50 equal split", () => {
    const owners = [
      { personId: "a", share: null },
      { personId: "b", share: null },
    ];
    expect(attributeAmount(100, owners, "a")).toBe(50);
    expect(attributeAmount(100, owners, "b")).toBe(50);
  });

  it("attributes by explicit share", () => {
    const owners = [
      { personId: "a", share: 0.7 },
      { personId: "b", share: 0.3 },
    ];
    expect(attributeAmount(100, owners, "a")).toBeCloseTo(70);
    expect(attributeAmount(100, owners, "b")).toBeCloseTo(30);
  });

  it("attributes the full amount when querying with null personId (whole household)", () => {
    const owners = [
      { personId: "a", share: 0.6 },
      { personId: "b", share: 0.4 },
    ];
    expect(attributeAmount(100, owners, null)).toBe(100);
  });
});
