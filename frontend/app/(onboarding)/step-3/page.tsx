"use client";

import { useState, useTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  RiArrowLeftLine,
  RiCheckLine,
  RiLoader4Line,
  RiBankLine,
  RiSkipForwardLine,
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
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { ConnectBankButton } from "@/components/bank-connect/connect-bank-button";
import { BankConnectionStatus } from "@/components/bank-connect/bank-connection-status";
import { completeOnboarding } from "@/lib/actions/onboarding";
import { getBankConnections, type BankConnection } from "@/lib/actions/bank-connections";

export default function OnboardingStep3Page() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [connections, setConnections] = useState<BankConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Load bank connections on mount
  useEffect(() => {
    loadConnections();
  }, []);

  const loadConnections = async () => {
    try {
      const bankConnections = await getBankConnections();
      setConnections(bankConnections);
    } catch (error) {
      console.error("Failed to load bank connections:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleComplete = async () => {
    startTransition(async () => {
      const result = await completeOnboarding();

      if (result.success) {
        toast.success("Onboarding complete! Welcome to your finance dashboard.");
        router.push("/");
      } else {
        toast.error(result.error || "Failed to complete onboarding");
      }
    });
  };

  const handleBack = () => {
    router.push("/step-2");
  };

  const hasConnections = connections.length > 0;

  if (isLoading) {
    return (
      <div className="space-y-8">
        <OnboardingProgress currentStep={3} />
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
      <OnboardingProgress currentStep={3} />

      <Card>
        <CardHeader>
          <CardTitle>Connect your bank accounts</CardTitle>
          <CardDescription>
            Link your bank accounts to automatically import and categorize your
            transactions. This step is optional - you can skip it and add accounts
            manually later.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {hasConnections ? (
            <div className="space-y-4">
              {connections.map((connection) => (
                <BankConnectionStatus
                  key={connection.id}
                  connection={connection}
                  onUpdate={loadConnections}
                />
              ))}
              <div className="flex justify-center pt-4">
                <ConnectBankButton variant="outline" />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 space-y-6">
              <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                <RiBankLine className="h-8 w-8 text-muted-foreground" />
              </div>
              <div className="text-center space-y-2">
                <h3 className="font-medium">No bank accounts connected</h3>
                <p className="text-sm text-muted-foreground max-w-md">
                  Connect your bank to automatically sync your transactions. We use
                  secure open banking protocols to keep your data safe.
                </p>
              </div>
              <ConnectBankButton size="lg" />
            </div>
          )}
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handleBack}>
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={handleComplete} disabled={isPending}>
            {isPending ? (
              <>
                <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
                Completing...
              </>
            ) : hasConnections ? (
              <>
                <RiCheckLine className="mr-2 h-4 w-4" />
                Complete Setup
              </>
            ) : (
              <>
                <RiSkipForwardLine className="mr-2 h-4 w-4" />
                Skip for Now
              </>
            )}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
