import { RiEyeLine } from "@remixicon/react";

/**
 * Inline banner shown on settings panels when the current user is the
 * restricted demo account. Settings remain fully viewable but every
 * mutating control is disabled (and blocked server-side as a backstop).
 */
export function DemoReadOnlyNotice({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex items-center gap-2 border border-border bg-muted p-3 text-sm text-muted-foreground ${className}`}
    >
      <RiEyeLine className="h-4 w-4 shrink-0" />
      <span>
        You&apos;re exploring the demo account. Settings are read-only — changes
        are disabled.
      </span>
    </div>
  );
}
