"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  RiAddLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiArrowUpDownLine,
  RiMore2Fill,
} from "@remixicon/react";
import type { Holding } from "@/lib/api/investments";
import { currencySymbol } from "@/lib/utils/currency";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EditHoldingDialog } from "./EditHoldingDialog";

type Filter = "All" | "ETF" | "Equity" | "Cash";
type SortKey = "sym" | "acct" | "type" | "qty" | "price" | "value" | "pnl";

export function TypeBadge({ type }: { type: "etf" | "equity" | "cash" }) {
  if (type === "etf") return <Badge>ETF</Badge>;
  if (type === "equity") return <Badge variant="secondary">Equity</Badge>;
  return <Badge variant="outline">Cash</Badge>;
}

export function HoldingsTableHF({
  holdings,
  accountNames,
  accountsCount,
  portfolioCurrencySymbol,
  onAddClick,
  onDelete,
}: {
  holdings: Holding[];
  accountNames: Record<string, string>;
  accountsCount: number;
  portfolioCurrencySymbol: string;
  onAddClick?: () => void;
  onDelete?: (id: string) => void;
}) {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("All");
  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d * -1) as -1 | 1);
    else {
      setSortKey(k);
      setSortDir(-1);
    }
  };

  const rows = useMemo(() => {
    return holdings
      .filter(
        (h) =>
          filter === "All" ||
          (filter === "ETF" && h.instrument_type === "etf") ||
          (filter === "Equity" && h.instrument_type === "equity") ||
          (filter === "Cash" && h.instrument_type === "cash"),
      )
      .map((h) => {
        const qty = Number(h.quantity);
        const price = Number(h.current_price ?? 0);
        const value = Number(h.current_value_user_currency ?? 0);
        const cost = h.avg_cost != null ? Number(h.avg_cost) * qty : null;
        const pnl = cost != null ? value - cost : null;
        return {
          ...h,
          _qty: qty,
          _price: price,
          _value: value,
          _pnl: pnl,
          _acct: accountNames[h.account_id] ?? h.account_id,
        };
      })
      .sort((a, b) => {
        if (sortKey === "pnl") {
          if (a._pnl == null && b._pnl == null) return 0;
          if (a._pnl == null) return 1;
          if (b._pnl == null) return -1;
          return (a._pnl - b._pnl) * sortDir;
        }
        const get = (r: typeof a) =>
          ({
            sym: r.symbol,
            acct: r._acct,
            type: r.instrument_type,
            qty: r._qty,
            price: r._price,
            value: r._value,
          })[sortKey as Exclude<SortKey, "pnl">];
        const av = get(a) ?? 0;
        const bv = get(b) ?? 0;
        return typeof av === "string"
          ? (av as string).localeCompare(bv as string) * sortDir
          : ((av as number) - (bv as number)) * sortDir;
      });
  }, [holdings, accountNames, filter, sortKey, sortDir]);

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (
      sortDir === -1 ? (
        <RiArrowDownSLine className="size-3" />
      ) : (
        <RiArrowUpSLine className="size-3" />
      )
    ) : (
      <RiArrowUpDownLine className="size-3 opacity-30" />
    );

  const totalValue = rows.reduce((s, r) => s + r._value, 0);
  const editingHolding = editingId ? holdings.find((h) => h.id === editingId) : null;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-3">
        <div>
          <h2 className="text-sm font-semibold">All holdings</h2>
          <p className="text-xs text-muted-foreground">
            {holdings.length} positions · {accountsCount} account
            {accountsCount !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex-1" />
        <ToggleGroup
          multiple={false}
          value={[filter]}
          onValueChange={(v) => {
            const next = v[0] as Filter | undefined;
            if (next) setFilter(next);
          }}
          variant="outline"
          size="sm"
        >
          {(["All", "ETF", "Equity", "Cash"] as Filter[]).map((t) => (
            <ToggleGroupItem key={t} value={t} aria-label={`Filter ${t}`}>
              {t}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {onAddClick && (
          <Button size="sm" onClick={onAddClick}>
            <RiAddLine className="size-4" />
            Add holding
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              {(
                [
                  ["sym", "Symbol", "left"],
                  ["acct", "Account", "left"],
                  ["type", "Type", "left"],
                  ["qty", "Qty", "right"],
                  ["price", "Price", "right"],
                  ["value", "Value", "right"],
                  ["pnl", "P&L", "right"],
                ] as const
              ).map(([k, label, align]) => (
                <TableHead
                  key={k}
                  onClick={() => handleSort(k as SortKey)}
                  className={`cursor-pointer select-none uppercase tracking-wider text-[10px] ${
                    align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  <span className={`inline-flex items-center gap-1 ${
                    align === "right" ? "justify-end w-full" : ""
                  }`}>
                    {label}
                    <SortIcon k={k as SortKey} />
                  </span>
                </TableHead>
              ))}
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((h) => {
              const sym = currencySymbol(h.currency);
              return (
                <TableRow
                  key={h.id}
                  tabIndex={0}
                  aria-label={`View details for ${h.symbol}`}
                  onClick={() => router.push(`/investments/${h.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/investments/${h.id}`);
                    }
                  }}
                  className={`cursor-pointer ${
                    h.is_stale ? "bg-amber-50 dark:bg-amber-950/30" : ""
                  }`}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{h.symbol}</span>
                      {h.is_stale && (
                        <span
                          title="Price may be stale"
                          className="size-1.5 rounded-full bg-amber-500"
                        />
                      )}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      {h.name ?? ""}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{h._acct}</Badge>
                  </TableCell>
                  <TableCell>
                    <TypeBadge type={h.instrument_type} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {h._qty.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {h.current_price ? `${sym} ${h._price.toFixed(2)}` : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">
                    {portfolioCurrencySymbol} {h._value.toLocaleString("en", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell className={`text-right tabular-nums ${
                    h._pnl == null
                      ? "text-muted-foreground"
                      : h._pnl >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-destructive"
                  }`}>
                    {h._pnl == null
                      ? "—"
                      : `${h._pnl >= 0 ? "+" : ""}${portfolioCurrencySymbol} ${h._pnl.toLocaleString("en", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}`}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Row actions"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") e.stopPropagation();
                          }}
                        >
                          <RiMore2Fill className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent
                        align="end"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <DropdownMenuItem
                          onClick={() => router.push(`/investments/${h.id}`)}
                        >
                          View details
                        </DropdownMenuItem>
                        {h.source === "manual" && (
                          <>
                            <DropdownMenuItem onClick={() => setEditingId(h.id)}>
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => setDeletingId(h.id)}
                              className="text-destructive focus:text-destructive"
                            >
                              Delete
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell colSpan={6} className="font-semibold text-muted-foreground">
                Total
              </TableCell>
              <TableCell className="text-right tabular-nums font-bold">
                {portfolioCurrencySymbol} {totalValue.toLocaleString("en", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </TableCell>
              <TableCell />
            </TableRow>
          </TableFooter>
        </Table>
      </CardContent>

      {editingHolding && (
        <EditHoldingDialog
          open={true}
          onOpenChange={(o) => !o && setEditingId(null)}
          holding={editingHolding}
        />
      )}

      <AlertDialog
        open={deletingId !== null}
        onOpenChange={(o) => !o && setDeletingId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this holding?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the manual position. Price history is retained but the
              position will no longer count toward your portfolio.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deletingId && onDelete) onDelete(deletingId);
                setDeletingId(null);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
