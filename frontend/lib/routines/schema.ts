import { z } from "zod";

export const evidenceItemSchema = z.object({
  source: z.string().min(1),
  url: z.string().url(),
  quote: z.string().min(1),
  relevance: z.string().min(1),
});

export const householdPersonSchema = z.object({
  personId: z.string(),
  name: z.string(),
  cash: z.number(),
  investments: z.number(),
  properties: z.number(),
  vehicles: z.number(),
  total: z.number(),
});

export const positionRowSchema = z.object({
  label: z.string(),
  current: z.number(),
  target: z.number().nullable(),
  deltaPct: z.number().nullable(),
  note: z.string().nullable(),
});

export const newsItemSchema = z.object({
  title: z.string(),
  source: z.string(),
  url: z.string().url(),
  dateIso: z.string(),
  summary: z.string(),
});

export const recommendationSchema = z.object({
  severity: z.enum(["info", "monitor", "act_now"]),
  title: z.string(),
  rationale: z.string(),
  proposedChange: z.string().nullable(),
});

export const routineOutputSchema = z.object({
  status: z.enum(["GREEN", "AMBER", "RED"]),
  confidence: z.enum(["low", "medium", "high"]),
  headline: z.string(),
  summary: z.string(),
  evidence: z.array(evidenceItemSchema).default([]),
  household: z.object({ people: z.array(householdPersonSchema) }),
  positions: z.array(positionRowSchema).default([]),
  news: z.array(newsItemSchema).default([]),
  recommendations: z.array(recommendationSchema).default([]),
  flags: z.record(z.boolean()).default({}),
});

export type RoutineOutput = z.infer<typeof routineOutputSchema>;

export const parseScheduleResponseSchema = z.object({
  cron: z.string().min(1),
  timezone: z.string().min(1),
  humanReadable: z.string().min(1),
});
export type ParseScheduleResponse = z.infer<typeof parseScheduleResponseSchema>;
