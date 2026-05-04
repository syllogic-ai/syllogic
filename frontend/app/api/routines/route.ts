import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { listRoutines, createRoutine } from "@/lib/routines";

const createSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().nullable().optional(),
  prompt: z.string().min(1),
  cron: z.string().min(1).max(100),
  timezone: z.string().min(1).max(64),
  scheduleHuman: z.string().min(1),
  recipientEmail: z.string().email(),
  model: z.string().optional(),
  enabled: z.boolean().optional(),
});

export async function GET() {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const rows = await listRoutines(userId);
  return NextResponse.json({ routines: rows });
}

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  const row = await createRoutine(userId, parsed.data);
  return NextResponse.json({ routine: row }, { status: 201 });
}
