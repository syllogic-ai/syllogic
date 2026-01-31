"use client";

import { useState } from "react";
import { RiArrowDownSLine, RiArrowRightSLine } from "@remixicon/react";
import { formatCurrency } from "@/lib/utils";
import { WeightBarVisualizer } from "./weight-bar-visualizer";
import type { AssetCategory, AssetAccount, AssetCategoryKey } from "./types";

interface AssetsTableProps {
  categories: AssetCategory[];
  currency: string;
}

// Asset categories that are bank accounts (navigable to account detail)
const ACCOUNT_CATEGORY_KEYS: AssetCategoryKey[] = ["cash", "investment", "crypto"];

function AccountRow({
  account,
  currency,
  color,
  isLinkable = false,
}: {
  account: AssetAccount;
  currency: string;
  color: string;
  isLinkable?: boolean;
}) {
  const handleClick = () => {
    if (isLinkable) {
      window.location.href = `/accounts/${account.id}`;
    }
  };

  return (
    <div
      className={`flex items-center py-2 pl-8 pr-4 border-t border-border/50 ${isLinkable ? "hover:bg-muted/50 cursor-pointer transition-colors" : ""}`}
      onClick={handleClick}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <div
          className="h-3 w-3 shrink-0 rounded-sm"
          style={{ backgroundColor: color }}
        />
        <div className="truncate">
          <span className="text-sm">{account.name}</span>
          {account.institution && (
            <span className="text-xs text-muted-foreground ml-2">
              {account.institution}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        <div className="flex items-center gap-2 w-36">
          <WeightBarVisualizer percentage={account.percentage} color={color} />
          <span className="text-sm text-muted-foreground w-12 text-right">
            {account.percentage.toFixed(0)}%
          </span>
        </div>
        <span className="text-sm font-medium w-24 text-right">
          {formatCurrency(account.value, currency)}
        </span>
      </div>
    </div>
  );
}

function CategoryRow({
  category,
  currency,
  defaultOpen = false,
}: {
  category: AssetCategory;
  currency: string;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const hasAccounts = category.accounts.length > 0;

  if (!category.isActive) {
    return (
      <div className="flex items-center py-3 px-4 border-t">
        <div className="flex items-center gap-2 flex-1">
          <div className="w-4 h-4" /> {/* Spacer for alignment */}
          <span className="text-sm text-muted-foreground">{category.label}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground w-36 text-center">-</span>
          <span className="text-sm text-muted-foreground w-24 text-right">
            {formatCurrency(0, currency)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        className="flex items-center py-3 px-4 border-t cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => hasAccounts && setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2 flex-1">
          {hasAccounts ? (
            isOpen ? (
              <RiArrowDownSLine className="h-4 w-4 text-muted-foreground" />
            ) : (
              <RiArrowRightSLine className="h-4 w-4 text-muted-foreground" />
            )
          ) : (
            <div className="w-4 h-4" />
          )}
          <span className="text-sm font-medium">{category.label}</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 w-36">
            <WeightBarVisualizer
              percentage={category.percentage}
              color={category.color}
            />
            <span className="text-sm text-muted-foreground w-12 text-right">
              {category.percentage.toFixed(0)}%
            </span>
          </div>
          <span className="text-sm font-medium w-24 text-right">
            {formatCurrency(category.value, currency)}
          </span>
        </div>
      </div>
      {hasAccounts && isOpen && (
        <div>
          {category.accounts.map((account) => (
            <AccountRow
              key={account.id}
              account={account}
              currency={currency}
              color={category.color}
              isLinkable={ACCOUNT_CATEGORY_KEYS.includes(category.key)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function AssetsTable({ categories, currency }: AssetsTableProps) {
  return (
    <div className="rounded-md border">
      {/* Header */}
      <div className="flex items-center py-2 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">
        <div className="flex-1">Name</div>
        <div className="w-36 text-center">Weight</div>
        <div className="w-24 text-right">Value</div>
      </div>

      {/* Rows */}
      {categories.map((category, index) => (
        <CategoryRow
          key={category.key}
          category={category}
          currency={currency}
          defaultOpen={index === 0 && category.isActive}
        />
      ))}
    </div>
  );
}
