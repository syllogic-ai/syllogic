"use client";

import { useState } from "react";
import type { InvestmentPlanOutput } from "@/lib/investment-plans/schema";

type ExecutionMarks = Record<string, { executedAt: string | null; note?: string }>;

export function ProposedBuysCard({
  output,
  planId,
  runId,
  initialMarks,
}: {
  output: InvestmentPlanOutput;
  planId: string;
  runId: string;
  initialMarks: ExecutionMarks;
}) {
  const [marks, setMarks] = useState<ExecutionMarks>(initialMarks);

  async function toggle(slotId: string) {
    const wasExecuted = !!marks[slotId]?.executedAt;
    const now = new Date().toISOString();
    const prevMarks = marks;
    setMarks((prev) => {
      const next = { ...prev };
      if (wasExecuted) {
        delete next[slotId];
      } else {
        next[slotId] = { executedAt: now };
      }
      return next;
    });
    try {
      const r = await fetch(
        `/api/investment-plans/${planId}/runs/${runId}/execution-marks`,
        {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            slotId,
            executedAt: wasExecuted ? null : now,
          }),
        }
      );
      if (!r.ok) throw new Error(await r.text());
    } catch (e) {
      // Revert optimistic update.
      setMarks(prevMarks);
      alert(`Failed to update execution mark: ${e instanceof Error ? e.message : "unknown error"}`);
    }
  }

  const total = output.monthlyAction.proposedBuys.reduce(
    (a, b) => a + b.amount,
    0
  );

  return (
    <section className="border rounded-md p-4 bg-muted/30">
      <h2 className="font-semibold mb-3">This month's suggested buys</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">Symbol</th>
            <th>Amount</th>
            <th>Source</th>
            <th>Executed?</th>
          </tr>
        </thead>
        <tbody>
          {output.monthlyAction.proposedBuys.map((b) => {
            const executed = !!marks[b.slotId]?.executedAt;
            return (
              <tr key={b.slotId} className="border-b last:border-b-0">
                <td className="py-2 font-medium">{b.symbol}</td>
                <td>
                  {b.amount.toFixed(2)} {output.currency}
                </td>
                <td className="text-muted-foreground">{b.source}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={executed}
                    onChange={() => toggle(b.slotId)}
                  />
                  {executed && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {new Date(
                        marks[b.slotId]!.executedAt!
                      ).toLocaleDateString()}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="font-medium">
            <td className="py-2">Total</td>
            <td>
              {total.toFixed(2)} {output.currency}
            </td>
            <td colSpan={2}></td>
          </tr>
        </tfoot>
      </table>
    </section>
  );
}
