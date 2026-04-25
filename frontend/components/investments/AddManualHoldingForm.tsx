"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  addManualHolding,
  createManualAccount,
  listInvestmentAccounts,
  searchSymbols,
  type InvestmentAccount,
  type SymbolSearchResult,
} from "@/lib/api/investments";

type InstrumentType = "equity" | "etf" | "cash";

const NEW_ACCOUNT = "__new__";

export function AddManualHoldingForm() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<InvestmentAccount[] | null>(null);
  const [accountId, setAccountId] = useState<string>(NEW_ACCOUNT);
  const [accountName, setAccountName] = useState("My Brokerage");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [type, setType] = useState<InstrumentType>("equity");
  const [currency, setCurrency] = useState("USD");
  const [asOf, setAsOf] = useState("");
  const [matches, setMatches] = useState<SymbolSearchResult[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listInvestmentAccounts()
      .then((rows) => {
        setAccounts(rows);
        if (rows.length > 0) setAccountId(rows[0].id);
      })
      .catch(() => setAccounts([]));
  }, []);

  async function onSearch(q: string) {
    setSymbol(q);
    if (q.length === 0) {
      setMatches([]);
      return;
    }
    try {
      setMatches(await searchSymbols(q));
    } catch {
      setMatches([]);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const targetAccountId =
        accountId === NEW_ACCOUNT
          ? (await createManualAccount(accountName, baseCurrency)).account_id
          : accountId;
      await addManualHolding(targetAccountId, {
        symbol,
        quantity,
        instrument_type: type,
        currency,
        ...(asOf ? { as_of_date: asOf } : {}),
      });
      router.push("/investments");
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

  const useExisting = accountId !== NEW_ACCOUNT;

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      <label className="block">
        <span className="text-sm">Investment account</span>
        <select
          className="mt-1 w-full rounded border px-2 py-1"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          {(accounts ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
          <option value={NEW_ACCOUNT}>+ Create new account…</option>
        </select>
      </label>
      {!useExisting && (
        <>
          <label className="block">
            <span className="text-sm">New account name</span>
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
        </>
      )}
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
        disabled={submitting}
        className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm disabled:opacity-50"
      >
        {submitting ? "Adding…" : "Add holding"}
      </button>
    </form>
  );
}
