import { LINKS } from "@/lib/links";

const NOW = [
  "Self-host with Docker Compose or deploy with Railway.",
  "Track balances, categories, recurring spend, and cash-flow trends.",
  "Import and export transactions with CSV workflows.",
  "Use optional AI categorization and merchant enrichment.",
];

const NEXT = [
  "Smoother onboarding for first-time imports and shared demos.",
  "More self-host content: GIF walkthroughs, comparison pages, and install proof.",
  "Community-driven prioritization via issues and GitHub Discussions.",
];

const FEEDBACK = [
  {
    label: "Install help",
    href: LINKS.issuesNew.installHelp,
  },
  {
    label: "Demo feedback",
    href: LINKS.issuesNew.demoFeedback,
  },
  {
    label: "Feature request",
    href: LINKS.issuesNew.featureRequest,
  },
];

export function RoadmapSection() {
  return (
    <section
      id="roadmap"
      className="py-24 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      <div className="flex items-baseline gap-4 mb-8">
        <span
          className="font-mono text-sm"
          style={{ color: "var(--color-accent)" }}
        >
          06
        </span>
        <h2
          className="font-display text-5xl"
          style={{ color: "var(--color-fg)" }}
        >
          ROADMAP
        </h2>
      </div>

      <p
        className="max-w-3xl font-mono text-sm leading-relaxed mb-12"
        style={{ color: "var(--color-muted)" }}
      >
        Syllogic is already deployable. The next phase is focused on trust,
        onboarding, and sharper community feedback loops instead of adding
        abstract surface area.
      </p>

      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-px"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        <div className="p-8" style={{ backgroundColor: "var(--color-bg)" }}>
          <p
            className="font-mono text-xs uppercase tracking-widest mb-5"
            style={{ color: "var(--color-muted)" }}
          >
            Shipping now
          </p>
          <div className="space-y-4">
            {NOW.map((item) => (
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
            Coming next
          </p>
          <div className="space-y-4">
            {NEXT.map((item) => (
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
            Help shape it
          </p>
          <div className="space-y-4 mb-8">
            {FEEDBACK.map((item) => (
              <a
                key={item.label}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className="block font-mono text-sm"
                style={{ color: "var(--color-fg)" }}
              >
                {item.label}
              </a>
            ))}
          </div>

          <div className="flex flex-wrap gap-3">
            <a
              href={LINKS.roadmap}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                backgroundColor: "var(--color-accent)",
                color: "var(--color-bg)",
              }}
            >
              View roadmap
            </a>
            <a
              href={LINKS.discussions}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                border: "1px solid var(--color-border)",
                color: "var(--color-fg)",
              }}
            >
              Join discussions
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

