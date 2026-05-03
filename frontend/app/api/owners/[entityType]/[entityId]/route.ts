import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getOwners, setOwners, type EntityType } from "@/lib/people";
import { requireAuth } from "@/lib/auth-helpers";

const ENTITY_TYPES = ["account", "property", "vehicle"] as const;

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ entityType: string; entityId: string }> }
) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { entityType, entityId } = await ctx.params;
  if (!ENTITY_TYPES.includes(entityType as EntityType)) {
    return NextResponse.json({ error: "invalid entityType" }, { status: 400 });
  }
  const owners = await getOwners(entityType as EntityType, entityId);
  return NextResponse.json({ owners });
}

const putSchema = z.object({
  owners: z
    .array(
      z.object({
        personId: z.string().uuid(),
        share: z.number().nullable(),
      })
    )
    .min(1),
});

export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ entityType: string; entityId: string }> }
) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { entityType, entityId } = await ctx.params;
  if (!ENTITY_TYPES.includes(entityType as EntityType)) {
    return NextResponse.json({ error: "invalid entityType" }, { status: 400 });
  }
  const body = putSchema.parse(await req.json());
  try {
    await setOwners({
      userId,
      entityType: entityType as EntityType,
      entityId,
      owners: body.owners,
    });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
}
