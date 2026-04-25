"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  addManualHolding,
  createManualAccount,
  searchSymbols,
  type SymbolSearchResult,
} from "@/lib/api/investments";

type InstrumentType = "equity" | "etf" | "cash";

export function AddManualHoldingForm() {
  const router = useRouter();
  const [accountName, setAccountName] = useState("My Brokerage");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [type, setType] = useState<InstrumentType>("equity");
  const [currency, setCurrency] = useState("USD");
  const [asOf, setAsOf] = useState("");
  const [matches, setMatches] = useState<SymbolSearchResult[]>([]);
  const [err, setErr] = useState<string | null>(null);

  async function onSearch(q: string) {
    setSymbol(q);
    if (q.length >= 1) {
      try {
        setMatches(await searchSymbols(q));
      } catch {
        setMatches([]);
      }
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const { account_id } = await createManualAccount(
        accountName,
        baseCurrency,
      );
      await addManualHolding(account_id, {
        symbol,
        quantity,
        instrument_type: type,
        currency,
        ...(asOf ? { as_of_date: asOf } : {}),
      });
      router.push("/investments");
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      <label className="block">
        <span className="text-sm">Account name</span>
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={accountName}
          onChange={(e) => setAccountName(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="text-sm">Base currency</span>
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={baseCurrency}
          onChange={(e) => setBaseCurrency(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="text-sm">Symbol</span>
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={symbol}
          onChange={(e) => onSearch(e.target.value)}
          list="symMatches"
        />
      </label>
      <datalist id="symMatches">
        {matches.map((m) => (
          <option key={m.symbol} value={m.symbol}>
            {m.name}
          </option>
        ))}
      </datalist>
      <label className="block">
        <span className="text-sm">Quantity</span>
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="text-sm">Type</span>
        <select
          className="mt-1 w-full rounded border px-2 py-1"
          value={type}
          onChange={(e) => setType(e.target.value as InstrumentType)}
        >
          <option value="equity">Equity</option>
          <option value="etf">ETF</option>
          <option value="cash">Cash</option>
        </select>
      </label>
      <label className="block">
        <span className="text-sm">Currency</span>
        <input
          className="mt-1 w-full rounded border px-2 py-1"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="text-sm">Held since (optional)</span>
        <input
          type="date"
          className="mt-1 w-full rounded border px-2 py-1"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
        />
      </label>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button
        type="submit"
        className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm"
      >
        Add holding
      </button>
    </form>
  );
}
