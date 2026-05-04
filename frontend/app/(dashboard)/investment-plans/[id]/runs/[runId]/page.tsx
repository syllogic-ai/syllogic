import { getPlan, getPlanRun } from "@/lib/investment-plans";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import { investmentPlanOutputSchema } from "@/lib/investment-plans/schema";
import { ProposedBuysCard } from "@/components/investment-plans/proposed-buys-card";

export default async function PlanRunDetailPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id, runId } = await params;

  const [plan, run] = await Promise.all([
    getPlan(userId, id),
    getPlanRun(userId, runId),
  ]);
  if (!plan || !run) notFound();
  if (run.planId !== id) notFound();

  let output: ReturnType<typeof investmentPlanOutputSchema.parse> | null = null;
  let parseError: string | null = null;
  if (run.output) {
    const result = investmentPlanOutputSchema.safeParse(run.output);
    if (result.success) {
      output = result.data;
    } else {
      parseError = result.error.message;
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold">Run · {plan.name}</h1>
        <p className="text-sm text-muted-foreground">
          {run.startedAt ? new Date(run.startedAt).toLocaleString() : ""} ·
          status {run.status} · cost $
          {((run.costCents ?? 0) / 100).toFixed(2)}
        </p>
        {run.errorMessage && (
          <p className="text-sm text-destructive mt-1 whitespace-pre-wrap">
            {run.errorMessage}
          </p>
        )}
        {parseError && (
          <p className="text-sm text-destructive mt-1">
            Output failed schema validation: {parseError}
          </p>
        )}
      </header>

      {output && (
        <>
          <ProposedBuysCard
            output={output}
            planId={id}
            runId={runId}
            initialMarks={
              (run.executionMarks as Record<
                string,
                { executedAt: string | null; note?: string }
              >) ?? {}
            }
          />

          {output.monthlyAction.idleCashNudge && (
            <section className="border-l-4 border-amber-400 bg-amber-50 p-3 rounded-r-md">
              <div className="font-medium">Idle cash</div>
              <div className="text-sm">{output.monthlyAction.idleCashNudge}</div>
              {output.cashSnapshot.length > 0 && (
                <ul className="text-xs text-muted-foreground mt-2">
                  {output.cashSnapshot.map((c) => (
                    <li key={c.accountId}>
                      {c.accountName}: {c.idleCash.toFixed(2)} {c.currency}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {output.pinned.length > 0 && (
            <section>
              <h2 className="font-semibold mb-3">Pinned slots</h2>
              <div className="space-y-3">
                {output.pinned.map((p) => (
                  <div key={p.slotId} className="border rounded-md p-3">
                    <div className="flex items-center gap-2">
                      <div className="font-medium">{p.symbol}</div>
                      <span className="px-2 py-0.5 rounded-md text-xs bg-muted">
                        {p.allocatedAmount.toFixed(2)} {output!.currency}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-md text-xs ${
                          p.verdict === "keep"
                            ? "bg-green-100 text-green-800"
                            : p.verdict === "monitor"
                              ? "bg-blue-100 text-blue-800"
                              : p.verdict === "reduce"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                        }`}
                      >
                        {p.verdict}
                      </span>
                    </div>
                    <p className="text-sm mt-2">{p.rationale}</p>
                    {p.riskFlags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {p.riskFlags.map((f, i) => (
                          <span
                            key={i}
                            className="text-xs px-2 py-0.5 rounded-md bg-amber-100 text-amber-900"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {output.discretionary.length > 0 && (
            <section>
              <h2 className="font-semibold mb-3">Discretionary slots</h2>
              <div className="space-y-4">
                {output.discretionary.map((d) => (
                  <div key={d.slotId} className="border rounded-md p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="font-medium">{d.theme}</div>
                      <span className="px-2 py-0.5 rounded-md text-xs bg-muted">
                        {d.allocatedAmount.toFixed(2)} {output!.currency}
                      </span>
                    </div>
                    <ol className="space-y-2 text-sm">
                      {d.topPicks.map((pk) => (
                        <li
                          key={pk.rank}
                          className="border-l-2 pl-3 py-1"
                          style={{
                            borderColor: pk.rank === 1 ? "#10B981" : "#ddd",
                          }}
                        >
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs">#{pk.rank}</span>
                            <span className="font-medium">{pk.symbol}</span>
                            <span className="text-muted-foreground">
                              {pk.name}
                            </span>
                            {pk.rank === 1 && (
                              <span className="text-xs px-2 py-0.5 rounded-md bg-green-100 text-green-800">
                                Suggested for this month
                              </span>
                            )}
                          </div>
                          <p className="text-sm mt-1">{pk.rationale}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            </section>
          )}

          {output.monthlyAction.notes.length > 0 && (
            <section>
              <h2 className="font-semibold mb-2">Notes</h2>
              <ul className="list-disc pl-5 text-sm space-y-1">
                {output.monthlyAction.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}

          {output.evidence.length > 0 && (
            <section>
              <h2 className="font-semibold mb-2">Evidence</h2>
              <ol className="text-sm space-y-2 pl-5 list-decimal">
                {output.evidence.map((e, i) => (
                  <li key={i}>
                    <a href={e.url} className="font-medium underline">
                      {e.source}
                    </a>
                    <div className="italic text-muted-foreground">
                      &quot;{e.quote}&quot;
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {e.relevance}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </>
      )}
    </div>
  );
}
