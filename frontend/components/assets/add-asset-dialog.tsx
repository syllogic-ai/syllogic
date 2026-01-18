"use client";

import { useState } from "react";
import { toast } from "sonner";
import { RiAddLine, RiArrowLeftLine } from "@remixicon/react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CURRENCIES, ACCOUNT_TYPES } from "@/lib/constants";
import { createAccount } from "@/lib/actions/accounts";
import { AssetTypeSelector } from "./asset-type-selector";
import { AddPropertyForm } from "./add-property-form";
import { AddVehicleForm } from "./add-vehicle-form";
import type { AssetType } from "./types";

interface AddAssetDialogProps {
  onAssetAdded?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  showTrigger?: boolean;
}

type DialogStep = "select" | "property" | "vehicle" | "account";

export function AddAssetDialog({
  onAssetAdded,
  open: controlledOpen,
  onOpenChange,
  showTrigger = true,
}: AddAssetDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const setOpen = (newOpen: boolean) => {
    if (isControlled) {
      onOpenChange?.(newOpen);
    } else {
      setInternalOpen(newOpen);
    }
  };
  const [step, setStep] = useState<DialogStep>("select");
  const [isLoading, setIsLoading] = useState(false);

  // Account form state
  const [accountName, setAccountName] = useState("");
  const [accountType, setAccountType] = useState("");
  const [institution, setInstitution] = useState("");
  const [accountCurrency, setAccountCurrency] = useState("EUR");
  const [initialBalance, setInitialBalance] = useState("");

  const resetAccountForm = () => {
    setAccountName("");
    setAccountType("");
    setInstitution("");
    setAccountCurrency("EUR");
    setInitialBalance("");
  };

  const handleClose = () => {
    setOpen(false);
    // Reset step after animation completes
    setTimeout(() => {
      setStep("select");
      resetAccountForm();
    }, 200);
  };

  const handleSuccess = () => {
    handleClose();
    onAssetAdded?.();
  };

  const handleAssetTypeSelect = (type: AssetType) => {
    setStep(type as DialogStep);
  };

  const handleAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!accountName.trim()) {
      toast.error("Please enter an account name");
      return;
    }

    if (!accountType) {
      toast.error("Please select an account type");
      return;
    }

    if (!accountCurrency) {
      toast.error("Please select a currency");
      return;
    }

    setIsLoading(true);

    try {
      const balance = initialBalance ? parseFloat(initialBalance) : 0;
      if (initialBalance && isNaN(balance)) {
        toast.error("Please enter a valid initial balance");
        setIsLoading(false);
        return;
      }

      const result = await createAccount({
        name: accountName.trim(),
        accountType,
        institution: institution.trim() || undefined,
        currency: accountCurrency,
        startingBalance: balance,
      });

      if (result.success) {
        toast.success("Account added successfully");
        handleSuccess();
      } else {
        toast.error(result.error || "Failed to add account");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const getDialogTitle = () => {
    switch (step) {
      case "property":
        return "Add Property";
      case "vehicle":
        return "Add Vehicle";
      case "account":
        return "Add Account";
      default:
        return "Add Asset";
    }
  };

  const getDialogDescription = () => {
    switch (step) {
      case "property":
        return "Add a property to track its value in your portfolio.";
      case "vehicle":
        return "Add a vehicle to track its value in your portfolio.";
      case "account":
        return "Add a bank account or cash to track your finances.";
      default:
        return "Choose what type of asset you want to add.";
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {showTrigger && (
        <DialogTrigger render={<Button size="sm" variant="outline" />}>
          <RiAddLine className="mr-2 h-4 w-4" />
          Add Asset
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          {step !== "select" && (
            <Button
              variant="ghost"
              size="sm"
              className="absolute left-4 top-4 h-8 w-8 p-0"
              onClick={() => setStep("select")}
            >
              <RiArrowLeftLine className="h-4 w-4" />
              <span className="sr-only">Back</span>
            </Button>
          )}
          <DialogTitle>{getDialogTitle()}</DialogTitle>
          <DialogDescription>{getDialogDescription()}</DialogDescription>
        </DialogHeader>

        {step === "select" && (
          <div className="py-4">
            <AssetTypeSelector onSelect={handleAssetTypeSelect} />
          </div>
        )}

        {step === "property" && (
          <AddPropertyForm
            onSuccess={handleSuccess}
            onCancel={() => setStep("select")}
          />
        )}

        {step === "vehicle" && (
          <AddVehicleForm
            onSuccess={handleSuccess}
            onCancel={() => setStep("select")}
          />
        )}

        {step === "account" && (
          <form onSubmit={handleAccountSubmit}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="account-name">Account Name</Label>
                <Input
                  id="account-name"
                  placeholder="e.g., Main Checking"
                  value={accountName}
                  onChange={(e) => setAccountName(e.target.value)}
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

              <div className="space-y-2">
                <Label htmlFor="account-institution">Institution (optional)</Label>
                <Input
                  id="account-institution"
                  placeholder="e.g., Bank of America"
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                />
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

              <div className="space-y-2">
                <Label htmlFor="account-currency">Currency</Label>
                <Select value={accountCurrency} onValueChange={(v) => v && setAccountCurrency(v)}>
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
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep("select")}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading ? "Adding..." : "Add Account"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
