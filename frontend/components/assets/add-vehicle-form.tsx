"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
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
import { CURRENCIES } from "@/lib/constants/currencies";
import { createVehicle } from "@/lib/actions/vehicles";
import { VEHICLE_TYPES } from "./types";
import { OwnersField, type OwnerValue } from "@/components/household/owners-field";

type Person = { id: string; name: string; kind: string; color?: string | null; avatarUrl?: string | null };

interface AddVehicleFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function AddVehicleForm({ onSuccess, onCancel }: AddVehicleFormProps) {
  const [isLoading, setIsLoading] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [vehicleType, setVehicleType] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [currentValue, setCurrentValue] = useState("");
  const [currency, setCurrency] = useState("EUR");

  // Ownership state
  const [people, setPeople] = useState<Person[]>([]);
  const [owners, setOwners] = useState<OwnerValue[]>([]);
  const [ownersError, setOwnersError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/people")
      .then((r) => r.json())
      .then((data: { people: Person[] }) => {
        setPeople(data.people);
        const self = data.people.find((p) => p.kind === "self");
        if (self) {
          setOwners([{ personId: self.id, share: null }]);
        }
      })
      .catch(() => {
        // Non-fatal: owners field will be empty
      });
  }, []);

  const validateOwners = (): boolean => {
    if (owners.length === 0) {
      setOwnersError("Select at least one owner.");
      return false;
    }
    const allNull = owners.every((o) => o.share === null);
    const allSet = owners.every((o) => o.share !== null);
    if (!allNull && !allSet) {
      setOwnersError("All owners must either split equally or specify shares.");
      return false;
    }
    if (allSet) {
      const sum = owners.reduce((acc, o) => acc + (o.share as number), 0);
      if (Math.abs(sum - 1) > 0.0001) {
        setOwnersError(`Shares must sum to 100% (currently ${Math.round(sum * 100)}%).`);
        return false;
      }
    }
    setOwnersError(null);
    return true;
  };

  const putOwners = async (entityId: string) => {
    try {
      const r = await fetch(`/api/owners/vehicle/${entityId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owners }),
      });
      if (!r.ok) {
        const text = await r.text().catch(() => "request failed");
        throw new Error(`Failed to save owners: ${text.slice(0, 200)}`);
      }
    } catch (err) {
      toast.error((err as Error).message || "Vehicle created, but failed to save ownership. You can update it later.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter a vehicle name");
      return;
    }

    if (!vehicleType) {
      toast.error("Please select a vehicle type");
      return;
    }

    if (!currency) {
      toast.error("Please select a currency");
      return;
    }

    if (people.length > 0 && !validateOwners()) return;

    setIsLoading(true);

    try {
      const value = currentValue ? parseFloat(currentValue) : 0;
      if (currentValue && isNaN(value)) {
        toast.error("Please enter a valid value");
        setIsLoading(false);
        return;
      }

      const yearNum = year ? parseInt(year, 10) : undefined;
      if (year && (isNaN(yearNum!) || yearNum! < 1900 || yearNum! > new Date().getFullYear() + 1)) {
        toast.error("Please enter a valid year");
        setIsLoading(false);
        return;
      }

      const result = await createVehicle({
        name: name.trim(),
        vehicleType,
        make: make.trim() || undefined,
        model: model.trim() || undefined,
        year: yearNum,
        currentValue: value,
        currency,
      });

      if (result.success) {
        if (result.vehicleId) {
          await putOwners(result.vehicleId);
        }
        toast.success("Vehicle added successfully");
        onSuccess?.();
      } else {
        toast.error(result.error || "Failed to add vehicle");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="grid gap-4 py-4">
        {/* Vehicle Name */}
        <div className="space-y-2">
          <Label htmlFor="vehicle-name">Vehicle Name</Label>
          <Input
            id="vehicle-name"
            placeholder="e.g., Family Car"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* Vehicle Type */}
        <div className="space-y-2">
          <Label htmlFor="vehicle-type">Vehicle Type</Label>
          <Select value={vehicleType} onValueChange={(v) => v && setVehicleType(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select vehicle type" />
            </SelectTrigger>
            <SelectContent>
              {VEHICLE_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Make and Model */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="vehicle-make">Make (optional)</Label>
            <Input
              id="vehicle-make"
              placeholder="e.g., Toyota"
              value={make}
              onChange={(e) => setMake(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="vehicle-model">Model (optional)</Label>
            <Input
              id="vehicle-model"
              placeholder="e.g., Camry"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </div>
        </div>

        {/* Year */}
        <div className="space-y-2">
          <Label htmlFor="vehicle-year">Year (optional)</Label>
          <Input
            id="vehicle-year"
            type="number"
            placeholder="e.g., 2020"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          />
        </div>

        {/* Current Value */}
        <div className="space-y-2">
          <Label htmlFor="vehicle-value">Current Value</Label>
          <Input
            id="vehicle-value"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={currentValue}
            onChange={(e) => setCurrentValue(e.target.value)}
          />
        </div>

        {/* Currency */}
        <div className="space-y-2">
          <Label htmlFor="vehicle-currency">Currency</Label>
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

        {/* Owners */}
        {people.length > 0 && (
          <div className="space-y-2">
            <OwnersField
              people={people}
              value={owners}
              onChange={(next) => {
                setOwners(next);
                setOwnersError(null);
              }}
              disabled={isLoading}
            />
            {ownersError && (
              <p className="text-sm text-destructive">{ownersError}</p>
            )}
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isLoading}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isLoading}>
          {isLoading ? "Adding..." : "Add Vehicle"}
        </Button>
      </div>
    </form>
  );
}
