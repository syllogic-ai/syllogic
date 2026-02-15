"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { RiArrowLeftLine, RiArrowRightLine } from "@remixicon/react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { CsvUploadDropzone } from "@/components/transactions/csv-upload-dropzone";
import { getUserAccounts } from "@/lib/actions/transactions";
import { initializeCsvImport } from "@/lib/actions/csv-import";
import type { Account } from "@/lib/db/schema";

export default function StepFourImportPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileContent, setFileContent] = useState<string>("");

  useEffect(() => {
    const loadAccounts = async () => {
      const accountsData = await getUserAccounts();
      setAccounts(accountsData);
      if (accountsData.length > 0) {
        setSelectedAccountId(accountsData[0].id);
      }
    };
    loadAccounts();
  }, []);

  const handleFileSelect = (file: File, content: string) => {
    setSelectedFile(file);
    setFileContent(content);
  };

  const handleContinue = async () => {
    if (!selectedAccountId) {
      toast.error("Please select an account");
      return;
    }

    if (!selectedFile || !fileContent) {
      toast.error("Please upload a file");
      return;
    }

    setIsLoading(true);

    try {
      const result = await initializeCsvImport(
        selectedAccountId,
        selectedFile.name,
        fileContent
      );

      if (result.success && result.importId) {
        router.push(`/step-4/mapping?id=${result.importId}`);
      } else {
        toast.error(result.error || "Failed to initialize import");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleBack = () => {
    router.push("/step-3");
  };

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={4} />
      <Card className="min-h-[640px] h-[640px] flex flex-col">
        <CardHeader>
          <CardTitle>Import your transactions</CardTitle>
          <CardDescription>
            Upload a CSV or Excel file. We&apos;ll help you map the columns to the
            correct fields.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 space-y-6">
          <div className="space-y-2">
            <Label>Select Account</Label>
            {accounts.length === 0 ? (
              <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground space-y-2">
                <p>No accounts found. Create one first to continue.</p>
                <Button
                  type="button"
                  variant="link"
                  className="h-auto p-0 text-xs"
                  onClick={() => router.push("/step-3")}
                >
                  Go to Bank Accounts
                </Button>
              </div>
            ) : (
              <Select value={selectedAccountId} onValueChange={(v) => v && setSelectedAccountId(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select an account">
                    {accounts.find((a) => a.id === selectedAccountId)?.name ?? "Select an account"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="w-auto min-w-[var(--anchor-width)] max-w-[90vw]">
                  {accounts.map((account) => (
                    <SelectItem key={account.id} value={account.id} className="pr-10">
                      {account.name} ({account.currency})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-2">
            <Label>Upload File</Label>
            <CsvUploadDropzone onFileSelect={handleFileSelect} isUploading={isLoading} />
          </div>
        </CardContent>
        <CardFooter className="justify-between">
          <Button type="button" variant="outline" onClick={handleBack}>
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button
            onClick={handleContinue}
            disabled={isLoading || !selectedFile || accounts.length === 0}
          >
            {isLoading ? "Processing..." : "Continue"}
            <RiArrowRightLine className="ml-2 h-4 w-4" />
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
