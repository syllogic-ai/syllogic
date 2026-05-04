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
import { createProperty } from "@/lib/actions/properties";
import { PROPERTY_TYPES } from "./types";
import { OwnersField, type OwnerValue } from "@/components/household/owners-field";

type Person = { id: string; name: string; kind: string; color?: string | null; avatarUrl?: string | null };

interface AddPropertyFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function AddPropertyForm({ onSuccess, onCancel }: AddPropertyFormProps) {
  const [isLoading, setIsLoading] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [propertyType, setPropertyType] = useState("");
  const [address, setAddress] = useState("");
  const [currentValue, setCurrentValue] = useState("");
  const [currency, setCurrency] = useState("EUR");

  // Ownership state
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleLoaded, setPeopleLoaded] = useState(false);
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
        // Non-fatal: owners field will be empty; submit is still blocked until peopleLoaded.
      })
      .finally(() => setPeopleLoaded(true));
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
      const r = await fetch(`/api/owners/property/${entityId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owners }),
      });
      if (!r.ok) {
        const text = await r.text().catch(() => "request failed");
        throw new Error(`Failed to save owners: ${text.slice(0, 200)}`);
      }
    } catch (err) {
      toast.error((err as Error).message || "Property created, but failed to save ownership. You can update it later.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter a property name");
      return;
    }

    if (!propertyType) {
      toast.error("Please select a property type");
      return;
    }

    if (!currency) {
      toast.error("Please select a currency");
      return;
    }

    if (!peopleLoaded) {
      setOwnersError("Loading household data, please wait…");
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

      const result = await createProperty({
        name: name.trim(),
        propertyType,
        address: address.trim() || undefined,
        currentValue: value,
        currency,
      });

      if (result.success) {
        if (result.propertyId) {
          await putOwners(result.propertyId);
        }
        toast.success("Property added successfully");
        onSuccess?.();
      } else {
        toast.error(result.error || "Failed to add property");
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
        {/* Property Name */}
        <div className="space-y-2">
          <Label htmlFor="property-name">Property Name</Label>
          <Input
            id="property-name"
            placeholder="e.g., Main Residence"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* Property Type */}
        <div className="space-y-2">
          <Label htmlFor="property-type">Property Type</Label>
          <Select value={propertyType} onValueChange={(v) => v && setPropertyType(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select property type" />
            </SelectTrigger>
            <SelectContent>
              {PROPERTY_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Address */}
        <div className="space-y-2">
          <Label htmlFor="property-address">Address (optional)</Label>
          <Input
            id="property-address"
            placeholder="e.g., 123 Main St, City, State"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
        </div>

        {/* Current Value */}
        <div className="space-y-2">
          <Label htmlFor="property-value">Current Value</Label>
          <Input
            id="property-value"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={currentValue}
            onChange={(e) => setCurrentValue(e.target.value)}
          />
        </div>

        {/* Currency */}
        <div className="space-y-2">
          <Label htmlFor="property-currency">Currency</Label>
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
          {isLoading ? "Adding..." : "Add Property"}
        </Button>
      </div>
    </form>
  );
}
