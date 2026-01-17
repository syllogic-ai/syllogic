"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CategoryColorPicker } from "./category-color-picker";
import { CATEGORY_COLORS } from "@/lib/constants";
import { type CategoryInput } from "@/lib/actions/onboarding";

interface CategoryFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryType: "expense" | "income" | "transfer";
  category?: CategoryInput | null;
  onSave: (category: CategoryInput) => void;
  existingCount?: number;
}

export function CategoryFormDialog({
  open,
  onOpenChange,
  categoryType,
  category,
  onSave,
  existingCount = 0,
}: CategoryFormDialogProps) {
  const isEditing = !!category;

  const [name, setName] = useState("");
  const [color, setColor] = useState<string>(CATEGORY_COLORS[0].value);
  const [description, setDescription] = useState("");
  const [categorizationInstructions, setCategorizationInstructions] = useState("");

  // Reset form when dialog opens or category changes
  useEffect(() => {
    if (open) {
      if (category) {
        setName(category.name);
        setColor(category.color);
        setDescription(category.description || "");
        setCategorizationInstructions(category.categorizationInstructions || "");
      } else {
        // New category - reset form with default color based on existing count
        setName("");
        setColor(CATEGORY_COLORS[existingCount % CATEGORY_COLORS.length].value);
        setDescription("");
        setCategorizationInstructions("");
      }
    }
  }, [open, category, existingCount]);

  const handleSave = () => {
    if (!name.trim() || !description.trim()) return;

    const updatedCategory: CategoryInput = {
      name: name.trim(),
      categoryType,
      color,
      icon: category?.icon || "RiFolderLine",
      description: description.trim(),
      categorizationInstructions: categorizationInstructions.trim() || undefined,
      isSystem: category?.isSystem,
    };

    onSave(updatedCategory);
    onOpenChange(false);
  };

  const getCategoryTypeLabel = () => {
    switch (categoryType) {
      case "expense":
        return "Expense";
      case "income":
        return "Income";
      case "transfer":
        return "Transfer";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Edit Category" : `Add ${getCategoryTypeLabel()} Category`}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update the category details below."
              : "Create a new category to organize your transactions."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <div className="flex items-center gap-3">
              <CategoryColorPicker value={color} onChange={setColor} />
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter category name"
                className="flex-1"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description *</Label>
            <Input
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this category"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="categorizationInstructions">Categorization Instructions</Label>
            <Textarea
              id="categorizationInstructions"
              value={categorizationInstructions}
              onChange={(e) => setCategorizationInstructions(e.target.value)}
              placeholder="Instructions for AI to categorize transactions into this category (optional)"
              rows={3}
            />
            <p className="text-xs text-muted-foreground">
              Help the AI understand when to use this category. E.g., "Include all coffee shop purchases and cafe visits"
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!name.trim() || !description.trim()}>
            {isEditing ? "Save Changes" : "Add Category"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
