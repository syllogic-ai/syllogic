"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RiSearchLine } from "@remixicon/react";
import {
  addManualHolding,
  createManualAccount,
  type InvestmentAccount,
  type SymbolSearchResult,
} from "@/lib/api/investments";
import { searchSymbolsAction } from "@/lib/actions/investments";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import { Field, Input } from "./_form-bits";

const NEW = "__new__";
type Inst = "etf" | "equity" | "cash";

export function ManualForm({
  accounts,
  onCancel,
}: {
  accounts: InvestmentAccount[];
  onCancel: () => void;
}) {
  const router = useRouter();
  const [accountId, setAccountId] = useState<string>(accounts[0]?.id ?? NEW);
  const [newName, setNewName] = useState("My Brokerage");
  const [baseCcy, setBaseCcy] = useState("EUR");
  const [symbol, setSymbol] = useState("");
  const [matches, setMatches] = useState<SymbolSearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [qty, setQty] = useState("");
  const [type, setType] = useState<Inst>("etf");
  const [currency, setCurrency] = useState("EUR");
  const [avgCost, setAvgCost] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const debounce = useRef<number | null>(null);

  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    if (!symbol) {
      setMatches([]);
      return;
    }
    debounce.current = window.setTimeout(async () => {
      try {
        setMatches(await searchSymbolsAction(symbol));
      } catch {
        setMatches([]);
      }
    }, 200);
  }, [symbol]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const target =
        accountId === NEW
          ? (await createManualAccount(newName, baseCcy)).account_id
          : accountId;
      await addManualHolding(target, {
        symbol,
        quantity: qty,
        instrument_type: type,
        currency,
        ...(avgCost ? { avg_cost: avgCost } : {}),
      });
      router.push("/investments");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-t-2 border-t-primary">
      <CardContent className="p-6 space-y-4">
        <form onSubmit={submit} className="space-y-4">
          <div className="text-sm font-semibold">Add a holding</div>
          <div className="flex gap-3">
            <Field label="Account" className="flex-[1.2_1_0%]">
              <Select
                value={accountId}
                onValueChange={(v) => v && setAccountId(v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name} · {a.base_currency}
                    </SelectItem>
                  ))}
                  <SelectItem value={NEW}>+ Create new account…</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Symbol" className="flex-[2_1_0%]">
              <div className="relative">
                <RiSearchLine
                  size={12}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
                />
                <Input
                  placeholder="Search symbol or name…"
                  className="pl-7"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  onFocus={() => setShowResults(true)}
                  onBlur={() => setTimeout(() => setShowResults(false), 150)}
                />
                {showResults && matches.length > 0 && (
                  <div className="absolute top-full left-0 right-0 z-10 bg-card border border-border shadow-md">
                    {matches.map((r, i) => (
                      <div
                        key={i}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setSymbol(r.symbol);
                          if (r.currency) setCurrency(r.currency);
                        }}
                        className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer hover:bg-muted ${
                          i < matches.length - 1 ? "border-b border-border" : ""
                        }`}
                      >
                        <span className="font-bold text-xs min-w-[44px]">
                          {r.symbol}
                        </span>
                        <span className="flex-1 text-xs text-muted-foreground">
                          {r.name}
                        </span>
                        {r.exchange && (
                          <span className="text-[10px] px-1.5 py-px border border-border text-muted-foreground">
                            {r.exchange}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Field>
          </div>
          {accountId === NEW && (
            <div className="flex gap-3">
              <Field label="New account name" className="flex-[2_1_0%]">
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </Field>
              <Field label="Base currency" className="flex-1">
                <Select
                  value={baseCcy}
                  onValueChange={(v) => v && setBaseCcy(v)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>
          )}
          <div className="flex gap-3">
            <Field label="Quantity" className="flex-1">
              <Input
                type="number"
                placeholder="0.00"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </Field>
            <Field label="Instrument type" className="flex-1">
              <ToggleGroup
                multiple={false}
                value={[type]}
                onValueChange={(v) => v[0] && setType(v[0] as Inst)}
                variant="outline"
                size="sm"
              >
                {(["etf", "equity", "cash"] as Inst[]).map((t) => (
                  <ToggleGroupItem
                    key={t}
                    value={t}
                    className="capitalize flex-1"
                  >
                    {t === "etf" ? "ETF" : t}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Field>
            <Field label="Currency" className="flex-1">
              <Select
                value={currency}
                onValueChange={(v) => v && setCurrency(v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EUR">EUR</SelectItem>
                  <SelectItem value="USD">USD</SelectItem>
                  <SelectItem value="GBP">GBP</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field
              label={
                <>
                  Avg cost{" "}
                  <span className="font-normal text-muted-foreground normal-case tracking-normal">
                    (optional)
                  </span>
                </>
              }
              className="flex-1"
            >
              <Input
                type="number"
                placeholder="—"
                value={avgCost}
                onChange={(e) => setAvgCost(e.target.value)}
              />
            </Field>
          </div>
          {err && <div className="text-destructive text-xs">{err}</div>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Adding…" : "Add holding"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
