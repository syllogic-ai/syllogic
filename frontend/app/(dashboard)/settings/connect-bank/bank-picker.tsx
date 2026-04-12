"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import { buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  RiSearchLine,
  RiBankLine,
  RiArrowLeftLine,
  RiLoader4Line,
  RiAlertLine,
} from "@remixicon/react";
import Link from "next/link";
import { initiateAuth } from "@/lib/actions/bank-connections";

// European countries with Enable Banking support
const COUNTRIES = [
  { code: "NL", name: "Netherlands" },
  { code: "DE", name: "Germany" },
  { code: "FR", name: "France" },
  { code: "ES", name: "Spain" },
  { code: "IT", name: "Italy" },
  { code: "BE", name: "Belgium" },
  { code: "AT", name: "Austria" },
  { code: "FI", name: "Finland" },
  { code: "SE", name: "Sweden" },
  { code: "NO", name: "Norway" },
  { code: "DK", name: "Denmark" },
  { code: "PT", name: "Portugal" },
  { code: "IE", name: "Ireland" },
  { code: "LU", name: "Luxembourg" },
  { code: "PL", name: "Poland" },
  { code: "EE", name: "Estonia" },
  { code: "LV", name: "Latvia" },
  { code: "LT", name: "Lithuania" },
];

interface Aspsp {
  name: string;
  country: string;
  logo?: string;
  beta?: boolean;
}

export function BankPicker() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  const [country, setCountry] = useState("NL");
  const [search, setSearch] = useState("");
  const [aspsps, setAspsps] = useState<Aspsp[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [connectingBank, setConnectingBank] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function fetchAspsps() {
      setLoading(true);
      setFetchError(null);
      try {
        const resp = await fetch(`/api/enable-banking/aspsps?country=${country}`, {
          signal: controller.signal,
        });
        if (!resp.ok) throw new Error("Failed to load banks");
        const data = await resp.json();
        const list = Array.isArray(data) ? data : data.aspsps || [];
        setAspsps(list);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setFetchError("Failed to load available banks. Please try again.");
        setAspsps([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }
    fetchAspsps();
    return () => controller.abort();
  }, [country]);

  const filtered = useMemo(() => {
    if (!search) return aspsps;
    const lower = search.toLowerCase();
    return aspsps.filter((a) => a.name.toLowerCase().includes(lower));
  }, [aspsps, search]);

  const handleConnect = async (aspsp: Aspsp) => {
    setConnectingBank(aspsp.name);
    try {
      const result = await initiateAuth(aspsp.name, aspsp.country || country);
      if (result.success && result.url) {
        window.location.href = result.url;
      } else {
        setFetchError(result.error || "Failed to initiate connection");
        setConnectingBank(null);
      }
    } catch {
      setFetchError("Failed to initiate connection. Please try again.");
      setConnectingBank(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/settings?tab=bank-connections"
        className={buttonVariants({ variant: "ghost", size: "sm" })}
      >
        <RiArrowLeftLine className="mr-1.5 h-4 w-4" />
        Back to Settings
      </Link>

      {/* Error from callback */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          <RiAlertLine className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold">Select Your Bank</h2>
        <p className="text-sm text-muted-foreground">
          Choose your bank to connect via Open Banking. You&apos;ll be redirected to authorize access.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Select value={country} onValueChange={(v) => v && setCountry(v)}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Select country" />
          </SelectTrigger>
          <SelectContent>
            {COUNTRIES.map((c) => (
              <SelectItem key={c.code} value={c.code}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="relative flex-1">
          <RiSearchLine className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search banks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Bank grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RiLoader4Line className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : fetchError ? (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-center text-sm text-destructive">
          {fetchError}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          No banks found{search ? ` matching "${search}"` : ` for ${country}`}.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((aspsp) => (
            <button
              key={aspsp.name}
              onClick={() => handleConnect(aspsp)}
              disabled={connectingBank !== null}
              className="flex items-center gap-3 rounded-lg border p-4 text-left transition-colors hover:bg-muted/50 disabled:opacity-50"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                <RiBankLine className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {aspsp.name}
                  {connectingBank === aspsp.name && (
                    <RiLoader4Line className="ml-2 inline h-4 w-4 animate-spin" />
                  )}
                </p>
                {aspsp.beta && (
                  <span className="text-xs text-muted-foreground">Beta</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
