"use client";

import { useEffect, useRef, useState } from "react";
import { FeatureModal, type Feature } from "./feature-modal";

const FEATURES: Feature[] = [
  {
    id: "01",
    title: "Balances and cash flow",
    description:
      "Live balances, savings, spending, and cash-flow views that make it obvious where your money goes.",
    detail:
      "Your home base for understanding your money. At a glance you see total income, total expenses, and net savings for any period you choose — a week, a month, or a custom range. A profit & loss chart breaks down the trend over time, while a Sankey flow diagram shows exactly where your money comes from and where it ends up. All numbers update in real time as you import new transactions.",
    wide: true,
  },
  {
    id: "02",
    title: "AI Categorization",
    description:
      "Optional OpenAI-powered categorization with a fallback path when no API key is set.",
    detail:
      "Every time you import a transaction, Syllogic reads the description and assigns it a spending category — things like Groceries, Dining, Travel, or Subscriptions — without you lifting a finger. When the AI gets it wrong (it occasionally does), you correct it once and it remembers. Over time the categories get more accurate and reflect your personal spending patterns.",
    wide: false,
  },
  {
    id: "03",
    title: "Subscription Tracking",
    description:
      "Detect recurring charges, group them by merchant, and understand monthly subscription drag.",
    detail:
      "Syllogic scans your transaction history to find recurring charges — the ones that repeat every month or year at a predictable amount. It groups them by merchant so you can see the full list of your active subscriptions, when they renew, and what your total monthly subscription spend looks like. A surprisingly useful number once you actually see it.",
    wide: false,
  },
  {
    id: "04",
    title: "Category Analytics",
    description:
      "Break spending down by category, compare periods, and spot trends before they become habits.",
    detail:
      "Pick any category — say, Dining — and see exactly how much you spent in it each month for the past year. Compare it to the previous period, see if you're trending up or down, and spot the months where you overspent. A donut chart shows the category breakdown at a glance so you immediately know where the biggest opportunities to cut back are.",
    wide: false,
  },
  {
    id: "05",
    title: "Transfer and reimbursement linking",
    description:
      "Link related transactions across accounts to avoid double-counting.",
    detail:
      "If you transfer money from your checking account to your savings account, that shows up as both an outgoing and an incoming transaction. Without linking them, your expense totals look inflated. Syllogic lets you mark those two transactions as related so your dashboard counts them correctly — one transfer, not two separate expenses.",
    wide: false,
  },
  {
    id: "06",
    title: "CSV Import / Export",
    description:
      "Import from bank CSVs and export your data whenever you want. No lock-in.",
    detail:
      "Every bank lets you download your transaction history as a CSV file. Syllogic can import those files regardless of the column format your bank uses — it adapts to the structure automatically. And because your data is yours, you can export everything at any time in a clean, standard format. No lock-in, no strings attached.",
    wide: false,
  },
  {
    id: "07",
    title: "MCP Server",
    description:
      "Connect Claude Desktop or any MCP-compatible LLM directly to your financial data. Ask questions, run bulk operations, and get AI-driven insights — all in natural language.",
    detail:
      "Syllogic ships a built-in MCP (Model Context Protocol) server that exposes your financial data as tools any compatible AI client can call. Connect Claude Desktop, Cursor, or any other MCP-compatible app and start talking to your finances like you would a spreadsheet — except smarter. The LLM can read transactions, categories, accounts, and balances, then act on them based on your instructions.",
    wide: true,
    useCases: [
      "\"How much did I spend on dining last month compared to the month before?\"",
      "\"Recategorize all transactions from Amazon as Shopping instead of Other.\"",
      "\"Which subscriptions am I paying for that I haven't used in 3 months?\"",
      "\"What are my top 5 spending categories this year and how can I reduce them?\"",
      "\"Flag all transactions above €200 from the last 30 days for my review.\"",
      "\"Give me a summary of my income vs expenses for Q1.\"",
    ],
  },
];

export function WorkSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [selected, setSelected] = useState<Feature | null>(null);

  useEffect(() => {
    let cleanup: (() => void) | undefined;

    async function initGsap() {
      const { gsap } = await import("gsap");
      const { ScrollTrigger } = await import("gsap/ScrollTrigger");
      gsap.registerPlugin(ScrollTrigger);

      const cards =
        sectionRef.current?.querySelectorAll<HTMLElement>(".feature-card");
      if (!cards?.length) return;

      gsap.fromTo(
        cards,
        { opacity: 0, y: 24 },
        {
          opacity: 1,
          y: 0,
          stagger: 0.08,
          duration: 0.55,
          ease: "power2.out",
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 75%",
          },
        }
      );

      cleanup = () => ScrollTrigger.getAll().forEach((t) => t.kill());
    }

    initGsap();
    return () => cleanup?.();
  }, []);

  return (
    <>
      <section
        ref={sectionRef}
        id="work"
        className="py-24 px-8 lg:px-24"
        style={{ borderTop: "1px solid var(--color-border)" }}
      >
        {/* Section header */}
        <div className="flex items-baseline gap-4 mb-4">
        <span
          className="font-mono text-sm"
          style={{ color: "var(--color-accent)" }}
        >
            04
        </span>
          <h2
            className="font-display text-5xl"
            style={{ color: "var(--color-fg)" }}
          >
            WHAT WORKS TODAY
          </h2>
        </div>
        <p
          className="font-mono text-xs mb-4"
          style={{ color: "var(--color-muted)" }}
        >
          Click any card to learn more
        </p>
        <p
          className="font-mono text-sm leading-relaxed max-w-3xl mb-16"
          style={{ color: "var(--color-muted)" }}
        >
          Syllogic already covers the workflows a self-hoster needs to evaluate
          the product honestly: dashboards, imports, recurring spend, optional
          AI enrichment, and exportable data.
        </p>

        {/* Bento grid */}
        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px"
          style={{ backgroundColor: "var(--color-border)" }}
        >
          {FEATURES.map((feature) => (
            <button
              key={feature.id}
              className={`feature-card group p-8 text-left transition-colors duration-200 cursor-pointer ${
                feature.wide ? "lg:col-span-2" : ""
              }`}
              style={{ backgroundColor: "var(--color-bg)", opacity: 0 }}
              onClick={() => setSelected(feature)}
              onMouseEnter={(e) =>
                (e.currentTarget.style.backgroundColor =
                  "rgba(255,255,255,0.025)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.backgroundColor = "var(--color-bg)")
              }
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span
                    className="font-mono text-xs"
                    style={{ color: "var(--color-accent)" }}
                  >
                    {feature.id}
                  </span>
                  {feature.useCases && (
                    <span
                      className="font-mono text-xs px-2 py-0.5 uppercase tracking-widest"
                      style={{
                        border: "1px solid rgba(249,115,22,0.35)",
                        color: "var(--color-accent)",
                      }}
                    >
                      NEW
                    </span>
                  )}
                </div>
                <span
                  className="font-mono text-xs opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                  style={{ color: "var(--color-muted)" }}
                >
                  VIEW →
                </span>
              </div>
              <h3
                className="font-display text-2xl mb-3 transition-colors duration-200 group-hover:text-accent"
                style={{ color: "var(--color-fg)" }}
              >
                {feature.title}
              </h3>
              <p
                className="font-mono text-sm leading-relaxed"
                style={{ color: "var(--color-muted)" }}
              >
                {feature.description}
              </p>
              {feature.useCases && (
                <ul className="mt-5 space-y-1.5">
                  {feature.useCases.slice(0, 3).map((uc, i) => (
                    <li
                      key={i}
                      className="font-mono text-xs leading-relaxed"
                      style={{ color: "rgba(232,230,225,0.45)" }}
                    >
                      <span style={{ color: "var(--color-accent)" }}>›</span>{" "}
                      {uc.replace(/^"|"$/g, "")}
                    </li>
                  ))}
                </ul>
              )}
            </button>
          ))}
        </div>
      </section>

      {selected && (
        <FeatureModal feature={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
