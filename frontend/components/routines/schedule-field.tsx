"use client";

import { useState } from "react";
import { Cron } from "croner";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export type ScheduleValue = { cron: string; timezone: string; humanReadable: string };

export function ScheduleField(props: {
  value: ScheduleValue;
  onChange: (v: ScheduleValue) => void;
}) {
  const [tab, setTab] = useState<"nl" | "cron">("nl");
  const [nlText, setNlText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function parseNl() {
    if (!nlText.trim()) return;
    setParsing(true);
    setError(null);
    try {
      const r = await fetch("/api/routines/parse-schedule", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: nlText }),
      });
      if (!r.ok) {
        setError(await r.text());
        return;
      }
      const j = await r.json();
      props.onChange({ cron: j.cron, timezone: j.timezone, humanReadable: j.humanReadable });
    } finally {
      setParsing(false);
    }
  }

  let preview: string[] = [];
  let cronError: string | null = null;
  try {
    const c = new Cron(props.value.cron, { timezone: props.value.timezone });
    preview = c.nextRuns(3).map((d) => d.toLocaleString());
  } catch (e) {
    cronError = (e as Error).message;
  }

  return (
    <div className="space-y-3 rounded-md border p-4">
      <div className="flex gap-2">
        <Button
          type="button"
          variant={tab === "nl" ? "default" : "ghost"}
          size="sm"
          onClick={() => setTab("nl")}
        >
          Natural language
        </Button>
        <Button
          type="button"
          variant={tab === "cron" ? "default" : "ghost"}
          size="sm"
          onClick={() => setTab("cron")}
        >
          Cron expression
        </Button>
      </div>

      {tab === "nl" && (
        <div className="space-y-2">
          <Label>Describe the schedule</Label>
          <Textarea
            value={nlText}
            onChange={(e) => setNlText(e.target.value)}
            placeholder="every Monday at 8am Amsterdam time"
            rows={2}
          />
          <Button type="button" size="sm" onClick={parseNl} disabled={parsing}>
            {parsing ? "Parsing…" : "Parse with AI"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      )}

      {tab === "cron" && (
        <div className="space-y-2">
          <Label>Cron expression</Label>
          <Input
            value={props.value.cron}
            onChange={(e) => props.onChange({ ...props.value, cron: e.target.value })}
            placeholder="0 8 * * 1"
          />
          <Label>Timezone (IANA)</Label>
          <Input
            value={props.value.timezone}
            onChange={(e) => props.onChange({ ...props.value, timezone: e.target.value })}
            placeholder="Europe/Amsterdam"
          />
        </div>
      )}

      <div className="rounded-md bg-muted p-3 text-sm">
        <div className="font-medium">{props.value.humanReadable || "(no schedule yet)"}</div>
        {cronError ? (
          <div className="text-destructive mt-1">{cronError}</div>
        ) : (
          <ul className="mt-2 list-disc pl-5 text-muted-foreground">
            {preview.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
