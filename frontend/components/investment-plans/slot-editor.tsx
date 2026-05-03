"use client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SymbolSearch } from "./symbol-search";
import type { SlotConfig } from "@/lib/investment-plans/schema";

function genId() {
  return crypto.randomUUID();
}

export function SlotEditor(props: {
  value: SlotConfig[];
  onChange: (next: SlotConfig[]) => void;
  totalMonthly: number;
  currency: string;
}) {
  function update(i: number, patch: Partial<SlotConfig>) {
    const next = props.value.slice();
    next[i] = { ...next[i], ...patch } as SlotConfig;
    props.onChange(next);
  }
  function remove(i: number) {
    props.onChange(props.value.filter((_, j) => j !== i));
  }
  function addPinned() {
    props.onChange([...props.value, { id: genId(), kind: "pinned", symbol: "", amount: 0 }]);
  }
  function addDiscretionary() {
    props.onChange([...props.value, { id: genId(), kind: "discretionary", theme: "", amount: 0 }]);
  }

  const sum = props.value.reduce((a, s) => a + (Number(s.amount) || 0), 0);
  const diff = props.totalMonthly - sum;

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {props.value.map((s, i) => (
          <div key={s.id} className="flex items-start gap-2 border rounded-md p-3">
            <div className="flex-1 space-y-2">
              <div className="flex gap-1">
                <Button type="button" size="sm"
                        variant={s.kind === "pinned" ? "default" : "ghost"}
                        onClick={() => {
                          if (s.kind === "pinned") return;
                          update(i, { kind: "pinned", symbol: "", amount: s.amount } as unknown as Partial<SlotConfig>);
                        }}>
                  Pinned
                </Button>
                <Button type="button" size="sm"
                        variant={s.kind === "discretionary" ? "default" : "ghost"}
                        onClick={() => {
                          if (s.kind === "discretionary") return;
                          update(i, { kind: "discretionary", theme: "", amount: s.amount } as unknown as Partial<SlotConfig>);
                        }}>
                  Discretionary
                </Button>
              </div>
              {s.kind === "pinned" ? (
                <div>
                  <Label>Symbol</Label>
                  <SymbolSearch value={s.symbol} onChange={(sym) => update(i, { symbol: sym } as unknown as Partial<SlotConfig>)} />
                </div>
              ) : (
                <div>
                  <Label>Theme</Label>
                  <Textarea
                    value={s.theme}
                    onChange={(e) => update(i, { theme: e.target.value } as unknown as Partial<SlotConfig>)}
                    placeholder="What kind of company / sector should the agent research?"
                    rows={2}
                  />
                </div>
              )}
              <div>
                <Label>Amount ({props.currency})</Label>
                <Input type="number" min={0} step={1} value={s.amount}
                       onChange={(e) => update(i, { amount: Number(e.target.value) } as unknown as Partial<SlotConfig>)} />
              </div>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={() => remove(i)}>Remove</Button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={addPinned}>+ Pinned slot</Button>
        <Button type="button" variant="outline" size="sm" onClick={addDiscretionary}>+ Discretionary slot</Button>
      </div>

      <div className={`text-sm rounded-md px-3 py-2 ${Math.abs(diff) < 0.01 ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>
        Allocated: {sum.toFixed(2)} {props.currency} of {props.totalMonthly.toFixed(2)} {props.currency}
        {Math.abs(diff) >= 0.01 && ` — off by ${diff.toFixed(2)}`}
      </div>
    </div>
  );
}
