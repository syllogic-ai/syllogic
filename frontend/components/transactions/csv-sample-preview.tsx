"use client";

import { useMemo } from "react";
import { RiArrowRightLine } from "@remixicon/react";
import type { ColumnMapping } from "@/lib/actions/csv-import";

interface CsvSamplePreviewProps {
  headers: string[];
  sampleRows: string[][];
  mapping: ColumnMapping;
}

const MAPPED_FIELDS = [
  { key: "date", label: "Date" },
  { key: "amount", label: "Amount" },
  { key: "description", label: "Description" },
  { key: "merchant", label: "Merchant" },
  { key: "transactionType", label: "Type" },
] as const;

export function CsvSamplePreview({
  headers,
  sampleRows,
  mapping,
}: CsvSamplePreviewProps) {
  // Get the mapped data based on current mapping selection
  const mappedData = useMemo(() => {
    return sampleRows.slice(0, 5).map((row) => {
      const mapped: Record<string, string> = {};

      MAPPED_FIELDS.forEach((field) => {
        const columnName = mapping[field.key as keyof ColumnMapping] as string | null;
        if (columnName) {
          const columnIndex = headers.indexOf(columnName);
          if (columnIndex !== -1) {
            mapped[field.key] = row[columnIndex] || "";
          }
        }
      });

      return mapped;
    });
  }, [headers, sampleRows, mapping]);

  // Check if any fields are mapped
  const hasMappings = Object.values(mapping).some(
    (value) => value !== null && typeof value !== "object"
  );

  // Get the list of mapped fields for display
  const activeMappings = MAPPED_FIELDS.filter(
    (field) => mapping[field.key as keyof ColumnMapping]
  );

  if (!hasMappings) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8">
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            Map columns on the left to see a preview of your data
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mapping indicators */}
      <div className="flex flex-wrap gap-2">
        {activeMappings.map((field) => {
          const columnName = mapping[field.key as keyof ColumnMapping] as string;
          return (
            <div
              key={field.key}
              className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs"
            >
              <span className="text-muted-foreground">{columnName}</span>
              <RiArrowRightLine className="h-3 w-3 text-muted-foreground" />
              <span className="font-medium">{field.label}</span>
            </div>
          );
        })}
      </div>

      {/* Preview table */}
      <div className="overflow-hidden rounded-lg border">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {activeMappings.map((field) => (
                  <th
                    key={field.key}
                    className="whitespace-nowrap px-4 py-3 text-left text-xs font-medium text-muted-foreground"
                  >
                    {field.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {mappedData.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-muted/30">
                  {activeMappings.map((field) => (
                    <td key={field.key} className="whitespace-nowrap px-4 py-3">
                      {row[field.key] || (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Showing {mappedData.length} of {sampleRows.length} sample rows
      </p>
    </div>
  );
}
