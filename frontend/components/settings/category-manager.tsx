"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiAddLine } from "@remixicon/react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CategoryRow } from "@/components/onboarding/category-row";
import { CategoryFormDialog } from "@/components/onboarding/category-form-dialog";
import {
  createCategory,
  updateCategory,
  deleteCategory as deleteCategoryAction,
  type CategoryCreateInput,
  type CategoryUpdateInput,
} from "@/lib/actions/categories";
import type { Category } from "@/lib/db/schema";
import { type CategoryInput } from "@/lib/actions/onboarding";
import { groupCategoriesByType, getCategoryTypeLabel, type CategoryType } from "@/lib/utils/category-utils";

interface CategoryManagerProps {
  initialCategories: Category[];
}

export function CategoryManager({ initialCategories }: CategoryManagerProps) {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>(initialCategories);
  const [activeTab, setActiveTab] = useState<CategoryType>("expense");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const groupedCategories = groupCategoriesByType(categories);

  const getCategoriesByType = (type: CategoryType) => groupedCategories[type];

  const handleEdit = (category: Category) => {
    setEditingCategory(category);
    setDialogOpen(true);
  };

  const handleDelete = async (category: Category) => {
    if (category.isSystem) {
      toast.error("System categories cannot be deleted");
      return;
    }

    setIsLoading(true);
    try {
      const result = await deleteCategoryAction(category.id);
      if (result.success) {
        setCategories(categories.filter((c) => c.id !== category.id));
        toast.success("Category deleted");
        router.refresh();
      } else {
        toast.error(result.error || "Failed to delete category");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddClick = (type: "expense" | "income" | "transfer") => {
    setEditingCategory(null);
    setActiveTab(type);
    setDialogOpen(true);
  };

  const handleSaveCategory = async (categoryInput: CategoryInput) => {
    setIsLoading(true);
    try {
      if (editingCategory) {
        // Update existing category
        const updateData: CategoryUpdateInput = {
          name: categoryInput.name,
          color: categoryInput.color,
          icon: categoryInput.icon,
          description: categoryInput.description,
          categorizationInstructions: categoryInput.categorizationInstructions,
        };

        const result = await updateCategory(editingCategory.id, updateData);
        if (result.success) {
          // Update local state
          setCategories(categories.map((c) =>
            c.id === editingCategory.id
              ? {
                  ...c,
                  name: categoryInput.name,
                  color: categoryInput.color,
                  icon: categoryInput.icon,
                  description: categoryInput.description || null,
                  categorizationInstructions: categoryInput.categorizationInstructions || null,
                }
              : c
          ));
          toast.success("Category updated");
          router.refresh();
        } else {
          toast.error(result.error || "Failed to update category");
        }
      } else {
        // Create new category
        const createData: CategoryCreateInput = {
          name: categoryInput.name,
          categoryType: categoryInput.categoryType,
          color: categoryInput.color,
          icon: categoryInput.icon,
          description: categoryInput.description,
          categorizationInstructions: categoryInput.categorizationInstructions,
        };

        const result = await createCategory(createData);
        if (result.success && result.categoryId) {
          // Add to local state
          const newCategory: Category = {
            id: result.categoryId,
            userId: "", // Will be filled by server
            name: categoryInput.name,
            parentId: null,
            categoryType: categoryInput.categoryType,
            color: categoryInput.color,
            icon: categoryInput.icon,
            description: categoryInput.description || null,
            categorizationInstructions: categoryInput.categorizationInstructions || null,
            isSystem: false,
            createdAt: new Date(),
          };
          setCategories([...categories, newCategory]);
          toast.success("Category created");
          router.refresh();
        } else {
          toast.error(result.error || "Failed to create category");
        }
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
      setDialogOpen(false);
    }
  };

  const categoryToInput = (category: Category | null): CategoryInput | null => {
    if (!category) return null;
    return {
      name: category.name,
      categoryType: category.categoryType as "expense" | "income" | "transfer",
      color: category.color || "#6b7280",
      icon: category.icon || "RiFolderLine",
      description: category.description || undefined,
      categorizationInstructions: category.categorizationInstructions || undefined,
      isSystem: category.isSystem || false,
    };
  };

  const renderCategoryList = (
    categoryList: Category[],
    categoryType: "expense" | "income" | "transfer"
  ) => {
    return (
      <div className="flex flex-col">
        {/* Category list */}
        <div className="space-y-1 min-h-[200px] max-h-[400px] overflow-y-auto">
          {categoryList.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded border border-dashed">
              <p className="text-sm text-muted-foreground">No categories yet</p>
            </div>
          ) : (
            categoryList.map((category) => {
              const input = categoryToInput(category);
              if (!input) return null;
              return (
                <CategoryRow
                  key={category.id}
                  category={input}
                  onEdit={() => handleEdit(category)}
                  onDelete={() => handleDelete(category)}
                />
              );
            })
          )}
        </div>

        {/* Add button */}
        <div className="pt-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => handleAddClick(categoryType)}
            disabled={isLoading}
          >
            <RiAddLine className="mr-2 h-4 w-4" />
            Add {getCategoryTypeLabel(categoryType)} Category
          </Button>
        </div>
      </div>
    );
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Categories</CardTitle>
          <CardDescription>
            Manage your transaction categories. Categories help you organize and track your spending.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as CategoryType)}
          >
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="expense">
                Expenses ({groupedCategories.expense.length})
              </TabsTrigger>
              <TabsTrigger value="income">
                Income ({groupedCategories.income.length})
              </TabsTrigger>
              <TabsTrigger value="transfer">
                Transfers ({groupedCategories.transfer.length})
              </TabsTrigger>
            </TabsList>
            <TabsContent value="expense" className="mt-4">
              {renderCategoryList(groupedCategories.expense, "expense")}
            </TabsContent>
            <TabsContent value="income" className="mt-4">
              {renderCategoryList(groupedCategories.income, "income")}
            </TabsContent>
            <TabsContent value="transfer" className="mt-4">
              {renderCategoryList(groupedCategories.transfer, "transfer")}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <CategoryFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        categoryType={activeTab}
        category={categoryToInput(editingCategory)}
        onSave={handleSaveCategory}
        existingCount={getCategoriesByType(activeTab).length}
      />
    </>
  );
}
