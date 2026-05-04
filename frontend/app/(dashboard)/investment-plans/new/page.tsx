import { requireAuth } from "@/lib/auth-helpers";
import { redirect } from "next/navigation";
import { PlanForm } from "@/components/investment-plans/plan-form";

export default async function NewPlanPage() {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">New investment plan</h1>
      <PlanForm />
    </div>
  );
}
