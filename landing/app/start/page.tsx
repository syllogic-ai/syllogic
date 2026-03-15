import type { Metadata } from "next";
import { LINKS } from "@/lib/links";

const USE_CASES = [
  "You want a self-hosted dashboard for balances, spending, recurring charges, and trends.",
  "You care about privacy and do not want your transaction data trapped in a hosted finance app.",
  "You want Docker-first deployment, but still want a fallback path through Railway.",
];

const RUN_PATHS = [
  {
    label: "Live demo",
    detail:
      "See the dashboard, recurring spend tracking, and transaction workflows without deploying first.",
    href: LINKS.demo.start,
  },
  {
    label: "Docker",
    detail:
      "Run the full stack on your own machine or homelab with the install script or Docker Compose docs.",
    href: LINKS.readme,
  },
  {
    label: "Railway",
    detail:
      "Use the one-click template when you want the fastest route to a working hosted environment.",
    href: LINKS.railway.install,
  },
];

const COMPARE_ROWS = [
  {
    label: "Data control",
    syllogic: "You own the database and files",
    hosted: "Vendor-controlled",
    spreadsheet: "Local file only",
  },
  {
    label: "Deployment",
    syllogic: "Docker, Railway, CasaOS",
    hosted: "No self-host option",
    spreadsheet: "No app to deploy",
  },
  {
    label: "AI categorization",
    syllogic: "Optional OpenAI integration",
    hosted: "Vendor-dependent",
    spreadsheet: "Manual formulas or scripts",
  },
  {
    label: "Recurring spend tracking",
    syllogic: "Built in",
    hosted: "Usually built in",
    spreadsheet: "Manual setup",
  },
  {
    label: "Exportability",
    syllogic: "CSV import and export",
    hosted: "Varies by vendor",
    spreadsheet: "Manual and brittle",
  },
];

export const metadata: Metadata = {
  title: "Start Here | Syllogic",
  description:
    "What Syllogic is, who it is for, and how to self-host it in under 10 minutes.",
};

export default function StartPage() {
  return (
    <main className="min-h-screen px-8 py-16 lg:px-24">
      <div className="max-w-6xl mx-auto">
        <a
          href="/"
          className="inline-flex items-center mb-8 font-mono text-xs uppercase tracking-widest"
          style={{ color: "var(--color-muted)" }}
        >
          Back to home
        </a>

        <div className="max-w-4xl mb-16">
          <p
            className="font-mono text-xs uppercase tracking-[0.25em] mb-6"
            style={{ color: "var(--color-accent)" }}
          >
            START HERE
          </p>
          <h1
            className="font-display leading-none mb-6"
            style={{ fontSize: "clamp(3rem, 10vw, 8rem)", color: "var(--color-fg)" }}
          >
            SELF-HOSTED PERSONAL FINANCE
          </h1>
          <p
            className="font-mono text-base leading-relaxed max-w-3xl"
            style={{ color: "var(--color-fg)" }}
          >
            Syllogic is a self-hosted personal finance dashboard with AI
            categorization, recurring spend tracking, CSV import and export,
            and a live demo. It is built for self-hosters who want a real app,
            not a spreadsheet template and not a black-box hosted product.
          </p>
        </div>

        <section
          className="py-10"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <h2
            className="font-display text-4xl mb-8"
            style={{ color: "var(--color-fg)" }}
          >
            WHO IT IS FOR
          </h2>
          <div
            className="grid grid-cols-1 lg:grid-cols-3 gap-px"
            style={{ backgroundColor: "var(--color-border)" }}
          >
            {USE_CASES.map((item, index) => (
              <div
                key={item}
                className="p-8"
                style={{ backgroundColor: "var(--color-bg)" }}
              >
                <p
                  className="font-mono text-xs mb-4"
                  style={{ color: "var(--color-accent)" }}
                >
                  0{index + 1}
                </p>
                <p
                  className="font-mono text-sm leading-relaxed"
                  style={{ color: "var(--color-fg)" }}
                >
                  {item}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section
          className="py-10"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <h2
            className="font-display text-4xl mb-8"
            style={{ color: "var(--color-fg)" }}
          >
            HOW TO RUN IT
          </h2>
          <div
            className="grid grid-cols-1 lg:grid-cols-3 gap-px"
            style={{ backgroundColor: "var(--color-border)" }}
          >
            {RUN_PATHS.map((path) => (
              <a
                key={path.label}
                href={path.href}
                target="_blank"
                rel="noopener noreferrer"
                className="p-8 block"
                style={{ backgroundColor: "var(--color-bg)" }}
              >
                <h3
                  className="font-display text-3xl mb-4"
                  style={{ color: "var(--color-fg)" }}
                >
                  {path.label.toUpperCase()}
                </h3>
                <p
                  className="font-mono text-sm leading-relaxed"
                  style={{ color: "var(--color-muted)" }}
                >
                  {path.detail}
                </p>
              </a>
            ))}
          </div>
        </section>

        <section
          className="py-10"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <h2
            className="font-display text-4xl mb-8"
            style={{ color: "var(--color-fg)" }}
          >
            QUICK COMPARISON
          </h2>
          <div
            className="overflow-x-auto"
            style={{ border: "1px solid var(--color-border)" }}
          >
            <table className="w-full min-w-[760px] border-collapse">
              <thead>
                <tr style={{ backgroundColor: "rgba(255,255,255,0.03)" }}>
                  <th className="p-4 text-left font-mono text-xs uppercase tracking-widest">
                    Category
                  </th>
                  <th className="p-4 text-left font-mono text-xs uppercase tracking-widest">
                    Syllogic
                  </th>
                  <th className="p-4 text-left font-mono text-xs uppercase tracking-widest">
                    Hosted app
                  </th>
                  <th className="p-4 text-left font-mono text-xs uppercase tracking-widest">
                    Spreadsheet
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPARE_ROWS.map((row) => (
                  <tr
                    key={row.label}
                    style={{ borderTop: "1px solid var(--color-border)" }}
                  >
                    <td className="p-4 font-mono text-sm" style={{ color: "var(--color-fg)" }}>
                      {row.label}
                    </td>
                    <td className="p-4 font-mono text-sm" style={{ color: "var(--color-fg)" }}>
                      {row.syllogic}
                    </td>
                    <td className="p-4 font-mono text-sm" style={{ color: "var(--color-muted)" }}>
                      {row.hosted}
                    </td>
                    <td className="p-4 font-mono text-sm" style={{ color: "var(--color-muted)" }}>
                      {row.spreadsheet}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section
          className="py-10"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <h2
            className="font-display text-4xl mb-6"
            style={{ color: "var(--color-fg)" }}
          >
            NEXT LINKS
          </h2>
          <div className="flex flex-wrap gap-3">
            <a
              href={LINKS.startHere}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                backgroundColor: "var(--color-accent)",
                color: "var(--color-bg)",
              }}
            >
              GitHub start guide
            </a>
            <a
              href={LINKS.roadmap}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center px-5 py-3 font-mono text-xs uppercase tracking-widest"
              style={{
                border: "1px solid var(--color-border)",
                color: "var(--color-fg)",
              }}
            >
              Roadmap
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
              Discussions
            </a>
          </div>
        </section>
      </div>
    </main>
  );
}
