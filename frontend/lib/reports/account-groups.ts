import {
  ASSET_CATEGORY_LABELS,
  ASSET_CATEGORY_ORDER,
  getAssetCategory,
  type AssetCategoryKey,
} from "@/lib/assets/asset-category";

export type PickerAccount = {
  id: string;
  name: string;
  account_type: string;
  institution: string | null;
  is_active: boolean;
};

export type AccountGroup = {
  key: AssetCategoryKey;
  label: string;
  accounts: PickerAccount[];
};

/**
 * Groups accounts for the report picker.
 *
 * Reuses the asset-category map rather than introducing a fourth account-type
 * taxonomy: it already covers investment_brokerage / investment_manual, which
 * the ACCOUNT_TYPES lists elsewhere in the codebase do not.
 */
export function groupAccounts(accounts: PickerAccount[]): AccountGroup[] {
  const buckets = new Map<AssetCategoryKey, PickerAccount[]>();
  for (const account of accounts) {
    const key = getAssetCategory(account.account_type);
    const existing = buckets.get(key);
    if (existing) existing.push(account);
    else buckets.set(key, [account]);
  }

  return ASSET_CATEGORY_ORDER.filter((key) => buckets.has(key)).map((key) => ({
    key,
    label: ASSET_CATEGORY_LABELS[key],
    accounts: buckets.get(key)!,
  }));
}
