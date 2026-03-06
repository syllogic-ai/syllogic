const STACK = [
  { label: "Frontend", value: "Next.js 16 + Drizzle ORM" },
  { label: "Backend", value: "FastAPI + Celery" },
  { label: "Database", value: "PostgreSQL 16" },
  { label: "Cache", value: "Redis 7" },
  { label: "Auth", value: "BetterAuth" },
  { label: "AI", value: "OpenAI API" },
  { label: "UI", value: "shadcn/ui + Recharts" },
  { label: "License", value: "AGPL-3.0" },
];

const LINKS = [
  {
    label: "GitHub",
    href: "https://github.com/syllogic-ai/syllogic",
  },
  {
    label: "Railway Template",
    href: "https://railway.app/template/syllogic",
  },
  {
    label: "Documentation",
    href: "https://github.com/syllogic-ai/syllogic/blob/main/README.md",
  },
  {
    label: "Issues",
    href: "https://github.com/syllogic-ai/syllogic/issues",
  },
  {
    label: "Contributing",
    href: "https://github.com/syllogic-ai/syllogic/blob/main/CONTRIBUTING.md",
  },
];

export function ColophonSection() {
  return (
    <section
      id="colophon"
      className="py-24 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      {/* Section header */}
      <div className="flex items-baseline gap-4 mb-16">
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
          STACK
        </h2>
      </div>

      {/* Content grid */}
      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-px mb-px"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        {/* Stack */}
        <div
          className="p-8 lg:col-span-2"
          style={{ backgroundColor: "var(--color-bg)" }}
        >
          <h3
            className="font-mono text-xs uppercase tracking-widest mb-6"
            style={{ color: "var(--color-muted)" }}
          >
            STACK
          </h3>
          <div className="grid grid-cols-2 gap-x-8 gap-y-5">
            {STACK.map(({ label, value }) => (
              <div key={label} className="flex flex-col gap-0.5">
                <span
                  className="font-mono text-xs uppercase tracking-wide"
                  style={{ color: "var(--color-muted)" }}
                >
                  {label}
                </span>
                <span
                  className="font-mono text-sm"
                  style={{ color: "var(--color-fg)" }}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Links */}
        <div className="p-8" style={{ backgroundColor: "var(--color-bg)" }}>
          <h3
            className="font-mono text-xs uppercase tracking-widest mb-6"
            style={{ color: "var(--color-muted)" }}
          >
            LINKS
          </h3>
          <div className="flex flex-col gap-4">
            {LINKS.map(({ label, href }) => (
              <a
                key={label}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-sm flex items-center gap-2 group transition-colors duration-150 hover:text-accent"
                style={{ color: "var(--color-fg)" }}
              >
                <span
                  className="opacity-0 group-hover:opacity-100 transition-opacity duration-150"
                  style={{ color: "var(--color-accent)" }}
                >
                  →
                </span>
                {label}
              </a>
            ))}
          </div>
        </div>
      </div>

    </section>
  );
}
