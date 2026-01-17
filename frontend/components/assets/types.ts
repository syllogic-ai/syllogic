export type AssetCategoryKey = "cash" | "investment" | "crypto" | "property" | "vehicle" | "other";

export interface AssetAccount {
  id: string;
  name: string;
  institution: string | null;
  value: number;
  percentage: number;
  currency: string;
  initial: string;
}

export interface AssetCategory {
  key: AssetCategoryKey;
  label: string;
  color: string;
  value: number;
  percentage: number;
  isActive: boolean;
  accounts: AssetAccount[];
}

export interface AssetsOverviewData {
  total: number;
  currency: string;
  categories: AssetCategory[];
}

export const ASSET_CATEGORY_COLORS: Record<AssetCategoryKey, string> = {
  cash: "#3B82F6",       // blue
  investment: "#10B981", // green
  crypto: "#F59E0B",     // amber
  property: "#8B5CF6",   // purple
  vehicle: "#EC4899",    // pink
  other: "#6B7280",      // gray
};

export const ASSET_CATEGORY_LABELS: Record<AssetCategoryKey, string> = {
  cash: "Cash",
  investment: "Investment",
  crypto: "Crypto",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};
