import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { Resend } from "resend";
import React from "react";
import { verifyInternalRequest, unauthorizedInternal } from "@/lib/internal/verify";
import { routineOutputSchema } from "@/lib/routines/schema";
import { getRoutine } from "@/lib/routines";
import { Digest } from "@/emails/digest";

const bodySchema = z.object({
  routineId: z.string().uuid(),
  runId: z.string().uuid(),
  output: routineOutputSchema,
});

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const auth = verifyInternalRequest(req, "/api/internal/digests/render-and-send", rawBody);
  if (!auth.ok) return unauthorizedInternal(auth.reason);

  const body = bodySchema.parse(JSON.parse(rawBody));
  const routine = await getRoutine(auth.userId, body.routineId);
  if (!routine) return NextResponse.json({ error: "routine not found" }, { status: 404 });

  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM_EMAIL;
  if (!apiKey || !from) {
    return NextResponse.json(
      { error: "Resend not configured (RESEND_API_KEY / RESEND_FROM_EMAIL)" },
      { status: 503 },
    );
  }
  const resend = new Resend(apiKey);

  const emoji = body.output.status === "GREEN" ? "🟢" : body.output.status === "AMBER" ? "🟡" : "🔴";
  const subject = `[${emoji}] ${body.output.headline}`;
  const appUrl = process.env.APP_URL ?? "";
  const runUrl = appUrl
    ? `${appUrl}/routines/${body.routineId}/runs/${body.runId}`
    : undefined;

  const { data, error } = await resend.emails.send({
    from,
    to: routine.recipientEmail,
    subject,
    react: React.createElement(Digest, { output: body.output, runUrl }),
  });

  if (error) {
    return NextResponse.json({ error: String((error as { message?: string }).message ?? error) }, { status: 502 });
  }

  return NextResponse.json({ messageId: data?.id ?? null });
}
