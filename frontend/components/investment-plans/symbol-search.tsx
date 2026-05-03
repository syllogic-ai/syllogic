"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";

type Symbol = { symbol: string; name?: string; exchange?: string; currency?: string };

export function SymbolSearch(props: { value: string; onChange: (sym: string) => void }) {
  const [query, setQuery] = useState(props.value);
  const [results, setResults] = useState<Symbol[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => { setQuery(props.value); }, [props.value]);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const handle = setTimeout(async () => {
      try {
        const r = await fetch("/api/symbols/search", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ query }),
        });
        if (r.ok) {
          const j = await r.json();
          setResults(j.results ?? []);
        }
      } catch { /* swallow */ }
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  return (
    <div className="relative">
      <Input
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); props.onChange(e.target.value.toUpperCase()); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="VUAA"
        className="uppercase"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-background border rounded-md shadow-lg max-h-56 overflow-auto">
          {results.map((s, i) => (
            <li key={`${s.symbol}-${i}`}
                className="cursor-pointer px-3 py-2 text-sm hover:bg-muted"
                onMouseDown={() => { props.onChange(s.symbol); setQuery(s.symbol); setOpen(false); }}>
              <div className="font-medium">{s.symbol}</div>
              {s.name && <div className="text-xs text-muted-foreground">{s.name}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
