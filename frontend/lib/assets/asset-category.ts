export type AssetCategoryKey =
  | "cash"
  | "savings"
  | "investment"
  | "crypto"
  | "property"
  | "vehicle"
  | "other";

export const ASSET_CATEGORY_ORDER: readonly AssetCategoryKey[] = [
  "cash",
  "savings",
  "investment",
  "crypto",
  "property",
  "vehicle",
  "other",
] as const;

export const ASSET_CATEGORY_LABELS: Record<AssetCategoryKey, string> = {
  cash: "Cash",
  savings: "Savings",
  investment: "Investment",
  crypto: "Crypto",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};

export const ASSET_CATEGORY_COLORS: Record<AssetCategoryKey, string> = {
  cash: "#3B82F6",       // blue
  savings: "#06B6D4",    // cyan — sibling of blue, distinct in net-worth stack
  investment: "#10B981", // green
  crypto: "#F59E0B",     // amber
  property: "#8B5CF6",   // purple
  vehicle: "#EC4899",    // pink
  other: "#6B7280",      // gray
};

const ACCOUNT_TYPE_TO_CATEGORY: Record<string, AssetCategoryKey> = {
  checking: "cash",
  savings: "savings",
  credit: "other",
  investment: "investment",
  brokerage: "investment",
  crypto: "crypto",
  property: "property",
  vehicle: "vehicle",
};

export function getAssetCategory(accountType: string): AssetCategoryKey {
  return ACCOUNT_TYPE_TO_CATEGORY[accountType.toLowerCase()] ?? "other";
}
