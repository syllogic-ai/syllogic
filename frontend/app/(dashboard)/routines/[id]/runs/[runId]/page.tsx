import { getRun, getRoutine } from "@/lib/routines";
import { requireAuth } from "@/lib/auth-helpers";
import { notFound, redirect } from "next/navigation";
import { render } from "@react-email/render";
import { Digest } from "@/emails/digest";
import { routineOutputSchema } from "@/lib/routines";
import React from "react";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const userId = await requireAuth();
  if (!userId) redirect("/login");
  const { id, runId } = await params;
  const routine = await getRoutine(userId, id);
  const run = await getRun(userId, runId);
  if (!routine || !run) notFound();
  if (run.routineId !== id) notFound();

  let html = "";
  let parsed = null;
  if (run.output) {
    try {
      parsed = routineOutputSchema.parse(run.output);
      html = await render(React.createElement(Digest, { output: parsed }));
    } catch (e) {
      html = `<pre>output failed schema validation: ${(e as Error).message}</pre>`;
    }
  }

  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Run · {routine.name}</h1>
        <p className="text-sm text-muted-foreground">
          {run.startedAt ? new Date(run.startedAt).toLocaleString() : ""} · status{" "}
          {run.status} · cost ${((run.costCents ?? 0) / 100).toFixed(2)}
        </p>
        {run.errorMessage && (
          <p className="text-sm text-destructive mt-1">{run.errorMessage}</p>
        )}
      </header>

      <section>
        <h2 className="font-medium mb-2">Email preview</h2>
        <iframe
          className="w-full h-[900px] border rounded-md bg-white"
          srcDoc={html || "<p>No output yet.</p>"}
          title="Email preview"
        />
      </section>

      <section>
        <h2 className="font-medium mb-2">Structured output (JSON)</h2>
        <pre className="text-xs overflow-auto bg-muted p-3 rounded-md max-h-[400px]">
          {JSON.stringify(run.output, null, 2)}
        </pre>
      </section>

      <section>
        <h2 className="font-medium mb-2">Transcript</h2>
        <pre className="text-xs overflow-auto bg-muted p-3 rounded-md max-h-[300px]">
          {JSON.stringify(run.transcript, null, 2)}
        </pre>
      </section>
    </div>
  );
}
