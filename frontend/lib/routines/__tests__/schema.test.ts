import { describe, it, expect } from "vitest";
import { routineOutputSchema } from "../schema";

const valid = {
  status: "GREEN",
  confidence: "high",
  headline: "Stay the course",
  summary: "Strategy on track.",
  evidence: [],
  household: { people: [] },
  positions: [],
  news: [],
  recommendations: [],
};

describe("routineOutputSchema", () => {
  it("accepts a minimal valid output", () => {
    expect(() => routineOutputSchema.parse(valid)).not.toThrow();
  });

  it("rejects an invalid status", () => {
    expect(() => routineOutputSchema.parse({ ...valid, status: "MAGENTA" })).toThrow();
  });

  it("allows negative person totals (credit-card debt is real)", () => {
    const bad = {
      ...valid,
      household: { people: [{ personId: "x", name: "X", cash: -1, investments: 0, properties: 0, vehicles: 0, total: -1 }] },
    };
    expect(() => routineOutputSchema.parse(bad)).not.toThrow();
  });
});
