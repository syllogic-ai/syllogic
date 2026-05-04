import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { updatePerson, deletePerson, getPeople } from "@/lib/people";
import { uploadPersonAvatar, deletePersonAvatar, avatarUrl } from "@/lib/people/avatars";
import { requireAuth } from "@/lib/auth-helpers";

const patchSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{6}$/)
    .optional(),
  // "1" means "clear avatar", missing means "leave unchanged"
  clearAvatar: z.string().optional(),
});

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const form = await req.formData();
  const parsed = patchSchema.safeParse({
    name: form.get("name") || undefined,
    color: form.get("color") || undefined,
    clearAvatar: form.get("clearAvatar") || undefined,
  });
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }

  // Look up current avatar path for cleanup decisions.
  const all = await getPeople(userId);
  const existing = all.find((p) => p.id === id);
  if (!existing) return NextResponse.json({ error: "not found" }, { status: 404 });

  let newAvatarPath: string | null | undefined = undefined;
  let oldAvatarPathToDelete: string | null = null;

  const avatar = form.get("avatar");
  if (avatar instanceof File && avatar.size > 0) {
    newAvatarPath = await uploadPersonAvatar(id, avatar);
    if (existing.avatarPath && existing.avatarPath !== newAvatarPath) {
      oldAvatarPathToDelete = existing.avatarPath;
    }
  } else if (parsed.data.clearAvatar === "1") {
    newAvatarPath = null;
    if (existing.avatarPath) oldAvatarPathToDelete = existing.avatarPath;
  }

  const updated = await updatePerson({
    userId,
    id,
    name: parsed.data.name,
    color: parsed.data.color,
    avatarPath: newAvatarPath,
  });

  // Only after DB update succeeds, delete the orphaned blob.
  if (oldAvatarPathToDelete) {
    await deletePersonAvatar(oldAvatarPathToDelete);
  }

  return NextResponse.json({
    person: { ...updated, avatarUrl: avatarUrl(updated.avatarPath) },
  });
}

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  try {
    // Capture the avatar path before deletion to clean up.
    const all = await getPeople(userId);
    const existing = all.find((p) => p.id === id);
    await deletePerson({ userId, id });
    if (existing?.avatarPath) await deletePersonAvatar(existing.avatarPath);
    return NextResponse.json({ ok: true });
  } catch (e) {
    const code = (e as any).code;
    if (code === "SOLE_OWNER") {
      return NextResponse.json(
        { error: (e as Error).message, blockers: (e as any).blockers },
        { status: 409 }
      );
    }
    throw e;
  }
}
