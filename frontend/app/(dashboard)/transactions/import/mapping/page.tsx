"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RiArrowLeftLine, RiArrowRightLine, RiSparklingLine } from "@remixicon/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Header } from "@/components/layout/header";
import { CsvMappingTable } from "@/components/transactions/csv-mapping-table";
import { CsvSamplePreview } from "@/components/transactions/csv-sample-preview";
import {
  parseCsvHeaders,
  getAiColumnMapping,
  saveColumnMapping,
  getCsvImportSession,
  type ColumnMapping,
  type ParsedCsvData,
} from "@/lib/actions/csv-import";

function MappingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const importId = searchParams.get("id");

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isAiMapping, setIsAiMapping] = useState(false);
  const [csvData, setCsvData] = useState<ParsedCsvData | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>({
    date: null,
    amount: null,
    description: null,
    merchant: null,
    transactionType: null,
    typeConfig: {
      isAmountSigned: false,
    },
  });

  const aiMappingTriggeredRef = useRef(false);

  const triggerAiMapping = useCallback(async (id: string, data: ParsedCsvData) => {
    if (aiMappingTriggeredRef.current) return;
    aiMappingTriggeredRef.current = true;

    setIsAiMapping(true);
    try {
      const result = await getAiColumnMapping(id, data.headers, data.sampleRows);
      if (result.success && result.mapping) {
        setMapping(result.mapping);
        toast.success("AI mapping applied automatically");
      }
    } catch {
      // Silently fail - user can still manually map
    } finally {
      setIsAiMapping(false);
    }
  }, []);

  const loadData = useCallback(async () => {
    if (!importId) {
      toast.error("Import ID not found");
      router.push("/transactions/import");
      return;
    }

    try {
      // Check if import session exists
      const session = await getCsvImportSession(importId);
      if (!session) {
        toast.error("Import session not found");
        router.push("/transactions/import");
        return;
      }

      // If existing mapping available, use it and skip AI mapping
      const hasExistingMapping = session.columnMapping &&
        (session.columnMapping.date || session.columnMapping.amount || session.columnMapping.description);

      if (hasExistingMapping) {
        setMapping(session.columnMapping!);
        aiMappingTriggeredRef.current = true; // Don't trigger AI if mapping exists
      }

      // Parse CSV headers
      const result = await parseCsvHeaders(importId);
      if (result.success && result.data) {
        setCsvData(result.data);

        // Auto-trigger AI mapping if no existing mapping
        if (!hasExistingMapping) {
          triggerAiMapping(importId, result.data);
        }
      } else {
        toast.error(result.error || "Failed to parse CSV");
        router.push("/transactions/import");
      }
    } catch (error) {
      console.error("Failed to load data:", error);
      toast.error("Failed to load import data");
      router.push("/transactions/import");
    } finally {
      setIsLoading(false);
    }
  }, [importId, router, triggerAiMapping]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleContinue = async () => {
    if (!importId) return;

    // Validate required fields
    if (!mapping.date || !mapping.amount || !mapping.description) {
      toast.error("Please map all required fields");
      return;
    }

    setIsSaving(true);
    try {
      const result = await saveColumnMapping(importId, mapping);
      if (result.success) {
        router.push(`/transactions/import/preview?id=${importId}`);
      } else {
        toast.error(result.error || "Failed to save mapping");
      }
    } catch {
      toast.error("Failed to save mapping");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <>
        <Header title="Map Columns" />
        <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
          <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
              <p className="text-muted-foreground">Loading CSV data...</p>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (!csvData) {
    return null;
  }

  return (
    <>
      <Header title="Map Columns" />
      <div className="flex flex-1 flex-col p-4 pt-0">
        {/* AI Mapping Status Banner */}
        {isAiMapping && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border bg-muted/50 px-4 py-3">
            <RiSparklingLine className="h-4 w-4 animate-pulse text-primary" />
            <span className="text-sm">Analyzing your CSV with AI...</span>
          </div>
        )}

        {/* Main Container with 2-Column Layout */}
        <div className="flex-1 rounded-lg border bg-card">
          <div className="grid h-full lg:grid-cols-2 lg:divide-x">
            {/* Left Column - Field Mapping */}
            <div className="flex flex-col p-6">
              <div className="mb-4">
                <h2 className="text-lg font-semibold">Field Mapping</h2>
                <p className="text-sm text-muted-foreground">
                  Match each CSV column to the corresponding transaction field
                </p>
              </div>
              <div className="flex-1 overflow-y-auto">
                <CsvMappingTable
                  headers={csvData.headers}
                  mapping={mapping}
                  onMappingChange={setMapping}
                />
              </div>
            </div>

            {/* Right Column - Dynamic Sample Preview */}
            <div className="flex flex-col border-t p-6 lg:border-t-0">
              <CsvSamplePreview
                headers={csvData.headers}
                sampleRows={csvData.sampleRows}
                mapping={mapping}
              />
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="mt-6 flex items-center justify-between border-t pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/transactions/import")}
          >
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button onClick={handleContinue} disabled={isSaving || isAiMapping}>
            {isSaving ? "Saving..." : "Preview Transactions"}
            <RiArrowRightLine className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

export default function MappingPage() {
  return (
    <Suspense
      fallback={
        <>
          <Header title="Map Columns" />
          <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
            <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
              <div className="text-center">
                <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
                <p className="text-muted-foreground">Loading...</p>
              </div>
            </div>
          </div>
        </>
      }
    >
      <MappingPageContent />
    </Suspense>
  );
}
