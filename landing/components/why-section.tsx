import { LINKS } from "@/lib/links";

const REASONS = [
  {
    id: "01",
    title: "Own the stack",
    body:
      "Run Syllogic on your own VPS, homelab, or NAS. Docker Compose is the default path, and Railway is there when you want a faster hosted setup.",
  },
  {
    id: "02",
    title: "Keep financial data under your control",
    body:
      "Balances, transactions, recurring spend, and imports stay on infrastructure you control. Export data when you want. Leave when you want.",
  },
  {
    id: "03",
    title: "Use AI only when it helps",
    body:
      "OpenAI-powered categorization is optional. If you do not set an API key, Syllogic still works with rule-based matching and manual cleanup.",
  },
];

const AUDIENCE = [
  "Self-hosters who want a real finance dashboard, not a spreadsheet maze.",
  "Privacy-focused developers who do not want their transaction history locked into a hosted SaaS.",
  "Homelab users who want a polished app with Docker, Railway, and CasaOS paths.",
];

export function WhySection() {
  return (
    <section
      id="why"
      className="py-24 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      <div className="flex items-baseline gap-4 mb-8">
        <span
          className="font-mono text-sm"
          style={{ color: "var(--color-accent)" }}
        >
          03
        </span>
        <h2
          className="font-display text-5xl"
          style={{ color: "var(--color-fg)" }}
        >
          WHY SELF-HOST
        </h2>
      </div>

      <p
        className="max-w-3xl font-mono text-sm leading-relaxed mb-12"
        style={{ color: "var(--color-muted)" }}
      >
        Syllogic is designed for people who want more control over their
        financial data than hosted budgeting products typically allow. The app
        is usable today, export-friendly, and deployable without a week of
        infrastructure work.
      </p>

      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-px mb-px"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        {REASONS.map((reason) => (
          <div
            key={reason.id}
            className="p-8"
            style={{ backgroundColor: "var(--color-bg)" }}
          >
            <p
              className="font-mono text-xs mb-4"
              style={{ color: "var(--color-accent)" }}
            >
              {reason.id}
            </p>
            <h3
              className="font-display text-3xl mb-3"
              style={{ color: "var(--color-fg)" }}
            >
              {reason.title.toUpperCase()}
            </h3>
            <p
              className="font-mono text-sm leading-relaxed"
              style={{ color: "var(--color-muted)" }}
            >
              {reason.body}
            </p>
          </div>
        ))}
      </div>

      <div
        className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-px"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        <div className="p-8" style={{ backgroundColor: "var(--color-bg)" }}>
          <p
            className="font-mono text-xs uppercase tracking-widest mb-5"
            style={{ color: "var(--color-muted)" }}
          >
            Who it is for
          </p>
          <div className="space-y-4">
            {AUDIENCE.map((item) => (
              <p
                key={item}
                className="font-mono text-sm leading-relaxed"
                style={{ color: "var(--color-fg)" }}
              >
                {item}
              </p>
            ))}
          </div>
        </div>

        <div className="p-8" style={{ backgroundColor: "var(--color-bg)" }}>
          <p
            className="font-mono text-xs uppercase tracking-widest mb-5"
            style={{ color: "var(--color-muted)" }}
          >
            Next step
          </p>
          <p
            className="font-mono text-sm leading-relaxed mb-8"
            style={{ color: "var(--color-muted)" }}
          >
            Start with the live demo if you want to see the product first, or
            go straight to the quick-start guide if you are ready to self-host.
          </p>
          <div className="flex flex-wrap gap-3">
            <a
              href={LINKS.demo.hero}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                backgroundColor: "var(--color-accent)",
                color: "var(--color-bg)",
              }}
            >
              Try the demo
            </a>
            <a
              href={LINKS.startPath}
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                border: "1px solid var(--color-border)",
                color: "var(--color-fg)",
              }}
            >
              Start here
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

