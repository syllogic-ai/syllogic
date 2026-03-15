import Image from "next/image";

const SCREENSHOTS = [
  {
    label: "Dashboard Overview",
    wide: true,
    src: "/images/screenshots/dashboard.png",
    width: 3776,
    height: 1810,
  },
];

const WIDE_SCREENSHOT_SIZES =
  "(min-width: 1024px) calc(100vw - 12rem), calc(100vw - 4rem)";
const HALF_SCREENSHOT_SIZES =
  "(min-width: 1024px) calc((100vw - 12rem - 0.75rem) / 2), calc(100vw - 4rem)";

function ScreenshotPlaceholder({
  label,
  wide,
  src,
  width,
  height,
}: {
  label: string;
  wide?: boolean;
  src: string;
  width: number;
  height: number;
}) {
  return (
    <div
      className={`relative overflow-hidden ${wide ? "lg:col-span-2" : ""}`}
      style={{
        backgroundColor: "rgba(255,255,255,0.02)",
        border: "1px solid var(--color-border)",
      }}
    >
      {/* Fake browser chrome */}
      <div
        className="flex items-center gap-1.5 px-3"
        style={{
          height: "32px",
          borderBottom: "1px solid var(--color-border)",
          backgroundColor: "rgba(255,255,255,0.02)",
        }}
      >
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
          <div
            key={c}
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: c, opacity: 0.65 }}
          />
        ))}
        <div
          className="flex-1 mx-4 h-4 rounded-sm"
          style={{ backgroundColor: "rgba(255,255,255,0.08)" }}
        />
      </div>

      <Image
        src={src}
        alt={label}
        width={width}
        height={height}
        sizes={wide ? WIDE_SCREENSHOT_SIZES : HALF_SCREENSHOT_SIZES}
        className="block h-auto w-full"
      />
    </div>
  );
}

export function PreviewSection() {
  return (
    <section
      id="preview"
      className="py-24 px-8 lg:px-24"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      {/* Header */}
      <div className="flex items-baseline gap-4 mb-16">
        <span
          className="font-mono text-sm"
          style={{ color: "var(--color-accent)" }}
        >
          02
        </span>
        <h2
          className="font-display text-5xl"
          style={{ color: "var(--color-fg)" }}
        >
          PREVIEW
        </h2>
      </div>

      {/* Screenshots grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {SCREENSHOTS.map(({ label, wide, src, width, height }) => (
          <ScreenshotPlaceholder
            key={label}
            label={label}
            wide={wide}
            src={src}
            width={width}
            height={height}
          />
        ))}
      </div>
    </section>
  );
}
