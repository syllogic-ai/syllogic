import { listRuns, getRoutine } from "@/lib/routines";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { TestRunButton } from "@/components/routines/test-run-button";

export default async function RunsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id } = await params;
  const routine = await getRoutine(userId, id);
  if (!routine) notFound();
  const runs = await listRuns(userId, id);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{routine.name} — runs</h1>
          <p className="text-sm text-muted-foreground">{routine.scheduleHuman}</p>
        </div>
        <TestRunButton routineId={id} />
      </div>

      {runs.length === 0 ? (
        <p className="text-muted-foreground">
          No runs yet. Click &quot;Test run&quot; to trigger one now.
        </p>
      ) : (
        <ul className="divide-y rounded-md border">
          {runs.map((r) => (
            <li key={r.id} className="flex items-center gap-3 p-4">
              <div className="flex-1">
                <div className="font-medium">
                  {(r.output as { headline?: string } | null)?.headline ?? "(no headline)"}
                </div>
                <div className="text-sm text-muted-foreground">
                  {r.createdAt ? new Date(r.createdAt).toLocaleString() : ""} · cost $
                  {((r.costCents ?? 0) / 100).toFixed(2)}
                </div>
              </div>
              <span
                className={`px-2 py-1 rounded-md text-xs ${
                  r.status === "sent"
                    ? "bg-green-100 text-green-800"
                    : r.status === "failed"
                    ? "bg-red-100 text-red-800"
                    : "bg-blue-100 text-blue-800"
                }`}
              >
                {r.status}
              </span>
              <Link href={`/routines/${id}/runs/${r.id}`}>
                <Button variant="outline" size="sm">
                  Open
                </Button>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
