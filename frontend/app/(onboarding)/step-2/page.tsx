"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { RiArrowLeftLine, RiArrowRightLine, RiRefreshLine } from "@remixicon/react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { CategoryListEditor } from "@/components/onboarding/category-list-editor";
import {
  saveOnboardingCategories,
  getDefaultCategories,
  type CategoryInput,
} from "@/lib/actions/onboarding";
import { type DefaultCategory } from "@/lib/constants";

export default function Step2Page() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [categories, setCategories] = useState<CategoryInput[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    const loadDefaultCategories = async () => {
      const defaults = await getDefaultCategories();
      setCategories(
        defaults.map((cat: DefaultCategory) => ({
          name: cat.name,
          categoryType: cat.categoryType,
          color: cat.color,
          icon: cat.icon,
          description: cat.description,
          isSystem: cat.isSystem,
        }))
      );
      setIsInitialized(true);
    };
    loadDefaultCategories();
  }, []);

  const handleResetToDefaults = async () => {
    const defaults = await getDefaultCategories();
    setCategories(
      defaults.map((cat: DefaultCategory) => ({
        name: cat.name,
        categoryType: cat.categoryType,
        color: cat.color,
        icon: cat.icon,
        description: cat.description,
        isSystem: cat.isSystem,
      }))
    );
    toast.success("Categories reset to defaults");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate categories
    const validCategories = categories.filter((cat) => cat.name.trim());
    if (validCategories.length === 0) {
      toast.error("Please add at least one category");
      return;
    }

    // Check for duplicate names within each type
    const categoryTypes = ["expense", "income", "transfer"] as const;
    for (const type of categoryTypes) {
      const typeCategories = validCategories.filter((c) => c.categoryType === type);
      const names = typeCategories.map((c) => c.name.toLowerCase().trim());
      const duplicates = names.filter((name, index) => names.indexOf(name) !== index);
      if (duplicates.length > 0) {
        toast.error(`Duplicate category name "${duplicates[0]}" in ${type} categories`);
        return;
      }
    }

    setIsLoading(true);

    try {
      const result = await saveOnboardingCategories(validCategories);

      if (result.success) {
        toast.success("Categories saved");
        router.push("/step-3");
      } else {
        toast.error(result.error || "Failed to save categories");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  if (!isInitialized) {
    return (
      <div className="flex flex-col h-full">
        <OnboardingProgress currentStep={2} />
        <Card className="flex-1 mt-8">
          <CardContent className="flex h-64 items-center justify-center">
            <p className="text-muted-foreground">Loading categories...</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <OnboardingProgress currentStep={2} />

      <Card className="flex flex-col flex-1 mt-8 min-h-0">
        <CardHeader className="shrink-0">
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>Set up your categories</CardTitle>
              <CardDescription>
                Customize your spending and income categories. You can add, edit, or remove
                categories to match your needs.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleResetToDefaults}
            >
              <RiRefreshLine className="mr-2 h-4 w-4" />
              Reset
            </Button>
          </div>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent>
            <CategoryListEditor categories={categories} onChange={setCategories} />
          </CardContent>
          <CardFooter className="justify-between shrink-0 border-t pt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push("/step-1")}
            >
              <RiArrowLeftLine className="mr-2 h-4 w-4" />
              Back
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Saving..." : "Continue"}
              <RiArrowRightLine className="ml-2 h-4 w-4" />
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
