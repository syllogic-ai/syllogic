"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  RiDeleteBinLine,
  RiEditLine,
  RiMoreLine,
  RiRefreshLine,
  RiEyeLine,
} from "@remixicon/react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { CURRENCIES } from "@/lib/constants/currencies";
import { updateAccount, deleteAccount, recalculateAccountTimeseries } from "@/lib/actions/accounts";
import { UpdateBalanceDialog } from "@/components/accounts/update-balance-dialog";
import { AccountLogo } from "@/components/ui/account-logo";
import type { Account } from "@/lib/db/schema";

const ACCOUNT_TYPES = [
  { value: "checking", label: "Checking Account" },
  { value: "savings", label: "Savings Account" },
  { value: "credit_card", label: "Credit Card" },
  { value: "investment", label: "Investment Account" },
  { value: "cash", label: "Cash" },
  { value: "other", label: "Other" },
] as const;

function getAccountTypeLabel(value: string): string {
  const type = ACCOUNT_TYPES.find((t) => t.value === value);
  return type?.label || value;
}

type AccountWithLogo = Account & {
  logo?: {
    id: string;
    logoUrl: string | null;
    updatedAt?: Date | null;
  } | null;
};

interface AccountListProps {
  accounts: AccountWithLogo[];
  onAccountUpdated?: () => void;
}

export function AccountList({ accounts, onAccountUpdated }: AccountListProps) {
  const [editingAccount, setEditingAccount] = useState<AccountWithLogo | null>(null);
  const [deletingAccount, setDeletingAccount] = useState<AccountWithLogo | null>(null);
  const [updateBalanceAccount, setUpdateBalanceAccount] = useState<AccountWithLogo | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editAccountType, setEditAccountType] = useState("");
  const [editInstitution, setEditInstitution] = useState("");
  const [editCurrency, setEditCurrency] = useState("");
  const [editBalance, setEditBalance] = useState("");

  const openEditDialog = (account: AccountWithLogo) => {
    setEditingAccount(account);
    setEditName(account.name);
    setEditAccountType(account.accountType);
    setEditInstitution(account.institution || "");
    setEditCurrency(account.currency || "EUR");
    setEditBalance(account.startingBalance || "0");
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAccount) return;

    if (!editName.trim()) {
      toast.error("Please enter an account name");
      return;
    }

    setIsLoading(true);

    try {
      const balance = parseFloat(editBalance);
      const result = await updateAccount(editingAccount.id, {
        name: editName.trim(),
        accountType: editAccountType,
        institution: editInstitution.trim() || undefined,
        currency: editCurrency,
        startingBalance: isNaN(balance) ? 0 : balance,
      });

      if (result.success) {
        toast.success("Account updated successfully");
        setEditingAccount(null);
        onAccountUpdated?.();
      } else {
        toast.error(result.error || "Failed to update account");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingAccount) return;

    setIsLoading(true);

    try {
      const result = await deleteAccount(deletingAccount.id);

      if (result.success) {
        toast.success("Account deleted successfully");
        setDeletingAccount(null);
        onAccountUpdated?.();
      } else {
        toast.error(result.error || "Failed to delete account");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRecalculate = async (accountId: string, accountName: string) => {
    setIsLoading(true);
    const toastId = toast.loading(`Recalculating balance for ${accountName}...`);

    try {
      const result = await recalculateAccountTimeseries(accountId);

      if (result.success) {
        toast.success(result.message || "Balance recalculated successfully", { id: toastId });
        onAccountUpdated?.();
      } else {
        toast.error(result.error || "Failed to recalculate balance", { id: toastId });
      }
    } catch {
      toast.error("An error occurred. Please try again.", { id: toastId });
    } finally {
      setIsLoading(false);
    }
  };

  if (accounts.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <CardDescription>
            You haven't created any accounts yet. Add an account to start tracking your finances.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-32 items-center justify-center rounded border border-dashed">
            <p className="text-sm text-muted-foreground">No accounts</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <CardDescription>
            Your financial accounts and cash holdings.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y">
            {accounts.map((account) => (
              <div
                key={account.id}
                className="flex items-center justify-between py-4 first:pt-0 last:pb-0"
              >
                <div className="flex items-center gap-3">
                  <AccountLogo
                    name={account.name}
                    logoUrl={account.logo?.logoUrl}
                    updatedAt={account.logo?.updatedAt}
                    className="!size-10"
                  />
                  <div>
                    <p className="font-medium">{account.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {getAccountTypeLabel(account.accountType)}
                      {account.institution && ` • ${account.institution}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="font-medium">
                      {new Intl.NumberFormat("en-US", {
                        style: "currency",
                        currency: account.currency || "EUR",
                      }).format(parseFloat(account.functionalBalance || "0"))}
                    </p>
                    <p className="text-xs text-muted-foreground">{account.currency}</p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.location.href = `/accounts/${account.id}`}
                  >
                    <RiEyeLine className="h-4 w-4" />
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        <RiMoreLine className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => openEditDialog(account)}>
                        <RiEditLine className="mr-2 h-4 w-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => handleRecalculate(account.id, account.name)}>
                        <RiRefreshLine className="mr-2 h-4 w-4" />
                        Recalculate Balance
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={() => setDeletingAccount(account)}
                      >
                        <RiDeleteBinLine className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={!!editingAccount} onOpenChange={(open) => !open && setEditingAccount(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Account</DialogTitle>
            <DialogDescription>
              Update your account details.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEdit}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Account Name</Label>
                <Input
                  id="edit-name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-type">Account Type</Label>
                <Select value={editAccountType} onValueChange={(v) => v && setEditAccountType(v)}>
                  <SelectTrigger>
                    <SelectValue />
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
                <Label htmlFor="edit-institution">Institution (optional)</Label>
                <Input
                  id="edit-institution"
                  value={editInstitution}
                  onChange={(e) => setEditInstitution(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-currency">Currency</Label>
                <Select value={editCurrency} onValueChange={(v) => v && setEditCurrency(v)} disabled>
                  <SelectTrigger>
                    <SelectValue />
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
                <Label htmlFor="edit-balance">Starting Balance</Label>
                <Input
                  id="edit-balance"
                  type="number"
                  step="0.01"
                  value={editBalance}
                  onChange={(e) => setEditBalance(e.target.value)}
                  className="flex-1"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditingAccount(null)}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading ? "Saving..." : "Save Changes"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deletingAccount} onOpenChange={(open) => !open && setDeletingAccount(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Account</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{deletingAccount?.name}"? This action cannot be undone.
              All transactions associated with this account will remain but will no longer be linked to an account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isLoading}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isLoading ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Update Balance Dialog */}
      {updateBalanceAccount && (
        <UpdateBalanceDialog
          account={{
            id: updateBalanceAccount.id,
            name: updateBalanceAccount.name,
            currency: updateBalanceAccount.currency,
            functionalBalance: updateBalanceAccount.functionalBalance,
          }}
          open={!!updateBalanceAccount}
          onOpenChange={(open) => !open && setUpdateBalanceAccount(null)}
          onSuccess={() => {
            setUpdateBalanceAccount(null);
            setEditingAccount(null);
            onAccountUpdated?.();
          }}
        />
      )}
    </>
  );
}
