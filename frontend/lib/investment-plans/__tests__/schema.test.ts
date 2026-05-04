import { describe, it, expect } from "vitest";
import { investmentPlanOutputSchema } from "../schema";

const minimal = {
  totalMonthly: 800,
  currency: "EUR",
  cashSnapshot: [],
  recentActivity: [],
  pinned: [],
  discretionary: [],
  monthlyAction: { proposedBuys: [], idleCashNudge: null, notes: [] },
  evidence: [],
};

describe("investmentPlanOutputSchema", () => {
  it("accepts a minimal valid output", () => {
    expect(() => investmentPlanOutputSchema.parse(minimal)).not.toThrow();
  });

  it("rejects pinned verdict outside enum", () => {
    const bad = { ...minimal, pinned: [{ slotId: "a", symbol: "VUAA", allocatedAmount: 400, verdict: "trash", rationale: "x", riskFlags: [], newsRefs: [] }] };
    expect(() => investmentPlanOutputSchema.parse(bad)).toThrow();
  });

  it("rejects discretionary topPicks without rank", () => {
    const bad = {
      ...minimal,
      discretionary: [{
        slotId: "x", theme: "t", allocatedAmount: 100,
        topPicks: [{ symbol: "AAA", name: "A", suggestedAmount: 100, rationale: "r", riskFlags: [], newsRefs: [] }],
      }],
    };
    expect(() => investmentPlanOutputSchema.parse(bad)).toThrow();
  });

  it("accepts a populated output", () => {
    const ok = {
      ...minimal,
      pinned: [{ slotId: "a", symbol: "VUAA", allocatedAmount: 400, verdict: "keep", rationale: "ok", riskFlags: [], newsRefs: [] }],
      discretionary: [{
        slotId: "b", theme: "clean energy", allocatedAmount: 400,
        topPicks: [{ rank: 1, symbol: "ENPH", name: "Enphase", suggestedAmount: 400, rationale: "growth", riskFlags: [], newsRefs: [0] }],
      }],
      monthlyAction: {
        proposedBuys: [
          { symbol: "VUAA", amount: 400, source: "pinned", slotId: "a" },
          { symbol: "ENPH", amount: 400, source: "discretionary", slotId: "b" },
        ],
        idleCashNudge: "€234 idle in IBKR",
        notes: [],
      },
      evidence: [{ source: "X", url: "https://x.example", quote: "q", relevance: "r" }],
    };
    expect(() => investmentPlanOutputSchema.parse(ok)).not.toThrow();
  });
});
