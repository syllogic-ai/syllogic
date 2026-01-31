"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useRegisterCommandPaletteCallbacks } from "@/components/command-palette-context";
import {
  RiDeleteBinLine,
  RiEditLine,
  RiBankLine,
  RiHome4Line,
  RiCarLine,
  RiMoreLine,
  RiScalesLine,
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
import { updateAccount, deleteAccount } from "@/lib/actions/accounts";
import { updateProperty, deleteProperty } from "@/lib/actions/properties";
import { updateVehicle, deleteVehicle } from "@/lib/actions/vehicles";
import { AddAssetDialog } from "@/components/assets/add-asset-dialog";
import { UpdateBalanceDialog } from "@/components/accounts/update-balance-dialog";
import { PROPERTY_TYPES, VEHICLE_TYPES } from "@/components/assets/types";
import type { Account, Property, Vehicle } from "@/lib/db/schema";

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

function getPropertyTypeLabel(value: string): string {
  const type = PROPERTY_TYPES.find((t) => t.value === value);
  return type?.label || value;
}

function getVehicleTypeLabel(value: string): string {
  const type = VEHICLE_TYPES.find((t) => t.value === value);
  return type?.label || value;
}

function formatCurrency(value: string | null, currency: string | null): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "EUR",
  }).format(parseFloat(value || "0"));
}

interface AssetManagementProps {
  initialAccounts: Account[];
  initialProperties: Property[];
  initialVehicles: Vehicle[];
}

export function AssetManagement({
  initialAccounts,
  initialProperties,
  initialVehicles,
}: AssetManagementProps) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [isAddAssetDialogOpen, setIsAddAssetDialogOpen] = useState(false);

  const handleOpenAddAssetDialog = useCallback(() => {
    setIsAddAssetDialogOpen(true);
  }, []);

  // Register command palette callbacks
  useRegisterCommandPaletteCallbacks(
    {
      onAddAsset: handleOpenAddAssetDialog,
    },
    [handleOpenAddAssetDialog]
  );

  // Edit states
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [editingProperty, setEditingProperty] = useState<Property | null>(null);
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null);
  const [updateBalanceAccount, setUpdateBalanceAccount] = useState<Account | null>(null);

  // Delete states
  const [deletingAccount, setDeletingAccount] = useState<Account | null>(null);
  const [deletingProperty, setDeletingProperty] = useState<Property | null>(null);
  const [deletingVehicle, setDeletingVehicle] = useState<Vehicle | null>(null);

  // Account edit form state
  const [editAccountName, setEditAccountName] = useState("");
  const [editAccountType, setEditAccountType] = useState("");
  const [editAccountInstitution, setEditAccountInstitution] = useState("");
  const [editAccountCurrency, setEditAccountCurrency] = useState("");
  const [editAccountBalance, setEditAccountBalance] = useState("");

  // Property edit form state
  const [editPropertyName, setEditPropertyName] = useState("");
  const [editPropertyType, setEditPropertyType] = useState("");
  const [editPropertyAddress, setEditPropertyAddress] = useState("");
  const [editPropertyValue, setEditPropertyValue] = useState("");
  const [editPropertyCurrency, setEditPropertyCurrency] = useState("");

  // Vehicle edit form state
  const [editVehicleName, setEditVehicleName] = useState("");
  const [editVehicleType, setEditVehicleType] = useState("");
  const [editVehicleMake, setEditVehicleMake] = useState("");
  const [editVehicleModel, setEditVehicleModel] = useState("");
  const [editVehicleYear, setEditVehicleYear] = useState("");
  const [editVehicleValue, setEditVehicleValue] = useState("");
  const [editVehicleCurrency, setEditVehicleCurrency] = useState("");

  const handleRefresh = () => {
    router.refresh();
  };

  // Account handlers
  const openEditAccountDialog = (account: Account) => {
    setEditingAccount(account);
    setEditAccountName(account.name);
    setEditAccountType(account.accountType);
    setEditAccountInstitution(account.institution || "");
    setEditAccountCurrency(account.currency || "EUR");
    setEditAccountBalance(account.functionalBalance || "0");
  };

  const handleEditAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAccount) return;

    setIsLoading(true);
    try {
      const balance = parseFloat(editAccountBalance);
      const result = await updateAccount(editingAccount.id, {
        name: editAccountName.trim(),
        accountType: editAccountType,
        institution: editAccountInstitution.trim() || undefined,
        currency: editAccountCurrency,
        startingBalance: isNaN(balance) ? 0 : balance,
      });

      if (result.success) {
        toast.success("Account updated");
        setEditingAccount(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to update account");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!deletingAccount) return;
    setIsLoading(true);
    try {
      const result = await deleteAccount(deletingAccount.id);
      if (result.success) {
        toast.success("Account deleted");
        setDeletingAccount(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to delete account");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  // Property handlers
  const openEditPropertyDialog = (property: Property) => {
    setEditingProperty(property);
    setEditPropertyName(property.name);
    setEditPropertyType(property.propertyType);
    setEditPropertyAddress(property.address || "");
    setEditPropertyValue(property.currentValue || "0");
    setEditPropertyCurrency(property.currency || "EUR");
  };

  const handleEditProperty = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProperty) return;

    setIsLoading(true);
    try {
      const value = parseFloat(editPropertyValue);
      const result = await updateProperty(editingProperty.id, {
        name: editPropertyName.trim(),
        propertyType: editPropertyType,
        address: editPropertyAddress.trim() || undefined,
        currentValue: isNaN(value) ? 0 : value,
        currency: editPropertyCurrency,
      });

      if (result.success) {
        toast.success("Property updated");
        setEditingProperty(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to update property");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteProperty = async () => {
    if (!deletingProperty) return;
    setIsLoading(true);
    try {
      const result = await deleteProperty(deletingProperty.id);
      if (result.success) {
        toast.success("Property deleted");
        setDeletingProperty(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to delete property");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  // Vehicle handlers
  const openEditVehicleDialog = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle);
    setEditVehicleName(vehicle.name);
    setEditVehicleType(vehicle.vehicleType);
    setEditVehicleMake(vehicle.make || "");
    setEditVehicleModel(vehicle.model || "");
    setEditVehicleYear(vehicle.year?.toString() || "");
    setEditVehicleValue(vehicle.currentValue || "0");
    setEditVehicleCurrency(vehicle.currency || "EUR");
  };

  const handleEditVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingVehicle) return;

    setIsLoading(true);
    try {
      const value = parseFloat(editVehicleValue);
      const year = editVehicleYear ? parseInt(editVehicleYear, 10) : undefined;
      const result = await updateVehicle(editingVehicle.id, {
        name: editVehicleName.trim(),
        vehicleType: editVehicleType,
        make: editVehicleMake.trim() || undefined,
        model: editVehicleModel.trim() || undefined,
        year: year && !isNaN(year) ? year : undefined,
        currentValue: isNaN(value) ? 0 : value,
        currency: editVehicleCurrency,
      });

      if (result.success) {
        toast.success("Vehicle updated");
        setEditingVehicle(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to update vehicle");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteVehicle = async () => {
    if (!deletingVehicle) return;
    setIsLoading(true);
    try {
      const result = await deleteVehicle(deletingVehicle.id);
      if (result.success) {
        toast.success("Vehicle deleted");
        setDeletingVehicle(null);
        handleRefresh();
      } else {
        toast.error(result.error || "Failed to delete vehicle");
      }
    } catch {
      toast.error("An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with Add Asset button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Asset Management</h2>
          <p className="text-sm text-muted-foreground">
            Add and manage your accounts, properties, and vehicles.
          </p>
        </div>
        <AddAssetDialog
          onAssetAdded={handleRefresh}
          open={isAddAssetDialogOpen}
          onOpenChange={setIsAddAssetDialogOpen}
        />
      </div>

      {/* Accounts Section */}
      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <CardDescription>Your financial accounts and cash holdings.</CardDescription>
        </CardHeader>
        <CardContent>
          {initialAccounts.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded border border-dashed">
              <p className="text-sm text-muted-foreground">No accounts added</p>
            </div>
          ) : (
            <div className="divide-y">
              {initialAccounts.map((account) => (
                <div key={account.id} className="flex items-center justify-between py-4 first:pt-0 last:pb-0">
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
                      <p className="font-medium">{formatCurrency(account.functionalBalance, account.currency)}</p>
                      <p className="text-xs text-muted-foreground">{account.currency}</p>
                    </div>
                    <Button
                      className="cursor-pointer"
                      onClick={() => router.push(`/accounts/${account.id}`)}
                    >
                      <RiEyeLine className="h-5 w-5" />
                      View
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <RiMoreLine className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEditAccountDialog(account)}>
                          <RiEditLine className="mr-2 h-4 w-4" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive" onClick={() => setDeletingAccount(account)}>
                          <RiDeleteBinLine className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Properties Section */}
      <Card>
        <CardHeader>
          <CardTitle>Properties</CardTitle>
          <CardDescription>Your real estate holdings.</CardDescription>
        </CardHeader>
        <CardContent>
          {initialProperties.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded border border-dashed">
              <p className="text-sm text-muted-foreground">No properties added</p>
            </div>
          ) : (
            <div className="divide-y">
              {initialProperties.map((property) => (
                <div key={property.id} className="flex items-center justify-between py-4 first:pt-0 last:pb-0">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded bg-muted">
                      <RiHome4Line className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-medium">{property.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {getPropertyTypeLabel(property.propertyType)}
                        {property.address && ` • ${property.address}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="font-medium">{formatCurrency(property.currentValue, property.currency)}</p>
                      <p className="text-xs text-muted-foreground">{property.currency}</p>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <RiMoreLine className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEditPropertyDialog(property)}>
                          <RiEditLine className="mr-2 h-4 w-4" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive" onClick={() => setDeletingProperty(property)}>
                          <RiDeleteBinLine className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Vehicles Section */}
      <Card>
        <CardHeader>
          <CardTitle>Vehicles</CardTitle>
          <CardDescription>Your vehicles and transportation assets.</CardDescription>
        </CardHeader>
        <CardContent>
          {initialVehicles.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded border border-dashed">
              <p className="text-sm text-muted-foreground">No vehicles added</p>
            </div>
          ) : (
            <div className="divide-y">
              {initialVehicles.map((vehicle) => (
                <div key={vehicle.id} className="flex items-center justify-between py-4 first:pt-0 last:pb-0">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded bg-muted">
                      <RiCarLine className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-medium">{vehicle.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {getVehicleTypeLabel(vehicle.vehicleType)}
                        {vehicle.make && ` • ${vehicle.make}`}
                        {vehicle.model && ` ${vehicle.model}`}
                        {vehicle.year && ` (${vehicle.year})`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="font-medium">{formatCurrency(vehicle.currentValue, vehicle.currency)}</p>
                      <p className="text-xs text-muted-foreground">{vehicle.currency}</p>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <RiMoreLine className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEditVehicleDialog(vehicle)}>
                          <RiEditLine className="mr-2 h-4 w-4" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive" onClick={() => setDeletingVehicle(vehicle)}>
                          <RiDeleteBinLine className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit Account Dialog */}
      <Dialog open={!!editingAccount} onOpenChange={(open) => !open && setEditingAccount(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Account</DialogTitle>
            <DialogDescription>Update your account details.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditAccount}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-account-name">Account Name</Label>
                <Input id="edit-account-name" value={editAccountName} onChange={(e) => setEditAccountName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-account-type">Account Type</Label>
                <Select value={editAccountType} onValueChange={(v) => v && setEditAccountType(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ACCOUNT_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-account-institution">Institution (optional)</Label>
                <Input id="edit-account-institution" value={editAccountInstitution} onChange={(e) => setEditAccountInstitution(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-account-balance">Current Balance</Label>
                <div className="flex gap-2">
                  <Input id="edit-account-balance" type="number" step="0.01" value={editAccountBalance} disabled className="flex-1" />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      if (editingAccount) {
                        setUpdateBalanceAccount(editingAccount);
                      }
                    }}
                  >
                    <RiScalesLine className="mr-2 h-4 w-4" />
                    Adjust
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-account-currency">Currency</Label>
                <Select value={editAccountCurrency} onValueChange={(v) => v && setEditAccountCurrency(v)} disabled>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((curr) => (
                      <SelectItem key={curr.code} value={curr.code}>{curr.code} - {curr.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingAccount(null)} disabled={isLoading}>Cancel</Button>
              <Button type="submit" disabled={isLoading}>{isLoading ? "Saving..." : "Save Changes"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Property Dialog */}
      <Dialog open={!!editingProperty} onOpenChange={(open) => !open && setEditingProperty(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Property</DialogTitle>
            <DialogDescription>Update your property details.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditProperty}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-property-name">Property Name</Label>
                <Input id="edit-property-name" value={editPropertyName} onChange={(e) => setEditPropertyName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-property-type">Property Type</Label>
                <Select value={editPropertyType} onValueChange={(v) => v && setEditPropertyType(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PROPERTY_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-property-address">Address (optional)</Label>
                <Input id="edit-property-address" value={editPropertyAddress} onChange={(e) => setEditPropertyAddress(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-property-value">Current Value</Label>
                <Input id="edit-property-value" type="number" step="0.01" value={editPropertyValue} onChange={(e) => setEditPropertyValue(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-property-currency">Currency</Label>
                <Select value={editPropertyCurrency} onValueChange={(v) => v && setEditPropertyCurrency(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((curr) => (
                      <SelectItem key={curr.code} value={curr.code}>{curr.code} - {curr.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingProperty(null)} disabled={isLoading}>Cancel</Button>
              <Button type="submit" disabled={isLoading}>{isLoading ? "Saving..." : "Save Changes"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Vehicle Dialog */}
      <Dialog open={!!editingVehicle} onOpenChange={(open) => !open && setEditingVehicle(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Vehicle</DialogTitle>
            <DialogDescription>Update your vehicle details.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditVehicle}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-vehicle-name">Vehicle Name</Label>
                <Input id="edit-vehicle-name" value={editVehicleName} onChange={(e) => setEditVehicleName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-vehicle-type">Vehicle Type</Label>
                <Select value={editVehicleType} onValueChange={(v) => v && setEditVehicleType(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {VEHICLE_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-vehicle-make">Make (optional)</Label>
                  <Input id="edit-vehicle-make" value={editVehicleMake} onChange={(e) => setEditVehicleMake(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-vehicle-model">Model (optional)</Label>
                  <Input id="edit-vehicle-model" value={editVehicleModel} onChange={(e) => setEditVehicleModel(e.target.value)} />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-vehicle-year">Year (optional)</Label>
                <Input id="edit-vehicle-year" type="number" value={editVehicleYear} onChange={(e) => setEditVehicleYear(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-vehicle-value">Current Value</Label>
                <Input id="edit-vehicle-value" type="number" step="0.01" value={editVehicleValue} onChange={(e) => setEditVehicleValue(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-vehicle-currency">Currency</Label>
                <Select value={editVehicleCurrency} onValueChange={(v) => v && setEditVehicleCurrency(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((curr) => (
                      <SelectItem key={curr.code} value={curr.code}>{curr.code} - {curr.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingVehicle(null)} disabled={isLoading}>Cancel</Button>
              <Button type="submit" disabled={isLoading}>{isLoading ? "Saving..." : "Save Changes"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Account Confirmation */}
      <AlertDialog open={!!deletingAccount} onOpenChange={(open) => !open && setDeletingAccount(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Account</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deletingAccount?.name}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteAccount} disabled={isLoading} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {isLoading ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Property Confirmation */}
      <AlertDialog open={!!deletingProperty} onOpenChange={(open) => !open && setDeletingProperty(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Property</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deletingProperty?.name}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteProperty} disabled={isLoading} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {isLoading ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Vehicle Confirmation */}
      <AlertDialog open={!!deletingVehicle} onOpenChange={(open) => !open && setDeletingVehicle(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Vehicle</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deletingVehicle?.name}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteVehicle} disabled={isLoading} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
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
            handleRefresh();
          }}
        />
      )}
    </div>
  );
}
