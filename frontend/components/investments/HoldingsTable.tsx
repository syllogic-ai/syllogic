"use client";
import type { Holding } from "@/lib/api/investments";

export function HoldingsTable({
  holdings,
  onDelete,
}: {
  holdings: Holding[];
  onDelete?: (id: string) => void;
}) {
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-muted-foreground">
        <tr>
          <th>Symbol</th>
          <th>Type</th>
          <th className="text-right">Qty</th>
          <th className="text-right">Price</th>
          <th className="text-right">Value</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => (
          <tr key={h.id} className="border-t">
            <td className="py-2">
              <span className="font-medium">{h.symbol}</span>{" "}
              <span className="text-xs text-muted-foreground">{h.name}</span>
            </td>
            <td>{h.instrument_type}</td>
            <td className="text-right">{h.quantity}</td>
            <td className="text-right">
              {h.current_price ?? "—"} {h.currency}
            </td>
            <td
              className={`text-right ${h.is_stale ? "text-amber-600" : ""}`}
            >
              {h.current_value_user_currency ?? "—"}
            </td>
            <td className="text-right">
              {onDelete && h.source === "manual" && (
                <button
                  type="button"
                  className="text-xs text-red-600"
                  onClick={() => onDelete(h.id)}
                >
                  Remove
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
