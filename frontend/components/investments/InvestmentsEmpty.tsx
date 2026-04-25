"use client";
import { useRouter } from "next/navigation";
import {
  RiAddLine,
  RiLineChartLine,
  RiLinksLine,
  RiPencilLine,
} from "@remixicon/react";
import { T } from "./_tokens";

export function InvestmentsEmpty() {
  const router = useRouter();
  const go = () => router.push("/investments/connect");
  return (
    <div
      className="syllogic-surface"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 40,
      }}
    >
      <div
        style={{
          maxWidth: 520,
          width: "100%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "32px 32px 24px",
            background: T.card,
            border: `1px solid ${T.border}`,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            alignItems: "center",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              border: `1px solid ${T.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: T.bg,
            }}
          >
            <RiLineChartLine size={20} color={T.mutedFg} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>No holdings yet</div>
            <div
              style={{
                fontSize: 12,
                color: T.mutedFg,
                lineHeight: 1.7,
                maxWidth: 340,
              }}
            >
              Track your portfolio by connecting a broker for automatic sync, or
              add holdings manually.
            </div>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            gap: 0,
            borderLeft: `1px solid ${T.border}`,
            borderRight: `1px solid ${T.border}`,
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <div
            style={{
              flex: 1,
              padding: 24,
              display: "flex",
              flexDirection: "column",
              gap: 12,
              borderRight: `1px solid ${T.border}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <RiLinksLine size={16} />
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                Connect broker
              </span>
              <span
                style={{
                  marginLeft: "auto",
                  padding: "1px 6px",
                  background: T.primary,
                  color: T.primaryFg,
                  fontSize: 9,
                  letterSpacing: ".06em",
                }}
              >
                RECOMMENDED
              </span>
            </div>
            <div
              style={{ fontSize: 11, color: T.mutedFg, lineHeight: 1.7 }}
            >
              Connect Interactive Brokers via Flex Query. Positions and trades
              sync automatically.
            </div>
            <ul
              style={{
                margin: "4px 0 0",
                padding: "0 0 0 16px",
                display: "flex",
                flexDirection: "column",
                gap: 5,
              }}
            >
              {[
                "Automatic position sync",
                "Trade history imported",
                "No manual entry needed",
              ].map((t) => (
                <li key={t} style={{ fontSize: 11, color: T.mutedFg }}>
                  {t}
                </li>
              ))}
            </ul>
            <button
              onClick={go}
              style={{
                marginTop: 4,
                padding: "8px 0",
                background: T.primary,
                color: T.primaryFg,
                border: "none",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: 12,
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              <RiLinksLine size={13} /> Connect IBKR
            </button>
          </div>
          <div
            style={{
              flex: 1,
              padding: 24,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <RiPencilLine size={16} />
              <span style={{ fontWeight: 600, fontSize: 13 }}>Add manually</span>
            </div>
            <div
              style={{ fontSize: 11, color: T.mutedFg, lineHeight: 1.7 }}
            >
              Create an account, search by symbol, and enter quantities. Prices
              are fetched automatically.
            </div>
            <ul
              style={{
                margin: "4px 0 0",
                padding: "0 0 0 16px",
                display: "flex",
                flexDirection: "column",
                gap: 5,
              }}
            >
              {[
                "No broker needed",
                "Prices updated daily",
                "You manage quantities",
              ].map((t) => (
                <li key={t} style={{ fontSize: 11, color: T.mutedFg }}>
                  {t}
                </li>
              ))}
            </ul>
            <button
              onClick={go}
              style={{
                marginTop: 4,
                padding: "8px 0",
                background: T.card,
                color: T.fg,
                border: `1px solid ${T.border}`,
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: 12,
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
              }}
            >
              <RiAddLine size={13} /> Add holding
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
