import { getRoutine } from "@/lib/routines";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import { RoutineForm } from "@/components/routines/routine-form";

export default async function EditRoutinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id } = await params;
  const r = await getRoutine(userId, id);
  if (!r) notFound();
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Edit routine</h1>
      <RoutineForm
        routineId={r.id}
        initial={{
          name: r.name,
          description: r.description ?? "",
          prompt: r.prompt,
          schedule: {
            cron: r.cron,
            timezone: r.timezone,
            humanReadable: r.scheduleHuman,
          },
          recipientEmail: r.recipientEmail,
          model: r.model,
          enabled: r.enabled,
        }}
      />
    </div>
  );
}
