"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrokerConnection } from "@/lib/api/investments";

const FIELDS = [
  "account_name",
  "flex_token",
  "query_id_positions",
  "query_id_trades",
  "base_currency",
] as const;

type FieldKey = (typeof FIELDS)[number];

export function ConnectIBKRForm() {
  const router = useRouter();
  const [form, setForm] = useState<Record<FieldKey, string>>({
    account_name: "Interactive Brokers",
    flex_token: "",
    query_id_positions: "",
    query_id_trades: "",
    base_currency: "EUR",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createBrokerConnection({ provider: "ibkr_flex", ...form });
      router.push("/investments");
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      {FIELDS.map((k) => (
        <label key={k} className="block">
          <span className="text-sm">{k}</span>
          <input
            className="mt-1 w-full rounded border px-2 py-1"
            value={form[k]}
            onChange={(e) => setForm({ ...form, [k]: e.target.value })}
          />
        </label>
      ))}
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm"
      >
        {busy ? "Connecting…" : "Connect IBKR"}
      </button>
      <p className="text-xs text-muted-foreground">
        Generate a Flex Token and two Flex Queries (positions + trades) in
        IBKR Account Management → Reports → Flex Queries → Flex Web Service.
      </p>
    </form>
  );
}
