export type Range = "1W" | "1M" | "3M" | "1Y" | "ALL";

export function rangeToDates(range: Range, now: Date = new Date()) {
  const to = now.toISOString().slice(0, 10);
  if (range === "ALL") return { from: "2010-01-01", to };
  const days = { "1W": 7, "1M": 30, "3M": 90, "1Y": 365 }[range];
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() - days);
  return { from: d.toISOString().slice(0, 10), to };
}
