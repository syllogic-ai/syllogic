"use client";

import { useState } from "react";
import { BitmapChevron } from "./bitmap-chevron";
import { LINKS } from "@/lib/links";

const RAILWAY_FEATURES = [
  "One-click deploy from Railway template",
  "Auto-scaling with zero config",
  "Managed PostgreSQL + Redis included",
  "Custom domain with SSL",
  "Environment variable management",
];

const DOCKER_FEATURES = [
  "Full control over infrastructure",
  "Run on any VPS or homelab",
  "Docker Compose for all services",
];

const SERVICES = [
  {
    name: "frontend",
    stack: "Next.js 16",
    description: "UI, authentication, and all data operations via server actions.",
  },
  {
    name: "backend",
    stack: "FastAPI + Celery",
    description: "AI categorization pipeline and scheduled background jobs.",
  },
  {
    name: "postgres",
    stack: "PostgreSQL 16",
    description: "Shared database — the single source of truth for all your data.",
  },
  {
    name: "redis",
    stack: "Redis 7",
    description: "Job queue and cache for async task processing.",
  },
];

const INSTALL_CMD =
  "curl -fsSL https://github.com/syllogic-ai/syllogic/releases/latest/download/install.sh | sudo bash";

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square">
      <rect x="9" y="9" width="13" height="13" rx="0" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function InstallSnippet() {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(INSTALL_CMD).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="flex items-stretch gap-0">
      {/* Command box */}
      <div
        className="flex-1 min-w-0 px-4 py-3 overflow-x-auto"
        style={{
          backgroundColor: "rgba(255,255,255,0.03)",
          border: "1px solid var(--color-border)",
          borderRight: "none",
        }}
      >
        <span
          className="font-mono text-xs whitespace-nowrap"
          style={{ color: "var(--color-accent)" }}
        >
          ${" "}
        </span>
        <span
          className="font-mono text-xs whitespace-nowrap"
          style={{ color: "var(--color-fg)" }}
        >
          {INSTALL_CMD}
        </span>
      </div>

      {/* Copy button */}
      <button
        onClick={copy}
        className="flex items-center justify-center px-3 shrink-0 transition-colors"
        style={{
          backgroundColor: "rgba(255,255,255,0.03)",
          border: "1px solid var(--color-border)",
          color: copied ? "var(--color-accent)" : "var(--color-muted)",
        }}
        aria-label="Copy to clipboard"
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    </div>
  );
}

export function PrinciplesSection() {
  return (
    <section
      id="install"
      className="py-24 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      {/* Section header */}
      <div className="flex items-baseline gap-4 mb-8">
        <span
          className="font-mono text-sm"
          style={{ color: "var(--color-accent)" }}
        >
          05
        </span>
        <h2
          className="font-display text-5xl"
          style={{ color: "var(--color-fg)" }}
        >
          INSTALL IN 10 MINUTES
        </h2>
      </div>

      <p
        className="font-mono text-sm leading-relaxed max-w-3xl mb-16"
        style={{ color: "var(--color-muted)" }}
      >
        Choose the path that matches how you like to run software. Start with
        the live demo, self-host with Docker, or use Railway when you want the
        quickest production path.
      </p>

      {/* Cards */}
      <div
        className="grid grid-cols-1 lg:grid-cols-2 gap-px"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        {/* Railway */}
        <div className="p-10" style={{ backgroundColor: "var(--color-bg)" }}>
          <div className="flex items-center gap-3 mb-6">
            <div
              className="w-7 h-7 flex items-center justify-center text-xs font-mono"
              style={{
                border: "1px solid var(--color-accent)",
                color: "var(--color-accent)",
              }}
            >
              R
            </div>
            <h3
              className="font-display text-3xl"
              style={{ color: "var(--color-fg)" }}
            >
              RAILWAY
            </h3>
          </div>

          <p
            className="font-mono text-sm leading-relaxed mb-8"
            style={{ color: "var(--color-muted)" }}
          >
            Fastest path to a working hosted stack. Use the published template,
            add your secrets, and validate the product before you commit to a
            longer self-hosted setup.
          </p>

          <ul className="space-y-3 mb-10">
            {RAILWAY_FEATURES.map((f) => (
              <li
                key={f}
                className="flex items-start gap-3 font-mono text-sm"
                style={{ color: "rgba(232,230,225,0.75)" }}
              >
                <BitmapChevron
                  className="-rotate-90 mt-1 shrink-0"
                  size={8}
                  style={{ color: "var(--color-accent)" }}
                />
                {f}
              </li>
            ))}
          </ul>

          <a
            href={LINKS.railway.install}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3 font-mono text-sm uppercase tracking-widest transition-opacity hover:opacity-80"
            style={{
              backgroundColor: "var(--color-accent)",
              color: "var(--color-bg)",
            }}
          >
            Deploy on Railway
            <BitmapChevron className="-rotate-90" size={8} />
          </a>
        </div>

        {/* Docker */}
        <div className="p-10" style={{ backgroundColor: "var(--color-bg)" }}>
          <div className="flex items-center gap-3 mb-6">
            <div
              className="w-7 h-7 flex items-center justify-center text-xs font-mono"
              style={{
                border: "1px solid var(--color-border)",
                color: "var(--color-fg)",
              }}
            >
              D
            </div>
            <h3
              className="font-display text-3xl"
              style={{ color: "var(--color-fg)" }}
            >
              DOCKER
            </h3>
          </div>

          <p
            className="font-mono text-sm leading-relaxed mb-8"
            style={{ color: "var(--color-muted)" }}
          >
            Self-host on your own machine, VPS, or homelab. Full control, no
            vendor lock-in, and a documented path from demo to production.
          </p>

          <ul className="space-y-3 mb-8">
            {DOCKER_FEATURES.map((f) => (
              <li
                key={f}
                className="flex items-start gap-3 font-mono text-sm"
                style={{ color: "rgba(232,230,225,0.75)" }}
              >
                <BitmapChevron
                  className="-rotate-90 mt-1 shrink-0"
                  size={8}
                  style={{ color: "var(--color-muted)" }}
                />
                {f}
              </li>
            ))}
          </ul>

          {/* Services */}
          <div className="mb-8">
            <p
              className="font-mono text-xs uppercase tracking-widest mb-4"
              style={{ color: "var(--color-muted)" }}
            >
              Services
            </p>
            <div
              className="divide-y"
              style={{ borderColor: "var(--color-border)" }}
            >
              {SERVICES.map((s) => (
                <div
                  key={s.name}
                  className="py-3 grid grid-cols-[6rem_1fr] gap-4 items-start"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <div>
                    <span
                      className="font-mono text-xs"
                      style={{ color: "var(--color-accent)" }}
                    >
                      {s.name}
                    </span>
                    <p
                      className="font-mono text-xs mt-0.5"
                      style={{ color: "var(--color-muted)" }}
                    >
                      {s.stack}
                    </p>
                  </div>
                  <p
                    className="font-mono text-xs leading-relaxed"
                    style={{ color: "rgba(232,230,225,0.6)" }}
                  >
                    {s.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <InstallSnippet />
          <div className="flex flex-wrap gap-3 mt-6">
            <a
              href={LINKS.startPath}
              className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest"
              style={{ color: "var(--color-fg)" }}
            >
              Read the quick-start guide
            </a>
            <a
              href={LINKS.demo.hero}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest"
              style={{ color: "var(--color-muted)" }}
            >
              Try the live demo first
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
