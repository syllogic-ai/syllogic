"use client";

import { useEffect, useMemo, useState } from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { PersonAvatar } from "./person-avatar";

export type OwnerValue = { personId: string; share: number | null };

type Person = { id: string; name: string; color?: string | null; avatarUrl?: string | null };

export function OwnersField(props: {
  people: Person[];
  value: OwnerValue[];
  onChange: (next: OwnerValue[]) => void;
  disabled?: boolean;
}) {
  const { people, value, onChange, disabled } = props;
  const [equalSplit, setEqualSplit] = useState<boolean>(
    value.length > 0 ? value.every((o) => o.share === null) : true
  );

  // When the value prop loads asynchronously (e.g. fetched from the server),
  // re-derive equalSplit from it so the toggle reflects the loaded state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    setEqualSplit(value.length > 0 ? value.every((o) => o.share === null) : true);
    // Intentionally depend on a stable serialization of the shares to avoid
    // re-running on every render while still reacting when the async load arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.length, value.map((o) => o.share).join(",")]);

  const selectedIds = useMemo(() => new Set(value.map((o) => o.personId)), [value]);

  function toggle(personId: string) {
    if (selectedIds.has(personId)) {
      onChange(value.filter((o) => o.personId !== personId));
    } else {
      onChange([...value, { personId, share: equalSplit ? null : 0 }]);
    }
  }

  function setShare(personId: string, raw: string) {
    let n = raw === "" ? 0 : Number(raw) / 100;
    if (!Number.isFinite(n) || n < 0) n = 0;
    if (n > 1) n = 1;
    onChange(value.map((o) => (o.personId === personId ? { ...o, share: n } : o)));
  }

  useEffect(() => {
    if (equalSplit) {
      onChange(value.map((o) => ({ ...o, share: null })));
    } else {
      const eq = value.length > 0 ? 1 / value.length : 0;
      onChange(value.map((o) => ({ ...o, share: o.share ?? eq })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equalSplit]);

  const sum = value.reduce((acc, o) => acc + (o.share ?? 0), 0);
  const sumOff = !equalSplit && Math.abs(sum - 1) > 0.0001;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Owners</Label>
        {value.length > 1 && (
          <div className="flex items-center gap-2">
            <Label htmlFor="equal-split" className="text-sm font-normal text-muted-foreground">
              Split equally
            </Label>
            <Switch
              id="equal-split"
              checked={equalSplit}
              onCheckedChange={setEqualSplit}
              disabled={disabled}
            />
          </div>
        )}
      </div>

      <div className="space-y-2">
        {people.map((p) => {
          const selected = selectedIds.has(p.id);
          const owner = value.find((o) => o.personId === p.id);
          return (
            <div key={p.id} className="flex items-center gap-3">
              <Checkbox
                checked={selected}
                onCheckedChange={() => toggle(p.id)}
                disabled={disabled}
              />
              <PersonAvatar person={p} size={24} />
              <span className="flex-1 text-sm">{p.name}</span>
              {selected && !equalSplit && (
                <div className="flex items-center gap-1">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step={1}
                    value={owner?.share != null ? Math.round(owner.share * 100) : ""}
                    onChange={(e) => setShare(p.id, e.target.value)}
                    disabled={disabled}
                    className="w-20"
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {sumOff && (
        <p className="text-sm text-destructive">
          Shares must sum to 100% (currently {Math.round(sum * 100)}%).
        </p>
      )}
      {value.length === 0 && (
        <p className="text-sm text-destructive">Select at least one owner.</p>
      )}
    </div>
  );
}
