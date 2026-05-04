import { NextRequest } from "next/server";
import { z } from "zod";
import { render } from "@react-email/render";
import { verifyInternalRequest, unauthorizedInternal } from "@/lib/internal/verify";
import { investmentPlanOutputSchema } from "@/lib/investment-plans/schema";
import { InvestmentPlanMonthly } from "@/emails/investment-plan-monthly";
import React from "react";

const bodySchema = z.object({ output: investmentPlanOutputSchema });

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
  const rawBody = await req.text();
  const auth = verifyInternalRequest(req, "/api/internal/digests/render-preview-plan", rawBody);
  if (!auth.ok) return unauthorizedInternal(auth.reason);
  const { output } = bodySchema.parse(JSON.parse(rawBody));
  const now = new Date();
  const monthLabel = `${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
  const html = await render(
    React.createElement(InvestmentPlanMonthly, { output, monthLabel }),
  );
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}
