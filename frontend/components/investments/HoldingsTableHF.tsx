"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  RiAddLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiArrowUpDownLine,
  RiMore2Fill,
} from "@remixicon/react";
import type { Holding } from "@/lib/api/investments";
import { T } from "./_tokens";

type Filter = "All" | "ETF" | "Equity" | "Cash";
type SortKey = "sym" | "acct" | "type" | "qty" | "price" | "value" | "pnl";

export function TypeBadge({ type }: { type: "etf" | "equity" | "cash" }) {
  const s = {
    etf: {
      background: T.primary,
      color: T.primaryFg,
      border: `1px solid ${T.primary}`,
    },
    equity: {
      background: T.muted,
      color: T.fg,
      border: `1px solid ${T.border}`,
    },
    cash: {
      background: "transparent",
      color: T.mutedFg,
      border: `1px solid ${T.border}`,
    },
  }[type];
  return (
    <span
      style={{
        display: "inline-flex",
        padding: "1px 6px",
        fontSize: 10,
        letterSpacing: ".04em",
        ...s,
      }}
    >
      {type === "etf" ? "ETF" : type === "equity" ? "Equity" : "Cash"}
    </span>
  );
}

export function HoldingsTableHF({
  holdings,
  accountNames,
  accountsCount,
  onAddClick,
  onDelete,
}: {
  holdings: Holding[];
  accountNames: Record<string, string>;
  accountsCount: number;
  onAddClick?: () => void;
  onDelete?: (id: string) => void;
}) {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("All");
  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);

  const handleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d * -1) as -1 | 1);
    else {
      setSortKey(k);
      setSortDir(-1);
    }
  };

  const rows = holdings
    .filter(
      (h) =>
        filter === "All" ||
        (filter === "ETF" && h.instrument_type === "etf") ||
        (filter === "Equity" && h.instrument_type === "equity") ||
        (filter === "Cash" && h.instrument_type === "cash"),
    )
    .map((h) => ({
      ...h,
      _qty: Number(h.quantity),
      _price: Number(h.current_price ?? 0),
      _value: Number(h.current_value_user_currency ?? 0),
      _acct: accountNames[h.account_id] ?? h.account_id,
    }))
    .sort((a, b) => {
      const get = (r: typeof a) =>
        ({
          sym: r.symbol,
          acct: r._acct,
          type: r.instrument_type,
          qty: r._qty,
          price: r._price,
          value: r._value,
          pnl: 0,
        })[sortKey];
      const av = get(a) ?? 0;
      const bv = get(b) ?? 0;
      return typeof av === "string"
        ? av.localeCompare(bv as string) * sortDir
        : ((av as number) - (bv as number)) * sortDir;
    });

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (
      sortDir === -1 ? (
        <RiArrowDownSLine size={11} />
      ) : (
        <RiArrowUpSLine size={11} />
      )
    ) : (
      <RiArrowUpDownLine size={10} style={{ opacity: 0.3 }} />
    );

  const totalValue = rows.reduce((s, r) => s + r._value, 0);

  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}` }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "12px 18px",
          gap: 12,
          borderBottom: `1px solid ${T.border}`,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13 }}>All holdings</span>
        <span style={{ fontSize: 11, color: T.mutedFg }}>
          {holdings.length} positions · {accountsCount} account
          {accountsCount !== 1 ? "s" : ""}
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 0 }}>
          {(["All", "ETF", "Equity", "Cash"] as Filter[]).map((t) => {
            const active = filter === t;
            return (
              <button
                key={t}
                onClick={() => setFilter(t)}
                style={{
                  padding: "4px 10px",
                  fontSize: 11,
                  fontFamily: "inherit",
                  border: `1px solid ${active ? T.primary : T.border}`,
                  background: active ? T.primary : T.card,
                  color: active ? T.primaryFg : T.mutedFg,
                  cursor: "pointer",
                  marginLeft: -1,
                }}
              >
                {t}
              </button>
            );
          })}
        </div>
        {onAddClick && (
          <button
            onClick={onAddClick}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "5px 12px",
              background: T.primary,
              color: T.primaryFg,
              border: "none",
              cursor: "pointer",
              fontSize: 11,
            }}
          >
            <RiAddLine size={12} /> Add holding
          </button>
        )}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {(
              [
                ["sym", "Symbol", "left"],
                ["acct", "Account", "left"],
                ["type", "Type", "left"],
                ["qty", "Qty", "right"],
                ["price", "Price", "right"],
                ["value", "Value", "right"],
              ] as const
            ).map(([k, label, align]) => (
              <th
                key={k}
                onClick={() => handleSort(k as SortKey)}
                style={{
                  textAlign: align,
                  padding: "9px 18px",
                  fontSize: 10,
                  color: T.mutedFg,
                  fontWeight: 500,
                  textTransform: "uppercase",
                  letterSpacing: ".08em",
                  cursor: "pointer",
                  userSelect: "none",
                }}
              >
                <span
                  style={{ display: "inline-flex", alignItems: "center", gap: 2 }}
                >
                  {label}
                  <SortIcon k={k as SortKey} />
                </span>
              </th>
            ))}
            <th style={{ width: 36 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr
              key={h.id}
              className={h.is_stale ? "stale" : ""}
              tabIndex={0}
              aria-label={`View details for ${h.symbol}`}
              onClick={() => router.push(`/investments/${h.id}`)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  router.push(`/investments/${h.id}`);
                }
              }}
              style={{
                borderBottom: `1px solid ${T.muted}`,
                background: h.is_stale ? T.staleBg : undefined,
                cursor: "pointer",
              }}
            >
              <td style={{ padding: "11px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{h.symbol}</span>
                  {h.is_stale && (
                    <span
                      title="Price may be stale"
                      style={{
                        width: 6,
                        height: 6,
                        background: T.stale,
                        borderRadius: "50%",
                      }}
                    />
                  )}
                </div>
                <div style={{ fontSize: 10, color: T.mutedFg, marginTop: 1 }}>
                  {h.name ?? ""}
                </div>
              </td>
              <td style={{ padding: "11px 18px" }}>
                <span
                  style={{
                    padding: "2px 6px",
                    border: `1px solid ${T.border}`,
                    fontSize: 10,
                    color: T.mutedFg,
                    background: T.muted,
                  }}
                >
                  {h._acct}
                </span>
              </td>
              <td style={{ padding: "11px 18px" }}>
                <TypeBadge type={h.instrument_type} />
              </td>
              <td
                style={{
                  padding: "11px 18px",
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {h._qty.toLocaleString()}
              </td>
              <td
                style={{
                  padding: "11px 18px",
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                  color: T.mutedFg,
                }}
              >
                {h.current_price
                  ? `${h.currency === "USD" ? "$" : "€"} ${h._price.toFixed(2)}`
                  : "—"}
              </td>
              <td
                style={{
                  padding: "11px 18px",
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                  fontWeight: 600,
                }}
              >
                €{" "}
                {h._value.toLocaleString("en", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
              <td style={{ padding: "11px 10px", textAlign: "center" }}>
                {onDelete && h.source === "manual" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(h.id); }}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation(); }}
                    title="Delete"
                    style={{
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      color: T.mutedFg,
                    }}
                  >
                    <RiMore2Fill size={14} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: `1px solid ${T.border}`, background: T.bg }}>
            <td
              colSpan={5}
              style={{
                padding: "10px 18px",
                fontSize: 11,
                fontWeight: 600,
                color: T.mutedFg,
              }}
            >
              Total
            </td>
            <td
              style={{
                padding: "10px 18px",
                textAlign: "right",
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
                fontSize: 13,
              }}
            >
              €{" "}
              {totalValue.toLocaleString("en", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
