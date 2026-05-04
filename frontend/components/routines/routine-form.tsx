"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScheduleField, type ScheduleValue } from "./schedule-field";

export type RoutineFormValues = {
  name: string;
  description: string;
  prompt: string;
  schedule: ScheduleValue;
  recipientEmail: string;
  model: string;
  enabled: boolean;
};

const MODELS = [
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6 (recommended)" },
  { id: "claude-opus-4-7", label: "Opus 4.7 (most capable, ~5x cost)" },
];

export function RoutineForm(props: {
  initial?: Partial<RoutineFormValues>;
  routineId?: string;
}) {
  const router = useRouter();
  const [values, setValues] = useState<RoutineFormValues>({
    name: props.initial?.name ?? "",
    description: props.initial?.description ?? "",
    prompt: props.initial?.prompt ?? "",
    schedule: props.initial?.schedule ?? {
      cron: "0 8 * * 1",
      timezone: "UTC",
      humanReadable: "Every Monday at 8:00 (UTC)",
    },
    recipientEmail: props.initial?.recipientEmail ?? "",
    model: props.initial?.model ?? "claude-sonnet-4-6",
    enabled: props.initial?.enabled ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: values.name,
        description: values.description || null,
        prompt: values.prompt,
        cron: values.schedule.cron,
        timezone: values.schedule.timezone,
        scheduleHuman: values.schedule.humanReadable,
        recipientEmail: values.recipientEmail,
        model: values.model,
        enabled: values.enabled,
      };
      const url = props.routineId ? `/api/routines/${props.routineId}` : "/api/routines";
      const method = props.routineId ? "PATCH" : "POST";
      const r = await fetch(url, {
        method,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        setError(await r.text());
        return;
      }
      const j = await r.json();
      router.push(`/routines/${j.routine.id}/runs`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5 max-w-2xl">
      <div>
        <Label>Name</Label>
        <Input
          value={values.name}
          onChange={(e) => setValues({ ...values, name: e.target.value })}
          required
          maxLength={255}
        />
      </div>
      <div>
        <Label>Description (optional)</Label>
        <Input
          value={values.description}
          onChange={(e) => setValues({ ...values, description: e.target.value })}
        />
      </div>
      <div>
        <Label>Prompt</Label>
        <Textarea
          value={values.prompt}
          onChange={(e) => setValues({ ...values, prompt: e.target.value })}
          rows={12}
          required
          className="font-mono text-sm"
        />
      </div>
      <div>
        <Label>Schedule</Label>
        <ScheduleField
          value={values.schedule}
          onChange={(s) => setValues({ ...values, schedule: s })}
        />
      </div>
      <div>
        <Label>Recipient email</Label>
        <Input
          type="email"
          value={values.recipientEmail}
          onChange={(e) => setValues({ ...values, recipientEmail: e.target.value })}
          required
        />
      </div>
      <div>
        <Label>Model</Label>
        <select
          className="block w-full rounded-md border px-3 py-2 text-sm"
          value={values.model}
          onChange={(e) => setValues({ ...values, model: e.target.value })}
        >
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <input
          id="enabled"
          type="checkbox"
          checked={values.enabled}
          onChange={(e) => setValues({ ...values, enabled: e.target.checked })}
        />
        <Label htmlFor="enabled" className="font-normal">
          Enabled
        </Label>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2 justify-end">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : props.routineId ? "Save" : "Create routine"}
        </Button>
      </div>
    </form>
  );
}
