"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiArrowLeftLine, RiCheckLine } from "@remixicon/react";
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
import { BankConnectionCard } from "@/components/onboarding/bank-connection-card";
import { skipBankConnection, completeOnboarding } from "@/lib/actions/onboarding";

export default function Step3Page() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  const handleSkip = async () => {
    setIsLoading(true);
    try {
      const result = await skipBankConnection();
      if (result.success) {
        toast.success("Onboarding complete!");
        router.push("/");
      } else {
        toast.error(result.error || "Failed to complete onboarding");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    // TODO: Implement GoCardless bank connection flow
    // For now, just show a coming soon message
    toast.info("Bank connection will be available soon. Skipping for now...");

    try {
      const result = await completeOnboarding();
      if (result.success) {
        toast.success("Onboarding complete!");
        router.push("/");
      } else {
        toast.error(result.error || "Failed to complete onboarding");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={3} />

      <Card>
        <CardHeader>
          <CardTitle>Connect your bank (optional)</CardTitle>
          <CardDescription>
            Connect your bank account to automatically import transactions, or skip this step
            and add transactions manually later.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BankConnectionCard onConnect={handleConnect} isConnecting={isConnecting} />
        </CardContent>
        <CardFooter className="justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/step-2")}
            disabled={isLoading || isConnecting}
          >
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={handleSkip}
            disabled={isLoading || isConnecting}
          >
            {isLoading ? "Completing..." : "Skip for Now"}
            <RiCheckLine className="ml-2 h-4 w-4" />
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
