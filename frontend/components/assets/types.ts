export type { AssetCategoryKey } from "@/lib/assets/asset-category";
export {
  ASSET_CATEGORY_COLORS,
  ASSET_CATEGORY_LABELS,
} from "@/lib/assets/asset-category";

export type AssetType = "account" | "property" | "vehicle";

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
  key: import("@/lib/assets/asset-category").AssetCategoryKey;
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

export const PROPERTY_TYPES = [
  { value: "residential", label: "Residential" },
  { value: "commercial", label: "Commercial" },
  { value: "land", label: "Land" },
  { value: "other", label: "Other" },
] as const;

export const VEHICLE_TYPES = [
  { value: "car", label: "Car" },
  { value: "motorcycle", label: "Motorcycle" },
  { value: "boat", label: "Boat" },
  { value: "rv", label: "RV" },
  { value: "other", label: "Other" },
] as const;

export type PropertyType = typeof PROPERTY_TYPES[number]["value"];
export type VehicleType = typeof VEHICLE_TYPES[number]["value"];
