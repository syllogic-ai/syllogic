"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function TestRunButton({ routineId }: { routineId: string }) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleTestRun() {
    setRunning(true);
    setError(null);
    try {
      const r = await fetch(`/api/routines/${routineId}/test-run`, {
        method: "POST",
      });
      if (!r.ok) {
        setError(await r.text());
        return;
      }
      router.refresh();
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button type="button" onClick={handleTestRun} disabled={running}>
        {running ? "Running…" : "Test run"}
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
