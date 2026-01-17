"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiAlertLine, RiRefreshLine } from "@remixicon/react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { resetOnboarding } from "@/lib/actions/settings";

export function ResetOnboardingDialog() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const handleReset = async () => {
    setIsLoading(true);

    try {
      const result = await resetOnboarding();

      if (result.success) {
        toast.success("Onboarding reset. Redirecting...");
        // Redirect to onboarding
        router.push("/step-1");
      } else {
        toast.error(result.error || "Failed to reset onboarding");
        setOpen(false);
      }
    } catch {
      toast.error("An error occurred. Please try again.");
      setOpen(false);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          <Button variant="outline" className="text-destructive hover:text-destructive">
            <RiRefreshLine className="mr-2 h-4 w-4" />
            Reset Onboarding
          </Button>
        }
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
              <RiAlertLine className="h-5 w-5 text-destructive" />
            </div>
            <AlertDialogTitle>Reset Onboarding</AlertDialogTitle>
          </div>
          <AlertDialogDescription className="pt-2">
            This action will:
            <ul className="mt-2 list-disc pl-6 space-y-1">
              <li>Delete all your custom categories</li>
              <li>Reset your onboarding status</li>
              <li>Redirect you to the onboarding flow</li>
            </ul>
            <p className="mt-3 font-medium text-foreground">
              Your accounts and transactions will not be affected.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleReset}
            disabled={isLoading}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isLoading ? "Resetting..." : "Reset Onboarding"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
