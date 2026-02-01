"use client";

import { RiDeleteBinLine, RiEditLine, RiLockLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { type CategoryInput } from "@/lib/actions/categories";

interface CategoryRowProps {
  category: CategoryInput;
  onEdit: () => void;
  onDelete: () => void;
}

export function CategoryRow({ category, onEdit, onDelete }: CategoryRowProps) {
  const isSystem = category.isSystem ?? false;

  return (
    <div className="flex items-center gap-3 py-2 px-1 hover:bg-muted/50 rounded">
      {/* Color dot */}
      <div
        className="h-4 w-4 rounded-full shrink-0"
        style={{ backgroundColor: category.color }}
      />

      {/* Name and description */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{category.name}</span>
          {isSystem && (
            <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              System
            </span>
          )}
        </div>
        {category.description && (
          <p className="text-sm text-muted-foreground truncate">
            {category.description}
          </p>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 shrink-0">
        {isSystem ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            disabled
            title="System category cannot be modified"
          >
            <RiLockLine className="h-4 w-4 text-muted-foreground" />
          </Button>
        ) : (
          <>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onEdit}
              title="Edit category"
            >
              <RiEditLine className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive"
              onClick={onDelete}
              title="Delete category"
            >
              <RiDeleteBinLine className="h-4 w-4" />
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
