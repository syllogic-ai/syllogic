"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CURRENCIES, ACCOUNT_TYPES } from "@/lib/constants";
import { createAccount, createPocketAccount } from "@/lib/actions/accounts";

const IBAN_RE = /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/;

interface AccountFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
  submitLabel?: string;
  cancelLabel?: string;
  showCancel?: boolean;
  successMessage?: string;
}

export function AccountForm({
  onSuccess,
  onCancel,
  submitLabel = "Create Account",
  cancelLabel = "Cancel",
  showCancel = true,
  successMessage = "Account created successfully",
}: AccountFormProps) {
  const [isLoading, setIsLoading] = useState(false);

  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState("");
  const [institution, setInstitution] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [initialBalance, setInitialBalance] = useState("");
  const [isPocket, setIsPocket] = useState(false);
  const [iban, setIban] = useState("");

  const resetForm = () => {
    setName("");
    setAccountType("");
    setInstitution("");
    setCurrency("EUR");
    setInitialBalance("");
    setIsPocket(false);
    setIban("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter an account name");
      return;
    }
    if (!accountType) {
      toast.error("Please select an account type");
      return;
    }
    if (!currency) {
      toast.error("Please select a currency");
      return;
    }

    const normalizedIban = iban.replace(/\s+/g, "").toUpperCase();
    if (isPocket) {
      if (!normalizedIban) {
        toast.error("Please enter an IBAN for the pocket account");
        return;
      }
      if (
        !IBAN_RE.test(normalizedIban)
        || normalizedIban.length < 15
        || normalizedIban.length > 34
      ) {
        toast.error("Please enter a valid IBAN");
        return;
      }
    }

    setIsLoading(true);

    try {
      const balance = initialBalance ? parseFloat(initialBalance) : 0;
      if (initialBalance && isNaN(balance)) {
        toast.error("Please enter a valid initial balance");
        setIsLoading(false);
        return;
      }

      const result = isPocket
        ? await createPocketAccount({
            name: name.trim(),
            accountType,
            currency,
            startingBalance: balance,
            iban: normalizedIban,
          })
        : await createAccount({
            name: name.trim(),
            accountType,
            institution: institution.trim() || undefined,
            currency,
            startingBalance: balance,
          });

      if (result.success) {
        const backfilled =
          isPocket && "backfilledCount" in result && typeof result.backfilledCount === "number"
            ? result.backfilledCount
            : 0;
        const message = backfilled > 0
          ? `${successMessage} — ${backfilled} existing transfer${backfilled === 1 ? "" : "s"} linked`
          : successMessage;
        toast.success(message);
        resetForm();
        onSuccess?.();
      } else {
        toast.error(result.error || "Failed to create account");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    resetForm();
    onCancel?.();
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="grid gap-4 py-4">
        <div className="space-y-2">
          <Label htmlFor="account-name">Account Name</Label>
          <Input
            id="account-name"
            placeholder="e.g., Main Checking"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="account-type">Account Type</Label>
          <Select value={accountType} onValueChange={(v) => v && setAccountType(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select account type" />
            </SelectTrigger>
            <SelectContent>
              {ACCOUNT_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {!isPocket && (
          <div className="space-y-2">
            <Label htmlFor="account-institution">Institution (optional)</Label>
            <Input
              id="account-institution"
              placeholder="e.g., Bank of America"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
            />
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="account-currency">Currency</Label>
          <Select value={currency} onValueChange={(v) => v && setCurrency(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select currency" />
            </SelectTrigger>
            <SelectContent>
              {CURRENCIES.map((curr) => (
                <SelectItem key={curr.code} value={curr.code}>
                  {curr.code} - {curr.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="account-balance">Initial Balance (optional)</Label>
          <Input
            id="account-balance"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={initialBalance}
            onChange={(e) => setInitialBalance(e.target.value)}
          />
        </div>

        <div className="flex items-center justify-between rounded border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="is-pocket" className="cursor-pointer">
              Register as pocket account
            </Label>
            <p className="text-xs text-muted-foreground">
              Track a savings pocket by IBAN. Transfers from your synced accounts
              will be auto-detected and linked.
            </p>
          </div>
          <Switch
            id="is-pocket"
            checked={isPocket}
            onCheckedChange={setIsPocket}
          />
        </div>

        {isPocket && (
          <div className="space-y-2">
            <Label htmlFor="account-iban">IBAN</Label>
            <Input
              id="account-iban"
              placeholder="NL91 ABNA 0417 1643 00"
              value={iban}
              onChange={(e) => setIban(e.target.value)}
              autoComplete="off"
              autoCapitalize="characters"
            />
            <p className="text-xs text-muted-foreground">
              Spaces are ignored. The IBAN is encrypted at rest and only used to
              match transfers from your synced accounts.
            </p>
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2">
        {showCancel && (
          <Button type="button" variant="outline" onClick={handleCancel} disabled={isLoading}>
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={isLoading}>
          {isLoading ? "Creating..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
