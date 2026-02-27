"use client";

import { useState } from "react";
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
import { AccountForm } from "@/components/accounts/account-form";
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

  const handleClose = () => {
    setOpen(false);
    setTimeout(() => {
      setStep("select");
    }, 200);
  };

  const handleSuccess = () => {
    handleClose();
    onAssetAdded?.();
  };

  const handleAssetTypeSelect = (type: AssetType) => {
    setStep(type as DialogStep);
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
        <DialogTrigger render={<Button size="sm" variant="outline" data-walkthrough="walkthrough-add" />}>
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
          <AddPropertyForm onSuccess={handleSuccess} onCancel={() => setStep("select")} />
        )}

        {step === "vehicle" && (
          <AddVehicleForm onSuccess={handleSuccess} onCancel={() => setStep("select")} />
        )}

        {step === "account" && (
          <AccountForm
            onSuccess={handleSuccess}
            onCancel={() => setStep("select")}
            submitLabel="Add Account"
            successMessage="Account added successfully"
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
