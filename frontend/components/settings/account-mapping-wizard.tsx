"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  RiBankLine,
  RiAddLine,
  RiLinkM,
  RiArrowRightLine,
  RiArrowLeftLine,
  RiLoader4Line,
  RiCheckLine,
  RiAlertLine,
} from "@remixicon/react";
import { submitAccountMappings } from "@/lib/actions/bank-connections";

interface BankAccount {
  uid: string;
  name: string;
  iban: string;
  currency: string;
  accountType: string;
}

interface LinkableAccount {
  id: string;
  name: string;
  currency: string | null;
  accountType: string | null;
  institution: string | null;
  bankConnectionId: string | null;
}

interface AccountMapping {
  bank_uid: string;
  action: "create" | "link";
  name?: string;
  existing_account_id?: string;
}

interface AccountMappingWizardProps {
  connectionId: string;
  aspspName: string;
  bankAccounts: BankAccount[];
  linkableAccounts: LinkableAccount[];
}

function maskIban(iban: string): string {
  if (!iban || iban.length < 8) return iban;
  return iban.slice(0, 4) + " •••• " + iban.slice(-4);
}

const SYNC_DAY_OPTIONS = [30, 60, 90, 180, 365, 730];

export function AccountMappingWizard({
  connectionId,
  aspspName,
  bankAccounts,
  linkableAccounts,
}: AccountMappingWizardProps) {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0);
  const [mappings, setMappings] = useState<AccountMapping[]>(
    bankAccounts.map((account) => ({
      bank_uid: account.uid,
      action: "create" as const,
      name: account.name,
    }))
  );
  const [initialSyncDays, setInitialSyncDays] = useState(90);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSummaryStep = currentStep === bankAccounts.length;
  const currentAccount = !isSummaryStep ? bankAccounts[currentStep] : null;
  const currentMapping = !isSummaryStep ? mappings[currentStep] : null;

  // Accounts already selected in other steps (for "link" action)
  const selectedAccountIds = mappings
    .filter((m, i) => i !== currentStep && m.action === "link" && m.existing_account_id)
    .map((m) => m.existing_account_id as string);

  const availableLinkableAccounts = linkableAccounts.filter(
    (a) => !selectedAccountIds.includes(a.id)
  );

  function updateCurrentMapping(patch: Partial<AccountMapping>) {
    setMappings((prev) =>
      prev.map((m, i) => (i === currentStep ? { ...m, ...patch } : m))
    );
  }

  function handleActionSelect(action: "create" | "link") {
    if (action === "create") {
      updateCurrentMapping({
        action: "create",
        name: currentAccount?.name || "",
        existing_account_id: undefined,
      });
    } else {
      updateCurrentMapping({
        action: "link",
        name: undefined,
        existing_account_id: undefined,
      });
    }
  }

  function canProceed(): boolean {
    if (!currentMapping) return true;
    if (currentMapping.action === "create") {
      return !!(currentMapping.name && currentMapping.name.trim().length > 0);
    }
    return !!currentMapping.existing_account_id;
  }

  async function handleSubmit() {
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await submitAccountMappings(
        connectionId,
        mappings,
        initialSyncDays
      );
      if (!result.success) {
        setError(result.error || "Failed to submit account mappings");
        setIsSubmitting(false);
        return;
      }
      router.push("/settings?tab=bank-connections");
    } catch {
      setError("An unexpected error occurred");
      setIsSubmitting(false);
    }
  }

  // Progress indicator
  const totalSteps = bankAccounts.length + 1; // +1 for summary
  const progressPercent = ((currentStep + 1) / totalSteps) * 100;

  return (
    <div className="mx-auto w-full max-w-2xl py-6">
      {/* Progress bar */}
      <div className="mb-6">
        <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {isSummaryStep
              ? "Review & Confirm"
              : `Account ${currentStep + 1} of ${bankAccounts.length}`}
          </span>
          <span>{Math.round(progressPercent)}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Header info */}
      <div className="mb-6 flex items-center gap-2">
        <RiBankLine className="h-5 w-5 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          Connecting to{" "}
          <span className="font-medium text-foreground">{aspspName}</span>
        </span>
      </div>

      {/* Step: per-account mapping */}
      {!isSummaryStep && currentAccount && currentMapping && (
        <div className="space-y-4">
          {/* Bank account details */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{currentAccount.name}</CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-2">
                {currentAccount.iban && (
                  <span>{maskIban(currentAccount.iban)}</span>
                )}
                <Badge variant="secondary">{currentAccount.currency}</Badge>
                <Badge variant="outline">{currentAccount.accountType}</Badge>
              </CardDescription>
            </CardHeader>
          </Card>

          {/* Action selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">
              What would you like to do with this account?
            </Label>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {/* Create new */}
              <button
                type="button"
                onClick={() => handleActionSelect("create")}
                className={`flex items-start gap-3 rounded-none border p-4 text-left transition-colors hover:bg-muted/50 ${
                  currentMapping.action === "create"
                    ? "border-primary bg-muted/30"
                    : "border-border"
                }`}
              >
                <RiAddLine className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                <div>
                  <p className="font-medium text-sm">Create new account</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Add this as a new account in Syllogic
                  </p>
                </div>
                {currentMapping.action === "create" && (
                  <RiCheckLine className="ml-auto h-4 w-4 shrink-0 text-primary" />
                )}
              </button>

              {/* Link existing */}
              <button
                type="button"
                onClick={() => handleActionSelect("link")}
                disabled={availableLinkableAccounts.length === 0}
                className={`flex items-start gap-3 rounded-none border p-4 text-left transition-colors hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-50 ${
                  currentMapping.action === "link"
                    ? "border-primary bg-muted/30"
                    : "border-border"
                }`}
              >
                <RiLinkM className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                <div>
                  <p className="font-medium text-sm">Link to existing account</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {availableLinkableAccounts.length === 0
                      ? "No unlinked accounts available"
                      : "Connect to an account you already have"}
                  </p>
                </div>
                {currentMapping.action === "link" && (
                  <RiCheckLine className="ml-auto h-4 w-4 shrink-0 text-primary" />
                )}
              </button>
            </div>
          </div>

          {/* Create: name input */}
          {currentMapping.action === "create" && (
            <div className="space-y-2">
              <Label htmlFor="account-name">Account name</Label>
              <Input
                id="account-name"
                value={currentMapping.name || ""}
                onChange={(e) => updateCurrentMapping({ name: e.target.value })}
                placeholder="e.g. Main Checking"
              />
            </div>
          )}

          {/* Link: account dropdown */}
          {currentMapping.action === "link" && (
            <div className="space-y-2">
              <Label htmlFor="existing-account">Select existing account</Label>
              <Select
                value={currentMapping.existing_account_id || ""}
                onValueChange={(v) =>
                  v && updateCurrentMapping({ existing_account_id: v })
                }
              >
                <SelectTrigger id="existing-account">
                  <SelectValue placeholder="Choose an account..." />
                </SelectTrigger>
                <SelectContent>
                  {availableLinkableAccounts.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.name}
                      {account.currency && ` (${account.currency})`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Currency mismatch warning */}
              {currentMapping.existing_account_id && (() => {
                const linked = linkableAccounts.find(
                  (a) => a.id === currentMapping.existing_account_id
                );
                if (
                  linked &&
                  linked.currency &&
                  linked.currency.toUpperCase() !==
                    currentAccount.currency.toUpperCase()
                ) {
                  return (
                    <div className="flex items-start gap-2 rounded-none border border-amber-200 bg-amber-50 p-3 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                      <RiAlertLine className="mt-0.5 h-4 w-4 shrink-0" />
                      <p className="text-xs">
                        Currency mismatch: bank account is{" "}
                        <strong>{currentAccount.currency}</strong> but selected
                        account is{" "}
                        <strong>{linked.currency.toUpperCase()}</strong>.
                        Transactions may be recorded in different currencies.
                      </p>
                    </div>
                  );
                }
                return null;
              })()}
            </div>
          )}
        </div>
      )}

      {/* Summary step */}
      {isSummaryStep && (
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Review your mappings</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Confirm how each bank account will be set up in Syllogic.
            </p>
          </div>

          <div className="space-y-2">
            {bankAccounts.map((account, idx) => {
              const mapping = mappings[idx];
              const linkedAccount =
                mapping.action === "link"
                  ? linkableAccounts.find(
                      (a) => a.id === mapping.existing_account_id
                    )
                  : null;

              return (
                <Card key={account.uid}>
                  <CardContent className="flex items-start gap-3 py-4">
                    <RiBankLine className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">
                        {account.name}
                      </p>
                      {account.iban && (
                        <p className="text-xs text-muted-foreground">
                          {maskIban(account.iban)}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <RiArrowRightLine className="h-4 w-4 text-muted-foreground" />
                      {mapping.action === "create" ? (
                        <div className="text-right">
                          <Badge variant="secondary" className="mb-1">
                            New
                          </Badge>
                          <p className="text-xs text-muted-foreground">
                            {mapping.name}
                          </p>
                        </div>
                      ) : (
                        <div className="text-right">
                          <Badge variant="outline" className="mb-1">
                            Link
                          </Badge>
                          <p className="text-xs text-muted-foreground">
                            {linkedAccount?.name || "Unknown"}
                          </p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Initial sync period */}
          <div className="space-y-2">
            <Label htmlFor="sync-days">Initial sync period</Label>
            <p className="text-xs text-muted-foreground">
              How far back should we fetch your transaction history?
            </p>
            <Select
              value={String(initialSyncDays)}
              onValueChange={(v) => v && setInitialSyncDays(Number(v))}
            >
              <SelectTrigger id="sync-days">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SYNC_DAY_OPTIONS.map((days) => (
                  <SelectItem key={days} value={String(days)}>
                    {days === 365 ? "1 year" : days === 730 ? "2 years" : `${days} days`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-none border border-destructive/30 bg-destructive/10 p-3 text-destructive">
              <RiAlertLine className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="text-xs">{error}</p>
            </div>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="mt-6 flex items-center justify-between">
        <Button
          variant="outline"
          onClick={() => setCurrentStep((s) => s - 1)}
          disabled={currentStep === 0 || isSubmitting}
        >
          <RiArrowLeftLine className="mr-2 h-4 w-4" />
          Back
        </Button>

        {isSummaryStep ? (
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
                Connecting...
              </>
            ) : (
              <>
                <RiCheckLine className="mr-2 h-4 w-4" />
                Connect & Sync
              </>
            )}
          </Button>
        ) : (
          <Button
            onClick={() => setCurrentStep((s) => s + 1)}
            disabled={!canProceed()}
          >
            Next
            <RiArrowRightLine className="ml-2 h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
