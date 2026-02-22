"use client";

import { RiRefreshLine } from "@remixicon/react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AccountLogo } from "@/components/ui/account-logo";
import { formatDistanceToNow } from "date-fns";
import type { Account } from "@/lib/db/schema";

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: "Checking",
  savings: "Savings",
  credit_card: "Credit Card",
  investment: "Investment",
  cash: "Cash",
  other: "Other",
};

interface AccountHeaderProps {
  account: Account & {
    logo?: {
      id: string;
      logoUrl: string | null;
      updatedAt?: Date | null;
    } | null;
  };
  currency: string;
}

function formatCurrency(value: string | null, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "EUR",
  }).format(parseFloat(value || "0"));
}

export function AccountHeader({ account, currency }: AccountHeaderProps) {
  const typeLabel = ACCOUNT_TYPE_LABELS[account.accountType] || account.accountType;
  const lastSyncedText = account.lastSyncedAt
    ? `Synced ${formatDistanceToNow(new Date(account.lastSyncedAt), { addSuffix: true })}`
    : "Manual account";

  return (
    <Card>
      <CardContent className="flex items-center justify-between p-6">
        <div className="flex items-center gap-4">
          <AccountLogo
            name={account.name}
            logoUrl={account.logo?.logoUrl}
            updatedAt={account.logo?.updatedAt}
            className="!size-12"
          />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{account.name}</h2>
              <Badge variant="secondary">{typeLabel}</Badge>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {account.institution && (
                <>
                  <span>{account.institution}</span>
                  <span>-</span>
                </>
              )}
              <div className="flex items-center gap-1">
                <RiRefreshLine className="h-3 w-3" />
                <span>{lastSyncedText}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-2xl font-semibold">
            {formatCurrency(account.functionalBalance, currency)}
          </p>
          <p className="text-sm text-muted-foreground">{currency}</p>
        </div>
      </CardContent>
    </Card>
  );
}
