import { listPlanRuns, getPlan } from "@/lib/investment-plans";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { TestRunButton } from "@/components/investment-plans/test-run-button";

export default async function PlanRunsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id } = await params;
  const plan = await getPlan(userId, id);
  if (!plan) notFound();
  const runs = await listPlanRuns(userId, id);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{plan.name} — runs</h1>
          <p className="text-sm text-muted-foreground">{plan.scheduleHuman}</p>
        </div>
        <TestRunButton planId={id} />
      </div>

      {runs.length === 0 ? (
        <p className="text-muted-foreground">
          No runs yet. Click &quot;Run now&quot; to trigger one.
        </p>
      ) : (
        <ul className="divide-y rounded-md border">
          {runs.map((r) => {
            const output = r.output as {
              monthlyAction?: { proposedBuys?: unknown[] };
            } | null;
            const buyCount = output?.monthlyAction?.proposedBuys?.length ?? 0;
            const headline = buyCount
              ? `${buyCount} suggested buys`
              : "(no output)";
            return (
              <li key={r.id} className="flex items-center gap-3 p-4">
                <div className="flex-1">
                  <div className="font-medium">{headline}</div>
                  <div className="text-sm text-muted-foreground">
                    {r.createdAt
                      ? new Date(r.createdAt).toLocaleString()
                      : ""}{" "}
                    · cost ${((r.costCents ?? 0) / 100).toFixed(2)}
                  </div>
                </div>
                <span
                  className={`px-2 py-1 rounded-md text-xs ${
                    r.status === "sent"
                      ? "bg-green-100 text-green-800"
                      : r.status === "succeeded"
                        ? "bg-blue-100 text-blue-800"
                        : r.status === "failed"
                          ? "bg-red-100 text-red-800"
                          : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {r.status}
                </span>
                <Link href={`/investment-plans/${id}/runs/${r.id}`}>
                  <Button variant="outline" size="sm">
                    Open
                  </Button>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
