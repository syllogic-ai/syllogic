"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiAddLine, RiCloseLine } from "@remixicon/react";
import {
  addManualHolding,
  createManualAccount,
  type InvestmentAccount,
  type SymbolSearchResult,
} from "@/lib/api/investments";
import { Button } from "@/components/ui/button";
import { SymbolSearchInput } from "./SymbolSearchInput";
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

type Row = {
  id: string;
  symbol: string;
  symbolConfirmed: boolean;
  qty: string;
  type: Inst;
  currency: string;
  avgCost: string;
  error: string | null;
};

let _rowSeq = 0;
function newRow(): Row {
  return {
    id: `r${++_rowSeq}`,
    symbol: "",
    symbolConfirmed: false,
    qty: "",
    type: "etf",
    currency: "EUR",
    avgCost: "",
    error: null,
  };
}

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
  const [rows, setRows] = useState<Row[]>([newRow()]);
  const [busy, setBusy] = useState(false);
  const [topErr, setTopErr] = useState<string | null>(null);

  const updateRow = (id: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const removeRow = (id: string) =>
    setRows((rs) => (rs.length === 1 ? rs : rs.filter((r) => r.id !== id)));
  const addRow = () => setRows((rs) => [...rs, newRow()]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setTopErr(null);
    setRows((rs) => rs.map((r) => ({ ...r, error: null })));

    // Validate at least one row has symbol + qty
    const valid = rows.filter((r) => r.symbol.trim() && r.qty.trim());
    if (valid.length === 0) {
      setTopErr("Add at least one holding with a symbol and quantity.");
      setBusy(false);
      return;
    }

    try {
      const target =
        accountId === NEW
          ? (await createManualAccount(newName, baseCcy)).account_id
          : accountId;

      const results = await Promise.allSettled(
        valid.map((r) =>
          addManualHolding(target, {
            symbol: r.symbol,
            quantity: r.qty,
            instrument_type: r.type,
            currency: r.currency,
            ...(r.avgCost ? { avg_cost: r.avgCost } : {}),
          }),
        ),
      );

      const failures = results
        .map((res, i) => ({ res, row: valid[i] }))
        .filter(({ res }) => res.status === "rejected");

      if (failures.length === 0) {
        router.push("/investments");
        return;
      }

      // Drop rows that succeeded (already saved on the backend); keep
      // failed rows with their error messages plus any rows that weren't
      // submitted because they were incomplete.
      const failedById = new Map(
        failures.map(({ res, row }) => {
          const reason = res.status === "rejected" ? res.reason : null;
          return [
            row.id,
            reason instanceof Error ? reason.message : String(reason),
          ];
        }),
      );
      const submittedIds = new Set(valid.map((r) => r.id));
      setRows((rs) =>
        rs
          .filter((r) => failedById.has(r.id) || !submittedIds.has(r.id))
          .map((r) =>
            failedById.has(r.id) ? { ...r, error: failedById.get(r.id)! } : r,
          ),
      );
      setTopErr(
        `${results.length - failures.length}/${results.length} holdings added. Fix the errors below to retry the rest.`,
      );
    } catch (e) {
      setTopErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-t-2 border-t-primary">
      <CardContent className="p-6 space-y-4">
        <form onSubmit={submit} className="space-y-4">
          <div className="text-sm font-semibold">Add holdings</div>

          <div className="flex gap-3">
            <Field label="Account" className="flex-1">
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

          <div className="space-y-3">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Holdings ({rows.length})
            </div>
            {rows.map((r, i) => (
              <HoldingRow
                key={r.id}
                row={r}
                index={i}
                canRemove={rows.length > 1}
                onChange={(patch) => updateRow(r.id, patch)}
                onRemove={() => removeRow(r.id)}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addRow}
              className="w-full"
            >
              <RiAddLine className="size-4" />
              Add another holding
            </Button>
          </div>

          {topErr && <div className="text-destructive text-xs">{topErr}</div>}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy
                ? "Adding…"
                : `Add ${rows.length} holding${rows.length === 1 ? "" : "s"}`}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function HoldingRow({
  row,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  row: Row;
  index: number;
  canRemove: boolean;
  onChange: (patch: Partial<Row>) => void;
  onRemove: () => void;
}) {
  const symbolLabel = row.symbol ? (
    <span className="flex items-center gap-1.5">
      Symbol
      {row.symbolConfirmed ? (
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-px text-[9px] font-semibold tracking-wide text-emerald-700 dark:text-emerald-400">
          ✓ verified
        </span>
      ) : (
        <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-px text-[9px] font-semibold tracking-wide text-amber-700 dark:text-amber-400">
          ⚠ pick from list
        </span>
      )}
    </span>
  ) : (
    "Symbol"
  );

  return (
    <div className="rounded border border-border p-3 space-y-3 relative">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          #{index + 1}
        </div>
        {canRemove && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onRemove}
            aria-label="Remove holding"
          >
            <RiCloseLine className="size-4" />
          </Button>
        )}
      </div>
      <div className="flex gap-3">
        <Field label={symbolLabel} className="flex-[2_1_0%]">
          <SymbolSearchInput
            value={row.symbol}
            onChange={(v) =>
              onChange({ symbol: v, symbolConfirmed: false })
            }
            onSelect={(r: SymbolSearchResult) =>
              onChange({
                symbol: r.symbol,
                symbolConfirmed: true,
                ...(r.currency ? { currency: r.currency } : {}),
              })
            }
            placeholder="Search symbol or name…"
          />
        </Field>
      </div>
      <div className="flex gap-3">
        <Field label="Quantity" className="flex-1">
          <Input
            type="number"
            placeholder="0.00"
            value={row.qty}
            onChange={(e) => onChange({ qty: e.target.value })}
          />
        </Field>
        <Field label="Instrument type" className="flex-1">
          <ToggleGroup
            multiple={false}
            value={[row.type]}
            onValueChange={(v) =>
              v[0] && onChange({ type: v[0] as Inst })
            }
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
            value={row.currency}
            onValueChange={(v) => v && onChange({ currency: v })}
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
            value={row.avgCost}
            onChange={(e) => onChange({ avgCost: e.target.value })}
          />
        </Field>
      </div>
      {row.error && (
        <div className="text-destructive text-xs">{row.error}</div>
      )}
    </div>
  );
}
