"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  RiDeleteBinLine,
  RiEditLine,
  RiBankLine,
  RiMoreLine,
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
import { updateAccount, deleteAccount } from "@/lib/actions/accounts";
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

interface AccountListProps {
  accounts: Account[];
  onAccountUpdated?: () => void;
}

export function AccountList({ accounts, onAccountUpdated }: AccountListProps) {
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [deletingAccount, setDeletingAccount] = useState<Account | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editAccountType, setEditAccountType] = useState("");
  const [editInstitution, setEditInstitution] = useState("");
  const [editCurrency, setEditCurrency] = useState("");
  const [editBalance, setEditBalance] = useState("");

  const openEditDialog = (account: Account) => {
    setEditingAccount(account);
    setEditName(account.name);
    setEditAccountType(account.accountType);
    setEditInstitution(account.institution || "");
    setEditCurrency(account.currency || "EUR");
    setEditBalance(account.balanceCurrent || "0");
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
        balanceCurrent: isNaN(balance) ? 0 : balance,
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
            Manage your financial accounts. Click on an account to edit or delete it.
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
                  <div className="flex h-10 w-10 items-center justify-center rounded bg-muted">
                    <RiBankLine className="h-5 w-5 text-muted-foreground" />
                  </div>
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
                      }).format(parseFloat(account.balanceCurrent || "0"))}
                    </p>
                    <p className="text-xs text-muted-foreground">{account.currency}</p>
                  </div>
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
                <Select value={editCurrency} onValueChange={(v) => v && setEditCurrency(v)}>
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
                <Label htmlFor="edit-balance">Current Balance</Label>
                <Input
                  id="edit-balance"
                  type="number"
                  step="0.01"
                  value={editBalance}
                  onChange={(e) => setEditBalance(e.target.value)}
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
    </>
  );
}
