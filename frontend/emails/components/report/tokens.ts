/**
 * Email-safe hex equivalents of the app's oklch design tokens.
 *
 * globals.css uses oklch(), which no email client supports, so each token is
 * pinned to its hex equivalent. The palette is Tailwind's *stone* ramp (warm
 * grayscale) plus red for --destructive.
 */
export const light = {
  background: "#FFFFFF", // --background
  foreground: "#0C0A09", // --foreground  stone-950
  card: "#FFFFFF", // --card
  muted: "#F5F5F4", // --muted        stone-100
  mutedForeground: "#78716C", // --muted-foreground stone-500
  border: "#E7E5E4", // --border       stone-200
  primary: "#1C1917", // --primary      stone-900
  secondary: "#F5F5F4", // --secondary    stone-100 (page backdrop)
  destructive: "#DC2626", // --destructive  red-600
};

export const dark = {
  background: "#121110", // --background
  foreground: "#FAFAF9", // --foreground  stone-50
  card: "#1C1917", // --card         stone-900
  muted: "#292524", // --muted        stone-800
  mutedForeground: "#A8A29E", // --muted-foreground stone-400
  border: "#2E2A28", // --border      (opaque stand-in for white/10%)
  primary: "#E7E5E4", // --primary     stone-200
  secondary: "#292524", // --secondary   stone-800
  destructive: "#F87171", // --destructive red-400
};

/** --radius is 0 in globals.css: everything is square. */
export const radius = "0px";

/**
 * The UI is JetBrains Mono throughout. Webfonts only load in a minority of
 * clients, so the stack degrades to the local monospace face everywhere else,
 * preserving the monospace character without embedding a font.
 */
export const fontStack =
  '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';

/**
 * Shared by every component that prints an amount. Defined once so a
 * formatting change lands in all of them at once.
 *
 * Amounts arrive as strings (Decimal is not JSON-native); an unparseable value
 * is passed through rather than rendered as "NaN".
 */
export function fmtMoney(value: string, currency: string): string {
  const n = Number(value);
  if (value.trim() === "" || Number.isNaN(n)) return `${value} ${currency}`;
  return `${n.toLocaleString("en-IE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`;
}
