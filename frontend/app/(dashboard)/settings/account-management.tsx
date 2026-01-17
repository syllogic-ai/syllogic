"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AddAccountDialog, AccountList } from "@/components/settings";
import type { Account } from "@/lib/db/schema";

interface AccountManagementProps {
  initialAccounts: Account[];
}

export function AccountManagement({ initialAccounts }: AccountManagementProps) {
  const router = useRouter();
  const [accounts, setAccounts] = useState(initialAccounts);

  const handleRefresh = () => {
    router.refresh();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Account Management</h2>
          <p className="text-sm text-muted-foreground">
            Add and manage your financial accounts.
          </p>
        </div>
        <AddAccountDialog onAccountAdded={handleRefresh} />
      </div>
      <AccountList accounts={accounts} onAccountUpdated={handleRefresh} />
    </div>
  );
}
