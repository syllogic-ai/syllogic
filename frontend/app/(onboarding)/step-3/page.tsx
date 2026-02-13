"use client";

import { useState, useTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiLoader4Line,
  RiBankLine,
  RiAddLine,
} from "@remixicon/react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { AccountForm } from "@/components/accounts/account-form";
import { completeOnboarding } from "@/lib/actions/onboarding";
import { getAccounts } from "@/lib/actions/accounts";
import type { Account } from "@/lib/db/schema";

export default function OnboardingStep3Page() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const loadAccounts = async () => {
    try {
      const accountList = await getAccounts();
      setAccounts(accountList);
    } catch (error) {
      console.error("Failed to load accounts:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const handleComplete = async () => {
    if (accounts.length === 0) {
      toast.error("Please create at least one account to continue");
      return;
    }

    startTransition(async () => {
      const result = await completeOnboarding();

      if (result.success) {
        router.push("/step-4");
      } else {
        toast.error(result.error || "Failed to complete onboarding");
      }
    });
  };

  const handleBack = () => {
    router.push("/step-2");
  };

  if (isLoading) {
    return (
      <div className="space-y-8">
        <OnboardingProgress currentStep={3} />
        <Card className="min-h-[640px] h-[640px] flex flex-col">
          <CardContent className="flex items-center justify-center py-12">
            <RiLoader4Line className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={3} />

      <Card className="min-h-[640px] h-[640px] flex flex-col">
        <CardHeader>
          <CardTitle>Set up your first bank account</CardTitle>
          <CardDescription>
            We&apos;re starting with CSV import only. Create your first account to
            begin importing transactions.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 min-h-0">
          <div className="space-y-6">
            {accounts.length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">Accounts created</p>
                <div className="space-y-2">
                  {accounts.map((account) => (
                    <div
                      key={account.id}
                      className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                    >
                      <span className="font-medium">{account.name}</span>
                      <span className="text-muted-foreground">
                        {account.currency} - {account.accountType}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10 text-center space-y-4">
                <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                  <RiBankLine className="h-8 w-8 text-muted-foreground" />
                </div>
                <div className="space-y-2">
                  <h3 className="font-medium">No accounts yet</h3>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Create one account to start importing your transactions via CSV.
                  </p>
                </div>
              </div>
            )}

            <Button onClick={() => setIsDialogOpen(true)} className="w-full" size="lg">
              <RiAddLine className="mr-2 h-4 w-4" />
              {accounts.length > 0 ? "Add another account" : "Create your first account"}
            </Button>
          </div>
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handleBack}>
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={handleComplete} disabled={isPending || accounts.length === 0}>
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

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Create Account</DialogTitle>
          </DialogHeader>
          <AccountForm
            onSuccess={() => {
              setIsDialogOpen(false);
              loadAccounts();
            }}
            onCancel={() => setIsDialogOpen(false)}
            submitLabel="Create Account"
            successMessage="Account created successfully"
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
