"use client";

import { useState } from "react";
import { RiAddLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { CategoryRow } from "./category-row";
import { CategoryFormDialog } from "./category-form-dialog";
import { type CategoryInput } from "@/lib/actions/categories";
import { groupCategoriesByType, type CategoryType } from "@/lib/utils/category-utils";

interface CategoryListEditorProps {
  categories: CategoryInput[];
  onChange: (categories: CategoryInput[]) => void;
}

interface CategoryGroup {
  type: CategoryType;
  label: string;
  categories: CategoryInput[];
}

export function CategoryListEditor({ categories, onChange }: CategoryListEditorProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryInput | null>(null);
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [addingType, setAddingType] = useState<CategoryType>("expense");

  const groupedCategories = groupCategoriesByType(categories);

  const groups: CategoryGroup[] = [
    { type: "expense", label: "Expenses", categories: groupedCategories.expense },
    { type: "income", label: "Income", categories: groupedCategories.income },
    { type: "transfer", label: "Transfers", categories: groupedCategories.transfer },
  ];

  const getCategoriesByType = (type: CategoryType) => groupedCategories[type];

  const handleEdit = (category: CategoryInput, globalIndex: number) => {
    setEditingCategory(category);
    setEditingIndex(globalIndex);
    setDialogOpen(true);
  };

  const handleDelete = (category: CategoryInput) => {
    if (category && !category.isSystem) {
      onChange(categories.filter((c) => c !== category));
    }
  };

  const handleAddClick = (type: "expense" | "income" | "transfer") => {
    setEditingCategory(null);
    setEditingIndex(-1);
    setAddingType(type);
    setDialogOpen(true);
  };

  const handleSaveCategory = (updatedCategory: CategoryInput) => {
    if (editingCategory) {
      // Editing existing category
      const newCategories = [...categories];
      newCategories[editingIndex] = updatedCategory;
      onChange(newCategories);
    } else {
      // Adding new category
      onChange([...categories, updatedCategory]);
    }
  };

  return (
    <>
      <div className="space-y-6 overflow-y-auto max-h-[500px] pr-2">
        {groups.map((group) => (
          <div key={group.type}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-muted-foreground">
                {group.label} ({group.categories.length})
              </h3>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => handleAddClick(group.type)}
              >
                <RiAddLine className="mr-1 h-3 w-3" />
                Add
              </Button>
            </div>
            <div className="space-y-1 border rounded-md p-2">
              {group.categories.length === 0 ? (
                <div className="flex h-12 items-center justify-center">
                  <p className="text-sm text-muted-foreground">No categories</p>
                </div>
              ) : (
                group.categories.map((category) => {
                  const globalIndex = categories.indexOf(category);
                  return (
                    <CategoryRow
                      key={`${category.name}-${globalIndex}`}
                      category={category}
                      onEdit={() => handleEdit(category, globalIndex)}
                      onDelete={() => handleDelete(category)}
                    />
                  );
                })
              )}
            </div>
          </div>
        ))}
      </div>

      <CategoryFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        categoryType={editingCategory?.categoryType || addingType}
        category={editingCategory}
        onSave={handleSaveCategory}
        existingCount={getCategoriesByType(editingCategory?.categoryType || addingType).length}
      />
    </>
  );
}
