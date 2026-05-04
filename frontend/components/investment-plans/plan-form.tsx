"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ScheduleField, type ScheduleValue } from "@/components/routines/schedule-field";
import { SlotEditor } from "./slot-editor";
import type { SlotConfig } from "@/lib/investment-plans/schema";

const MODELS = [
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6 (recommended)" },
  { id: "claude-opus-4-7", label: "Opus 4.7 (most capable, ~5x cost)" },
];

export type PlanFormValues = {
  name: string;
  description: string;
  totalMonthly: number;
  currency: string;
  slots: SlotConfig[];
  schedule: ScheduleValue;
  recipientEmail: string;
  model: string;
  enabled: boolean;
};

export function PlanForm(props: {
  initial?: Partial<PlanFormValues>;
  planId?: string;
}) {
  const router = useRouter();
  const [v, setV] = useState<PlanFormValues>({
    name: props.initial?.name ?? "",
    description: props.initial?.description ?? "",
    totalMonthly: props.initial?.totalMonthly ?? 800,
    currency: props.initial?.currency ?? "EUR",
    slots: props.initial?.slots ?? [],
    schedule: props.initial?.schedule ?? { cron: "0 8 1 * *", timezone: "UTC", humanReadable: "1st of every month at 8:00 (UTC)" },
    recipientEmail: props.initial?.recipientEmail ?? "",
    model: props.initial?.model ?? "claude-sonnet-4-6",
    enabled: props.initial?.enabled ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const body = {
        name: v.name,
        description: v.description || null,
        totalMonthly: v.totalMonthly,
        currency: v.currency,
        slots: v.slots,
        cron: v.schedule.cron,
        timezone: v.schedule.timezone,
        scheduleHuman: v.schedule.humanReadable,
        recipientEmail: v.recipientEmail || null,
        model: v.model,
        enabled: v.enabled,
      };
      const url = props.planId ? `/api/investment-plans/${props.planId}` : "/api/investment-plans";
      const method = props.planId ? "PATCH" : "POST";
      const r = await fetch(url, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) { setError(await r.text()); return; }
      const j = await r.json();
      router.push(`/investment-plans/${j.plan.id}/runs`);
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="space-y-5 max-w-2xl">
      <div>
        <Label>Name</Label>
        <Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} required maxLength={255} />
      </div>
      <div>
        <Label>Description (optional)</Label>
        <Input value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <Label>Total monthly</Label>
          <Input type="number" min={0} step={1} value={v.totalMonthly}
                 onChange={(e) => setV({ ...v, totalMonthly: Number(e.target.value) })} required />
        </div>
        <div className="w-24">
          <Label>Currency</Label>
          <Input value={v.currency} onChange={(e) => setV({ ...v, currency: e.target.value.toUpperCase().slice(0, 3) })} />
        </div>
      </div>
      <div>
        <Label>Slots</Label>
        <SlotEditor value={v.slots} onChange={(slots) => setV({ ...v, slots })}
                    totalMonthly={v.totalMonthly} currency={v.currency} />
      </div>
      <div>
        <Label>Schedule</Label>
        <ScheduleField value={v.schedule} onChange={(schedule) => setV({ ...v, schedule })} />
      </div>
      <div>
        <Label>Recipient email (optional — leave blank for in-app only)</Label>
        <Input type="email" value={v.recipientEmail}
               onChange={(e) => setV({ ...v, recipientEmail: e.target.value })} />
      </div>
      <div>
        <Label>Model</Label>
        <select className="block w-full rounded-md border px-3 py-2 text-sm"
                value={v.model} onChange={(e) => setV({ ...v, model: e.target.value })}>
          {MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <input id="enabled" type="checkbox" checked={v.enabled}
               onChange={(e) => setV({ ...v, enabled: e.target.checked })} />
        <Label htmlFor="enabled" className="font-normal">Enabled</Label>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : props.planId ? "Save" : "Create plan"}
        </Button>
      </div>
    </form>
  );
}
