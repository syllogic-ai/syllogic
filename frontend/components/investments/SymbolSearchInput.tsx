"use client";
import { useEffect, useRef, useState } from "react";
import { searchSymbolsAction } from "@/lib/actions/investments";
import type { SymbolSearchResult } from "@/lib/api/investments";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface SymbolSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (result: SymbolSearchResult) => void;
  placeholder?: string;
  id?: string;
  className?: string;
}

export function SymbolSearchInput({
  value,
  onChange,
  onSelect,
  placeholder = "e.g. AAPL, VUAA.LON",
  id,
  className,
}: SymbolSearchInputProps) {
  const [results, setResults] = useState<SymbolSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const latestRequestRef = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim() || value.length < 2) {
      // Invalidate any in-flight request so its late response can't
      // repaint the dropdown after the input is cleared.
      latestRequestRef.current++;
      setResults([]);
      setOpen(false);
      setLoading(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      const requestId = ++latestRequestRef.current;
      setLoading(true);
      try {
        const hits = await searchSymbolsAction(value.trim());
        if (requestId !== latestRequestRef.current) return;
        setResults(hits);
        setOpen(hits.length > 0);
        setActiveIndex(-1);
      } catch {
        if (requestId !== latestRequestRef.current) return;
        setResults([]);
        setOpen(false);
      } finally {
        if (requestId === latestRequestRef.current) setLoading(false);
      }
    }, 350);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (result: SymbolSearchResult) => {
    onSelect(result);
    setOpen(false);
    setResults([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(results[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={className}
        autoComplete="off"
      />
      {loading && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
          Searching…
        </span>
      )}
      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
          {results.map((r, i) => (
            <li
              key={r.symbol}
              className={cn(
                "flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-accent",
                i === activeIndex && "bg-accent",
              )}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(r);
              }}
            >
              <span className="font-mono font-medium">{r.symbol}</span>
              <span className="truncate text-muted-foreground">{r.name}</span>
              {r.exchange && (
                <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                  {r.exchange}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
