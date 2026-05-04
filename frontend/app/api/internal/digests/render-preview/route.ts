import { NextRequest } from "next/server";
import { z } from "zod";
import { render } from "@react-email/render";
import React from "react";
import { verifyInternalRequest, unauthorizedInternal } from "@/lib/internal/verify";
import { routineOutputSchema } from "@/lib/routines/schema";
import { Digest } from "@/emails/digest";

const bodySchema = z.object({
  output: routineOutputSchema,
});

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const auth = verifyInternalRequest(req, "/api/internal/digests/render-preview", rawBody);
  if (!auth.ok) return unauthorizedInternal(auth.reason);

  const { output } = bodySchema.parse(JSON.parse(rawBody));
  const html = await render(React.createElement(Digest, { output }));
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}
