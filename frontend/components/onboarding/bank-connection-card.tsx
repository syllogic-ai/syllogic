"use client";

import { RiBankLine, RiShieldCheckLine, RiTimeLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";

interface BankConnectionCardProps {
  onConnect: () => void;
  isConnecting?: boolean;
}

export function BankConnectionCard({ onConnect, isConnecting }: BankConnectionCardProps) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
          <RiBankLine className="h-8 w-8 text-primary" />
        </div>
        <h3 className="text-lg font-medium">Connect Your Bank Account</h3>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Securely connect your bank account to automatically import transactions and keep your
          finances up to date.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex items-start gap-3 rounded-lg border p-4">
          <RiShieldCheckLine className="mt-0.5 h-5 w-5 text-green-600" />
          <div>
            <p className="text-sm font-medium">Bank-Level Security</p>
            <p className="text-xs text-muted-foreground">
              We use GoCardless, a regulated Open Banking provider, to securely connect to your
              bank.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-3 rounded-lg border p-4">
          <RiTimeLine className="mt-0.5 h-5 w-5 text-blue-600" />
          <div>
            <p className="text-sm font-medium">Automatic Sync</p>
            <p className="text-xs text-muted-foreground">
              Your transactions will be automatically imported and categorized daily.
            </p>
          </div>
        </div>
      </div>

      <Button className="w-full" size="lg" onClick={onConnect} disabled={isConnecting}>
        {isConnecting ? "Connecting..." : "Connect Bank Account"}
      </Button>
    </div>
  );
}
