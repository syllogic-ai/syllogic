import { z } from "zod";

const SLOT_TOLERANCE = 0.01;

export const pinnedSlotSchema = z.object({
  id: z.string().min(1),
  kind: z.literal("pinned"),
  symbol: z.string().min(1).transform((s) => s.trim().toUpperCase()),
  amount: z.number().positive(),
  label: z.string().optional(),
});

export const discretionarySlotSchema = z.object({
  id: z.string().min(1),
  kind: z.literal("discretionary"),
  theme: z.string().min(1),
  amount: z.number().positive(),
  label: z.string().optional(),
});

export const slotConfigSchema = z.discriminatedUnion("kind", [pinnedSlotSchema, discretionarySlotSchema]);
export type PinnedSlot = z.infer<typeof pinnedSlotSchema>;
export type DiscretionarySlot = z.infer<typeof discretionarySlotSchema>;
export type SlotConfig = z.infer<typeof slotConfigSchema>;

export function validateSlots(slots: SlotConfig[], totalMonthly: number): void {
  if (slots.length === 0) throw new Error("at least one slot is required");

  const ids = new Set<string>();
  for (const s of slots) {
    if (ids.has(s.id)) throw new Error(`duplicate slot id: ${s.id}`);
    ids.add(s.id);
    if (!(s.amount > 0)) throw new Error(`amount must be > 0; got ${s.amount}`);
    if (s.kind === "pinned" && !s.symbol.trim()) throw new Error("pinned slot requires symbol");
    if (s.kind === "discretionary" && !s.theme.trim()) throw new Error("discretionary slot requires theme");
  }

  const sum = slots.reduce((a, s) => a + s.amount, 0);
  if (Math.abs(sum - totalMonthly) > SLOT_TOLERANCE) {
    throw new Error(`slot amounts sum (${sum.toFixed(2)}) must equal totalMonthly (${totalMonthly.toFixed(2)})`);
  }
}

// ---------- Output schema ----------

export const cashSnapshotItemSchema = z.object({
  accountId: z.string(),
  accountName: z.string(),
  idleCash: z.number(),
  currency: z.string(),
});

export const recentActivityItemSchema = z.object({
  symbol: z.string(),
  netBought: z.number(),
  tradeCount: z.number(),
  asOf: z.string(),
});

export const pinnedResultSchema = z.object({
  slotId: z.string(),
  symbol: z.string(),
  allocatedAmount: z.number(),
  verdict: z.enum(["keep", "reduce", "replace", "monitor"]),
  rationale: z.string(),
  riskFlags: z.array(z.string()).default([]),
  newsRefs: z.array(z.number()).default([]),
  proposedReplacement: z.object({ symbol: z.string(), reason: z.string() }).optional(),
});

export const topPickSchema = z.object({
  rank: z.number(),
  symbol: z.string(),
  name: z.string(),
  suggestedAmount: z.number(),
  rationale: z.string(),
  riskFlags: z.array(z.string()).default([]),
  newsRefs: z.array(z.number()).default([]),
});

export const discretionaryResultSchema = z.object({
  slotId: z.string(),
  theme: z.string(),
  allocatedAmount: z.number(),
  topPicks: z.array(topPickSchema),
});

export const proposedBuySchema = z.object({
  symbol: z.string(),
  amount: z.number(),
  source: z.enum(["pinned", "discretionary"]),
  slotId: z.string(),
});

export const monthlyActionSchema = z.object({
  proposedBuys: z.array(proposedBuySchema),
  idleCashNudge: z.string().nullable(),
  notes: z.array(z.string()).default([]),
});

export const evidenceItemSchema = z.object({
  source: z.string(),
  url: z.string().url(),
  quote: z.string(),
  relevance: z.string(),
});

export const investmentPlanOutputSchema = z.object({
  totalMonthly: z.number(),
  currency: z.string(),
  cashSnapshot: z.array(cashSnapshotItemSchema).default([]),
  recentActivity: z.array(recentActivityItemSchema).default([]),
  pinned: z.array(pinnedResultSchema).default([]),
  discretionary: z.array(discretionaryResultSchema).default([]),
  monthlyAction: monthlyActionSchema,
  evidence: z.array(evidenceItemSchema).default([]),
  flags: z.record(z.boolean()).default({}),
});

export type InvestmentPlanOutput = z.infer<typeof investmentPlanOutputSchema>;
