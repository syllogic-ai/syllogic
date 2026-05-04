import { listPlans } from "@/lib/investment-plans";
import { requireAuth } from "@/lib/auth-helpers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default async function InvestmentPlansPage() {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const rows = await listPlans(userId);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Investment plans</h1>
        <Link href="/investment-plans/new"><Button>New plan</Button></Link>
      </div>

      {rows.length === 0 ? (
        <p className="text-muted-foreground">No plans yet. Create one to get monthly agent-driven recommendations.</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-3 p-4">
              <div className="flex-1">
                <div className="font-medium">{r.name}</div>
                <div className="text-sm text-muted-foreground">
                  {r.scheduleHuman} · {Number(r.totalMonthly).toFixed(0)} {r.currency} / month · next: {r.nextRunAt ? new Date(r.nextRunAt).toLocaleString() : "—"}
                </div>
              </div>
              <span className={`px-2 py-1 rounded-md text-xs ${r.enabled ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
                {r.enabled ? "enabled" : "disabled"}
              </span>
              <Link href={`/investment-plans/${r.id}/runs`}><Button variant="outline" size="sm">Runs</Button></Link>
              <Link href={`/investment-plans/${r.id}/edit`}><Button variant="ghost" size="sm">Edit</Button></Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
