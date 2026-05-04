import { getPlan } from "@/lib/investment-plans";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import { PlanForm } from "@/components/investment-plans/plan-form";
import type { SlotConfig } from "@/lib/investment-plans/schema";

export default async function EditPlanPage({ params }: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id } = await params;
  const r = await getPlan(userId, id);
  if (!r) notFound();
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Edit investment plan</h1>
      <PlanForm
        planId={r.id}
        initial={{
          name: r.name,
          description: r.description ?? "",
          totalMonthly: Number(r.totalMonthly),
          currency: r.currency,
          slots: (r.slots as SlotConfig[]) ?? [],
          schedule: { cron: r.cron, timezone: r.timezone, humanReadable: r.scheduleHuman },
          recipientEmail: r.recipientEmail ?? "",
          model: r.model,
          enabled: r.enabled,
        }}
      />
    </div>
  );
}
