"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { updateHolding, type Holding } from "@/lib/api/investments";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SymbolSearchInput } from "./SymbolSearchInput";
import type { SymbolSearchResult } from "@/lib/api/investments";

export function EditHoldingDialog({
  open,
  onOpenChange,
  holding,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  holding: Holding;
}) {
  const router = useRouter();
  const [symbol, setSymbol] = useState(holding.symbol);
  const [qty, setQty] = useState(holding.quantity);
  const [avgCost, setAvgCost] = useState(holding.avg_cost ?? "");
  const [asOfDate, setAsOfDate] = useState(holding.as_of_date ?? "");
  const [providerSymbol, setProviderSymbol] = useState(holding.provider_symbol ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await updateHolding(holding.id, {
        ...(symbol !== holding.symbol ? { symbol } : {}),
        quantity: qty,
        avg_cost: avgCost === "" ? null : avgCost,
        as_of_date: asOfDate === "" ? null : asOfDate,
        provider_symbol: providerSymbol === "" ? null : providerSymbol,
      });
      onOpenChange(false);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit holding · {holding.symbol}</DialogTitle>
          <DialogDescription>
            Manual holdings only. Connected-broker positions sync automatically.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="symbol">Symbol</Label>
            <SymbolSearchInput
              id="symbol"
              value={symbol}
              onChange={setSymbol}
              onSelect={(r: SymbolSearchResult) => setSymbol(r.symbol)}
            />
            <p className="text-xs text-muted-foreground">
              Changing the symbol triggers an automatic re-pricing on save.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="qty">Quantity</Label>
            <Input
              id="qty"
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="avg-cost">
              Avg cost <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="avg-cost"
              type="number"
              value={avgCost}
              onChange={(e) => setAvgCost(e.target.value)}
              placeholder="—"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="as-of">
              As of date <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="as-of"
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-symbol">
              Price lookup symbol{" "}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <SymbolSearchInput
              id="provider-symbol"
              value={providerSymbol}
              onChange={setProviderSymbol}
              onSelect={(r: SymbolSearchResult) => setProviderSymbol(r.symbol)}
              placeholder={`e.g. ${holding.symbol}.LON or ${holding.symbol}.AS`}
            />
            <p className="text-xs text-muted-foreground">
              Override the ticker used for price lookups. Useful for European ETFs
              that need an exchange suffix (e.g. VUAA → VUAA.LON).
            </p>
          </div>
          {err && <p className="text-sm text-destructive">{err}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
