import { SplitFlapText } from "./split-flap-text";
import { BitmapChevron } from "./bitmap-chevron";
import { DrawText } from "./draw-text";

export function HeroSection() {
  return (
    <section
      id="hero"
      className="relative min-h-screen flex flex-col justify-center px-8 lg:px-24 pt-20 pb-16"
    >
      {/* Top label */}
      <p className="text-xs font-mono uppercase tracking-[0.25em] mb-10 overflow-hidden"
        style={{ color: "var(--color-muted)" }}>
        <DrawText>OPEN SOURCE · SELF-HOSTED · PERSONAL FINANCE</DrawText>
      </p>

      {/* Main heading */}
      <h1
        className="font-display leading-none mb-8"
        style={{
          fontSize: "clamp(4rem, 14vw, 13rem)",
          color: "var(--color-fg)",
        }}
      >
        <SplitFlapText text="SYLLOGIC" startDelay={400} charDelay={100} />
      </h1>

      {/* Sub-tagline */}
      <div
        className="font-mono text-base leading-relaxed max-w-lg mb-12"
        style={{ color: "var(--color-fg)" }}
      >
        <p>
          Manage your wealth. Reach financial freedom.
        </p>
        <p style={{ color: "var(--color-muted)" }}>
          Your data stays on your hardware.
        </p>
      </div>

      {/* CTAs */}
      <div className="flex flex-wrap items-center gap-4">
        <a
          href="#deploy"
          className="inline-flex items-center gap-2 px-6 py-3 font-mono text-sm uppercase tracking-widest transition-opacity hover:opacity-80"
          style={{
            backgroundColor: "var(--color-accent)",
            color: "var(--color-bg)",
          }}
        >
          Deploy Now
          <BitmapChevron className="-rotate-90" size={9} />
        </a>
        <a
          href="https://app.syllogic.ai/login?demo=true"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-6 py-3 font-mono text-sm uppercase tracking-widest transition-colors hover:border-fg"
          style={{
            border: "1px solid var(--color-border)",
            color: "var(--color-fg)",
          }}
        >
          View Demo
          <BitmapChevron className="-rotate-90" size={9} />
        </a>
      </div>

      {/* Scroll hint */}
      <div
        className="absolute bottom-8 left-8 lg:left-24 flex items-center gap-2 text-xs font-mono uppercase tracking-widest"
        style={{ color: "var(--color-muted)" }}
      >
        <span>Scroll</span>
        <BitmapChevron size={8} />
      </div>
    </section>
  );
}
