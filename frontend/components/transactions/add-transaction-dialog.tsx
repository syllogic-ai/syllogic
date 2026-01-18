"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import { RiArrowDownLine, RiArrowUpLine } from "@remixicon/react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { createTransaction, getUserAccounts } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";
import type { Account, Category } from "@/lib/db/schema";
import type { CategoryDisplay } from "@/types";
import { getCategoriesForTransactionType } from "@/lib/utils/category-utils";

interface AddTransactionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories?: CategoryDisplay[];
}

export function AddTransactionDialog({ open, onOpenChange, categories: propCategories }: AddTransactionDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  // Form state
  const [transactionType, setTransactionType] = useState<"debit" | "credit">("debit");
  const [accountId, setAccountId] = useState<string>("");
  const [amount, setAmount] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [bookedAt, setBookedAt] = useState<Date>(new Date());
  const [merchant, setMerchant] = useState<string>("");

  useEffect(() => {
    if (open) {
      const loadData = async () => {
        const accountsData = await getUserAccounts();
        setAccounts(accountsData);

        // Use prop categories if available, otherwise fetch
        if (propCategories && propCategories.length > 0) {
          setCategories(propCategories as Category[]);
        } else {
          const categoriesData = await getUserCategories();
          setCategories(categoriesData);
        }

        // Set default account if available
        if (accountsData.length > 0 && !accountId) {
          setAccountId(accountsData[0].id);
        }
      };
      loadData();
    }
  }, [open, accountId, propCategories]);

  const resetForm = () => {
    setTransactionType("debit");
    setAmount("");
    setDescription("");
    setCategoryId("");
    setBookedAt(new Date());
    setMerchant("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!accountId) {
      toast.error("Please select an account");
      return;
    }

    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }

    if (!description.trim()) {
      toast.error("Please enter a description");
      return;
    }

    setIsLoading(true);

    try {
      const result = await createTransaction({
        accountId,
        amount: parsedAmount,
        description: description.trim(),
        categoryId: categoryId || undefined,
        bookedAt,
        transactionType,
        merchant: merchant.trim() || undefined,
      });

      if (result.success) {
        toast.success("Transaction added");
        resetForm();
        onOpenChange(false);
      } else {
        toast.error(result.error || "Failed to add transaction");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // Filter categories based on transaction type
  const filteredCategories = getCategoriesForTransactionType(categories, transactionType);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Add Transaction</DialogTitle>
          <DialogDescription>
            Enter the details for your transaction.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            {/* Transaction Type Toggle */}
            <div className="flex gap-2">
              <Button
                type="button"
                variant={transactionType === "debit" ? "default" : "outline"}
                className="flex-1"
                onClick={() => setTransactionType("debit")}
              >
                <RiArrowDownLine className="mr-2 h-4 w-4" />
                Expense
              </Button>
              <Button
                type="button"
                variant={transactionType === "credit" ? "default" : "outline"}
                className="flex-1"
                onClick={() => setTransactionType("credit")}
              >
                <RiArrowUpLine className="mr-2 h-4 w-4" />
                Income
              </Button>
            </div>

            {/* Account Select */}
            <div className="space-y-2">
              <Label htmlFor="account">Account</Label>
              {accounts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No accounts found. Please create an account first.
                </p>
              ) : (
                <Select value={accountId} onValueChange={(v) => v && setAccountId(v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an account" />
                  </SelectTrigger>
                  <SelectContent>
                    {accounts.map((account) => (
                      <SelectItem key={account.id} value={account.id}>
                        {account.name} ({account.currency})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Amount */}
            <div className="space-y-2">
              <Label htmlFor="amount">Amount</Label>
              <Input
                id="amount"
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>

            {/* Date */}
            <div className="space-y-2">
              <Label>Date</Label>
              <Popover>
                <PopoverTrigger
                  render={
                    <Button
                      variant="outline"
                      className={cn(
                        "w-full justify-start text-left font-normal",
                        !bookedAt && "text-muted-foreground"
                      )}
                    >
                      {bookedAt ? format(bookedAt, "PPP") : "Pick a date"}
                    </Button>
                  }
                />
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={bookedAt}
                    onSelect={(date) => date && setBookedAt(date)}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Enter a description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>

            {/* Merchant (optional) */}
            <div className="space-y-2">
              <Label htmlFor="merchant">Merchant (optional)</Label>
              <Input
                id="merchant"
                placeholder="e.g., Amazon, Starbucks"
                value={merchant}
                onChange={(e) => setMerchant(e.target.value)}
              />
            </div>

            {/* Category */}
            <div className="space-y-2">
              <Label htmlFor="category">Category (optional)</Label>
              <Select value={categoryId} onValueChange={(v) => setCategoryId(v ?? "")}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">No category</SelectItem>
                  {filteredCategories.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      <div className="flex items-center gap-2">
                        <div
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: category.color || "#666" }}
                        />
                        {category.name}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading || accounts.length === 0}>
              {isLoading ? "Adding..." : "Add Transaction"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
