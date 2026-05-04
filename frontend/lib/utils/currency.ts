const SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
};

export function currencySymbol(code: string): string {
  const upper = code.toUpperCase();
  return SYMBOLS[upper] ?? upper;
}
