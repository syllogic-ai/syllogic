"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  RiBankLine,
  RiExternalLinkLine,
  RiEyeLine,
  RiEyeOffLine,
  RiRefreshLine,
} from "@remixicon/react";
import { createBrokerConnection } from "@/lib/api/investments";
import { T } from "./_tokens";
import {
  Field,
  Input,
  SelectWithChevron,
  btnGhost,
  btnPrimary,
} from "./_form-bits";

export function BrokerForm({ onCancel }: { onCancel: () => void }) {
  const router = useRouter();
  const [accountName, setAccountName] = useState("IBKR Main");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [token, setToken] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);
  const [qPos, setQPos] = useState("");
  const [qTrades, setQTrades] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createBrokerConnection({
        provider: "ibkr_flex",
        flex_token: token,
        query_id_positions: qPos,
        query_id_trades: qTrades,
        account_name: accountName,
        base_currency: baseCurrency,
      });
      router.push("/investments");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      style={{
        border: `1px solid ${T.border}`,
        borderTop: `2px solid ${T.primary}`,
        background: T.card,
        padding: 24,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            border: `1px solid ${T.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 11,
            color: T.mutedFg,
          }}
        >
          IBKR
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>
            Interactive Brokers · Flex Query
          </div>
          <div style={{ fontSize: 11, color: T.mutedFg, marginTop: 2 }}>
            Positions and trade history sync automatically via the Flex Web
            Service
          </div>
        </div>
      </div>
      <div
        style={{
          background: T.bg,
          border: `1px solid ${T.border}`,
          padding: "12px 16px",
          marginBottom: 20,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div
          style={{
            fontSize: 10,
            color: T.mutedFg,
            textTransform: "uppercase",
            letterSpacing: ".1em",
          }}
        >
          What you need
        </div>
        {[
          "A Flex Web Service token — from IBKR Account Management → Reports → Flex Queries",
          "A Positions Flex Query ID configured to export account positions",
          "A Trades Flex Query ID configured to export trade history",
        ].map((t) => (
          <div
            key={t}
            style={{
              display: "flex",
              gap: 8,
              fontSize: 11,
              color: T.mutedFg,
            }}
          >
            <span>·</span>
            <span>{t}</span>
          </div>
        ))}
        <a
          href="https://www.interactivebrokers.com/en/index.php?f=1325"
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: 11,
            color: T.fg,
            marginTop: 4,
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <RiExternalLinkLine size={11} /> How to set up Flex Queries →
        </a>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", gap: 14 }}>
          <Field label="Account name" flex={2}>
            <Input
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
            />
          </Field>
          <Field label="Base currency" flex={1}>
            <SelectWithChevron
              value={baseCurrency}
              onChange={(e) => setBaseCurrency(e.target.value)}
            >
              <option>EUR</option>
              <option>USD</option>
            </SelectWithChevron>
          </Field>
        </div>
        <Field label="Flex token">
          <div style={{ position: "relative" }}>
            <Input
              type={tokenVisible ? "text" : "password"}
              placeholder="Paste your Flex Web Service token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              style={{ paddingRight: 36 }}
            />
            <button
              type="button"
              onClick={() => setTokenVisible((v) => !v)}
              style={{
                position: "absolute",
                right: 10,
                top: "50%",
                transform: "translateY(-50%)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: T.mutedFg,
              }}
            >
              {tokenVisible ? (
                <RiEyeOffLine size={13} />
              ) : (
                <RiEyeLine size={13} />
              )}
            </button>
          </div>
        </Field>
        <div style={{ display: "flex", gap: 14 }}>
          <Field label="Positions query ID" flex={1}>
            <Input
              placeholder="e.g. 123456"
              value={qPos}
              onChange={(e) => setQPos(e.target.value)}
            />
          </Field>
          <Field label="Trades query ID" flex={1}>
            <Input
              placeholder="e.g. 789012"
              value={qTrades}
              onChange={(e) => setQTrades(e.target.value)}
            />
          </Field>
        </div>
        {err && <div style={{ color: T.negative, fontSize: 11 }}>{err}</div>}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: 4,
          }}
        >
          <button type="button" onClick={onCancel} style={btnGhost}>
            Cancel
          </button>
          <button type="submit" disabled={busy} style={btnPrimary}>
            <RiRefreshLine size={13} /> {busy ? "Syncing…" : "Connect & sync"}
          </button>
        </div>
      </div>
      <div
        style={{
          marginTop: 24,
          paddingTop: 20,
          borderTop: `1px solid ${T.border}`,
        }}
      >
        <div
          style={{
            fontSize: 10,
            color: T.mutedFg,
            textTransform: "uppercase",
            letterSpacing: ".1em",
            marginBottom: 10,
          }}
        >
          More brokers — coming soon
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {["Trading 212", "Degiro", "Schwab"].map((b) => (
            <div
              key={b}
              style={{
                flex: 1,
                padding: "10px 14px",
                border: `1px solid ${T.border}`,
                display: "flex",
                alignItems: "center",
                gap: 8,
                opacity: 0.45,
              }}
            >
              <RiBankLine size={14} color={T.mutedFg} />
              <span style={{ fontSize: 12, color: T.mutedFg }}>{b}</span>
            </div>
          ))}
        </div>
      </div>
    </form>
  );
}
