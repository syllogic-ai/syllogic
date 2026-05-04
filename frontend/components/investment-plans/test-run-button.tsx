"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function TestRunButton({ planId }: { planId: string }) {
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function trigger() {
    setBusy(true);
    try {
      const r = await fetch(`/api/investment-plans/${planId}/test-run`, { method: "POST" });
      if (!r.ok) {
        alert(await r.text());
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button onClick={trigger} disabled={busy}>
      {busy ? "Queued…" : "Run now"}
    </Button>
  );
}
