import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getPeople, createPerson, updatePerson } from "@/lib/people";
import { uploadPersonAvatar, avatarUrl } from "@/lib/people/avatars";
import { requireAuth } from "@/lib/auth-helpers";

export async function GET() {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const rows = await getPeople(userId);
  return NextResponse.json({
    people: rows.map((p) => ({ ...p, avatarUrl: avatarUrl(p.avatarPath) })),
  });
}

const createSchema = z.object({
  name: z.string().min(1).max(255),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{6}$/)
    .optional(),
});

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const form = await req.formData();
  const parsed = createSchema.safeParse({
    name: form.get("name"),
    color: form.get("color") || undefined,
  });
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  // Insert first so we have an id for the avatar filename.
  const person = await createPerson({ userId, ...parsed.data });
  const avatar = form.get("avatar");
  if (avatar instanceof File && avatar.size > 0) {
    const path = await uploadPersonAvatar(person.id, avatar);
    const updated = await updatePerson({ userId, id: person.id, avatarPath: path });
    return NextResponse.json(
      { person: { ...updated, avatarUrl: avatarUrl(path) } },
      { status: 201 }
    );
  }
  return NextResponse.json({ person: { ...person, avatarUrl: null } }, { status: 201 });
}
