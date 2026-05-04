import { describe, it, expect } from "vitest";
import { validateOwners, ownerInputSchema } from "../validation";

describe("validateOwners", () => {
  it("rejects empty owner lists", () => {
    expect(() => validateOwners([])).toThrow(/at least one owner/i);
  });

  it("accepts a single owner with null share", () => {
    expect(() => validateOwners([{ personId: "p1", share: null }])).not.toThrow();
  });

  it("accepts multiple owners with all-null shares (equal split)", () => {
    expect(() =>
      validateOwners([
        { personId: "p1", share: null },
        { personId: "p2", share: null },
      ])
    ).not.toThrow();
  });

  it("rejects mixed null and explicit shares", () => {
    expect(() =>
      validateOwners([
        { personId: "p1", share: null },
        { personId: "p2", share: 0.5 },
      ])
    ).toThrow(/all owners must either share equally or specify shares/i);
  });

  it("accepts explicit shares summing to 1", () => {
    expect(() =>
      validateOwners([
        { personId: "p1", share: 0.6 },
        { personId: "p2", share: 0.4 },
      ])
    ).not.toThrow();
  });

  it("rejects explicit shares not summing to 1", () => {
    expect(() =>
      validateOwners([
        { personId: "p1", share: 0.6 },
        { personId: "p2", share: 0.3 },
      ])
    ).toThrow(/must sum to 1/i);
  });

  it("rejects shares outside (0, 1]", () => {
    expect(() => validateOwners([{ personId: "p1", share: 0 }])).toThrow();
    expect(() => validateOwners([{ personId: "p1", share: 1.1 }])).toThrow();
  });

  it("rejects duplicate personIds", () => {
    expect(() =>
      validateOwners([
        { personId: "p1", share: 0.5 },
        { personId: "p1", share: 0.5 },
      ])
    ).toThrow(/duplicate/i);
  });
});

describe("ownerInputSchema", () => {
  it("parses string shares to numbers", () => {
    const parsed = ownerInputSchema.parse({
      personId: "00000000-0000-0000-0000-000000000001",
      share: "0.5",
    });
    expect(parsed.share).toBe(0.5);
  });
});
