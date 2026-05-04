import { requireAuth } from "@/lib/auth-helpers";
import { redirect } from "next/navigation";
import { RoutineForm } from "@/components/routines/routine-form";
import { INVESTMENT_REVIEW_TEMPLATE } from "@/lib/routines";

export default async function NewRoutinePage() {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">New routine</h1>
      <RoutineForm
        initial={{
          name: INVESTMENT_REVIEW_TEMPLATE.name,
          description: INVESTMENT_REVIEW_TEMPLATE.description,
          prompt: INVESTMENT_REVIEW_TEMPLATE.prompt,
          schedule: {
            cron: INVESTMENT_REVIEW_TEMPLATE.cron,
            timezone: INVESTMENT_REVIEW_TEMPLATE.timezone,
            humanReadable: INVESTMENT_REVIEW_TEMPLATE.scheduleHuman,
          },
        }}
      />
    </div>
  );
}
