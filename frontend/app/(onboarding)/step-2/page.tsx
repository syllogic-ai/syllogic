"use client";

import { useState, useTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { RiArrowLeftLine, RiArrowRightLine, RiLoader4Line, RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { CategoryListEditor } from "@/components/onboarding/category-list-editor";
import {
  saveOnboardingCategories,
  getDefaultCategories,
  type CategoryInput,
} from "@/lib/actions/onboarding";
import { DEFAULT_CATEGORIES } from "@/lib/constants/default-categories";

export default function OnboardingStep2Page() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [categories, setCategories] = useState<CategoryInput[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Load default categories on mount
  useEffect(() => {
    async function loadCategories() {
      try {
        const defaultCats = await getDefaultCategories();
        setCategories(
          defaultCats.map((cat) => ({
            name: cat.name,
            categoryType: cat.categoryType,
            color: cat.color,
            icon: cat.icon,
            description: cat.description,
            isSystem: cat.isSystem,
            hideFromSelection: cat.hideFromSelection,
          }))
        );
      } catch (error) {
        console.error("Failed to load categories:", error);
        // Fall back to local constants
        setCategories(
          DEFAULT_CATEGORIES.map((cat) => ({
            name: cat.name,
            categoryType: cat.categoryType,
            color: cat.color,
            icon: cat.icon,
            description: cat.description,
            isSystem: cat.isSystem,
            hideFromSelection: cat.hideFromSelection,
          }))
        );
      } finally {
        setIsLoading(false);
      }
    }
    loadCategories();
  }, []);

  const handleResetToDefaults = () => {
    setCategories(
      DEFAULT_CATEGORIES.map((cat) => ({
        name: cat.name,
        categoryType: cat.categoryType,
        color: cat.color,
        icon: cat.icon,
        description: cat.description,
        isSystem: cat.isSystem,
        hideFromSelection: cat.hideFromSelection,
      }))
    );
    toast.success("Categories reset to defaults");
  };

  const handleSubmit = async () => {
    if (categories.length === 0) {
      toast.error("Please add at least one category");
      return;
    }

    startTransition(async () => {
      const result = await saveOnboardingCategories(categories);

      if (result.success) {
        router.push("/step-3");
      } else {
        toast.error(result.error || "Failed to save categories");
      }
    });
  };

  const handleBack = () => {
    router.push("/step-1");
  };

  if (isLoading) {
    return (
      <div className="space-y-8">
        <OnboardingProgress currentStep={2} />
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <RiLoader4Line className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={2} />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Set up your categories</CardTitle>
              <CardDescription>
                Customize how you want to organize your transactions. You can add
                categorization instructions to help the AI categorize your transactions
                automatically.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleResetToDefaults}>
              <RiRefreshLine className="mr-2 h-4 w-4" />
              Reset to Defaults
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <CategoryListEditor categories={categories} onChange={setCategories} />
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handleBack}>
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={handleSubmit} disabled={isPending || categories.length === 0}>
            {isPending ? (
              <>
                <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                Continue
                <RiArrowRightLine className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
