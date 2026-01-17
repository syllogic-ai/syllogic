"use client";

import type { AssetCategory } from "./types";

interface AssetsStackedBarProps {
  categories: AssetCategory[];
  total: number;
}

export function AssetsStackedBar({ categories, total }: AssetsStackedBarProps) {
  const activeCategories = categories.filter((cat) => cat.isActive && cat.value > 0);

  if (activeCategories.length === 0) {
    return (
      <div className="space-y-4">
        <div className="h-3 w-full rounded-sm bg-muted" />
        <div className="text-sm text-muted-foreground">No assets tracked</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stacked Bar */}
      <div className="flex h-3 w-full overflow-hidden rounded-sm">
        {activeCategories.map((category) => (
          <div
            key={category.key}
            className="h-full transition-all"
            style={{
              width: `${category.percentage}%`,
              backgroundColor: category.color,
            }}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {activeCategories.map((category) => (
          <div key={category.key} className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-sm"
              style={{ backgroundColor: category.color }}
            />
            <span className="text-sm text-muted-foreground">
              {category.label}
            </span>
            <span className="text-sm font-medium">
              {category.percentage.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
