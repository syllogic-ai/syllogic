import { describe, it, expect } from "vitest";
import { validateSlots } from "../schema";

const pinnedA = { id: "a", kind: "pinned" as const, symbol: "VUAA", amount: 400 };
const pinnedB = { id: "b", kind: "pinned" as const, symbol: "VWCE", amount: 200 };
const discC = { id: "c", kind: "discretionary" as const, theme: "clean energy", amount: 200 };

describe("validateSlots", () => {
  it("rejects empty list", () => {
    expect(() => validateSlots([], 100)).toThrow(/at least one slot/i);
  });

  it("rejects amount <= 0", () => {
    expect(() => validateSlots([{ ...pinnedA, amount: 0 }], 0)).toThrow(/amount must be > 0/i);
  });

  it("rejects pinned without symbol", () => {
    expect(() => validateSlots([{ id: "x", kind: "pinned" as any, symbol: "", amount: 100 }], 100)).toThrow(/symbol/i);
  });

  it("rejects discretionary without theme", () => {
    expect(() => validateSlots([{ id: "x", kind: "discretionary" as any, theme: "", amount: 100 }], 100)).toThrow(/theme/i);
  });

  it("rejects duplicate slot ids", () => {
    expect(() => validateSlots([{ ...pinnedA }, { ...pinnedA }], 800)).toThrow(/duplicate/i);
  });

  it("rejects sum != total", () => {
    expect(() => validateSlots([pinnedA, pinnedB], 700)).toThrow(/sum/i);
  });

  it("accepts a valid config (sum equals total)", () => {
    expect(() => validateSlots([pinnedA, discC], 600)).not.toThrow();
  });

  it("accepts sum within €0.01 tolerance", () => {
    expect(() => validateSlots([{ ...pinnedA, amount: 400.001 }], 400)).not.toThrow();
  });
});
