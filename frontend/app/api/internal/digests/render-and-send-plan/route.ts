import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { Resend } from "resend";
import { verifyInternalRequest, unauthorizedInternal } from "@/lib/internal/verify";
import { investmentPlanOutputSchema } from "@/lib/investment-plans/schema";
import { InvestmentPlanMonthly } from "@/emails/investment-plan-monthly";
import React from "react";

const bodySchema = z.object({
  planId: z.string().uuid(),
  runId: z.string().uuid(),
  recipientEmail: z.string().email(),
  output: investmentPlanOutputSchema,
});

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export async function POST(req: NextRequest) {
  const auth = verifyInternalRequest(req, "/api/internal/digests/render-and-send-plan");
  if (!auth.ok) return unauthorizedInternal(auth.reason);

  const body = bodySchema.parse(await req.json());

  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM_EMAIL;
  if (!apiKey || !from) {
    return NextResponse.json({ error: "Resend not configured" }, { status: 503 });
  }
  const resend = new Resend(apiKey);

  const now = new Date();
  const monthLabel = `${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
  const buyCount = body.output.monthlyAction.proposedBuys.length;
  const subject = `[Investment plan] ${buyCount} suggested ${buyCount === 1 ? "buy" : "buys"} for ${monthLabel}`;
  const appUrl = process.env.APP_URL ?? "";
  const runUrl = appUrl
    ? `${appUrl}/investment-plans/${body.planId}/runs/${body.runId}`
    : undefined;

  const { data, error } = await resend.emails.send({
    from,
    to: body.recipientEmail,
    subject,
    react: React.createElement(InvestmentPlanMonthly, {
      output: body.output,
      runUrl,
      monthLabel,
    }),
  });
  if (error) return NextResponse.json({ error: String(error.message ?? error) }, { status: 502 });
  return NextResponse.json({ messageId: data?.id ?? null });
}
