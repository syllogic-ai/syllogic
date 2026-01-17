"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import type { ColumnMapping } from "@/lib/actions/csv-import";

interface CsvMappingTableProps {
  headers: string[];
  mapping: ColumnMapping;
  onMappingChange: (mapping: ColumnMapping) => void;
}

const FIELD_MAPPINGS = [
  { key: "date", label: "Date", description: "Transaction date", required: true },
  { key: "amount", label: "Amount", description: "Transaction amount", required: true },
  { key: "description", label: "Description", description: "Transaction description", required: true },
  { key: "merchant", label: "Merchant", description: "Merchant/payee name", required: false },
  { key: "transactionType", label: "Type", description: "Credit/Debit indicator", required: false },
] as const;

export function CsvMappingTable({
  headers,
  mapping,
  onMappingChange,
}: CsvMappingTableProps) {
  const updateMapping = (field: keyof ColumnMapping, value: string | null) => {
    onMappingChange({
      ...mapping,
      [field]: value === "none" ? null : value,
    });
  };

  const updateTypeConfig = (key: string, value: string | boolean) => {
    onMappingChange({
      ...mapping,
      typeConfig: {
        ...mapping.typeConfig,
        [key]: value,
      },
    });
  };

  return (
    <div className="space-y-6">
      {/* Field Mappings as List */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground">Column Mappings</h3>
        <div className="space-y-3">
          {FIELD_MAPPINGS.map((field) => (
            <div
              key={field.key}
              className="flex items-center justify-between gap-4 rounded-lg border bg-card p-4"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Label className="font-medium">
                    {field.label}
                    {field.required && <span className="ml-1 text-destructive">*</span>}
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">{field.description}</p>
              </div>
              <Select
                value={mapping[field.key as keyof ColumnMapping] as string || "none"}
                onValueChange={(value) => updateMapping(field.key as keyof ColumnMapping, value)}
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Select column" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">-- Not mapped --</SelectItem>
                  {headers.map((header) => (
                    <SelectItem key={header} value={header}>
                      {header}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>
      </div>

      {/* Amount Sign Configuration */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center space-x-3">
          <Checkbox
            id="isAmountSigned"
            checked={mapping.typeConfig?.isAmountSigned ?? false}
            onCheckedChange={(checked) => updateTypeConfig("isAmountSigned", !!checked)}
          />
          <div>
            <Label htmlFor="isAmountSigned" className="font-medium">
              Amount is signed
            </Label>
            <p className="text-xs text-muted-foreground">
              Positive values = income, negative values = expense
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
