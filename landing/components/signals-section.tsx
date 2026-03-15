const SIGNALS = [
  { label: "LICENSE", value: "AGPL-3.0" },
  { label: "DEPLOY", value: "Docker / Railway / CasaOS" },
  { label: "DEMO", value: "Live" },
  { label: "RELEASE", value: "v1.0.0" },
  { label: "DATA", value: "PostgreSQL 16" },
  { label: "AI", value: "Optional OpenAI" },
];

export function SignalsSection() {
  return (
    <section
      id="signals"
      className="py-8 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8">
        {SIGNALS.map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-1.5">
            <span
              className="text-xs font-mono uppercase tracking-widest"
              style={{ color: "var(--color-muted)" }}
            >
              {label}
            </span>
            <span
              className="text-sm font-mono"
              style={{ color: "var(--color-fg)" }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
