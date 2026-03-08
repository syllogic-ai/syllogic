"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiCheckLine,
  RiLoader4Line,
  RiSparklingLine,
  RiSendPlane2Line,
  RiAlertLine,
  RiCheckboxCircleLine,
  RiInformationLine,
  RiScales3Line,
} from "@remixicon/react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Header } from "@/components/layout/header";
import { CsvUploadDropzone } from "@/components/transactions/csv-upload-dropzone";
import { getUserAccounts } from "@/lib/actions/transactions";
import {
  uploadFileForAgenticImport,
  analyzeImport,
  approveAgenticImport,
  checkOpenAiAvailable,
} from "@/lib/actions/agentic-import";
import type { Account } from "@/lib/db/schema";

type Step = "upload" | "analyzing" | "clarify" | "preview" | "importing" | "result";

interface ImportResult {
  total_rows: number;
  imported: number;
  duplicates_skipped: number;
  failed_rows: { row_number: number; reason: string }[];
  balance_anchors_detected: boolean;
}

export default function AgenticImportPage() {
  const router = useRouter();

  // State
  const [step, setStep] = useState<Step>("upload");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(true);

  // Import session state
  const [importId, setImportId] = useState("");
  const [mappingSummary, setMappingSummary] = useState("");
  const [transformationDesc, setTransformationDesc] = useState("");
  const [balanceColumn, setBalanceColumn] = useState<string | null>(null);
  const [sampleTransactions, setSampleTransactions] = useState<Record<string, unknown>[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [profileLabel, setProfileLabel] = useState<string | null>(null);

  // Clarification
  const [question, setQuestion] = useState("");
  const [clarificationInput, setClarificationInput] = useState("");

  // Result
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    getUserAccounts().then((accts) => {
      setAccounts(accts);
      if (accts.length > 0) setSelectedAccountId(accts[0].id);
    });
    checkOpenAiAvailable().then(setAiAvailable);
  }, []);

  const handleFileSelect = useCallback((_file: File, _content: string) => {
    setSelectedFile(_file);
  }, []);

  const handleUpload = async () => {
    if (!selectedAccountId || !selectedFile) {
      toast.error("Please select an account and upload a file");
      return;
    }
    setIsLoading(true);
    setStep("analyzing");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("account_id", selectedAccountId);

      const result = await uploadFileForAgenticImport(formData);

      if (!result.success || !result.data) {
        toast.error(result.error || "Upload failed");
        setStep("upload");
        return;
      }

      const d = result.data;
      setImportId(d.import_id);

      if (d.status === "profile_matched") {
        setProfileLabel(d.profile_label || null);
        setMappingSummary(d.mapping_summary || "");
        setTransformationDesc(d.transformation_description || "");
        setBalanceColumn(d.balance_column || null);
        setSampleTransactions(d.sample_transactions || []);
        setTotalRows(d.total_rows || 0);
        setStep("preview");
      } else {
        await runAnalysis(d.import_id);
      }
    } catch {
      toast.error("An error occurred during upload");
      setStep("upload");
    } finally {
      setIsLoading(false);
    }
  };

  const runAnalysis = async (id: string, clarification?: string) => {
    setIsLoading(true);
    setStep("analyzing");

    try {
      const result = await analyzeImport(id, clarification);

      if (!result.success || !result.data) {
        toast.error(result.error || "Analysis failed");
        setStep("upload");
        return;
      }

      const d = result.data;

      if (d.status === "needs_clarification") {
        setQuestion(d.question || "");
        setStep("clarify");
      } else if (d.status === "preview_ready") {
        setMappingSummary(d.mapping_summary || "");
        setTransformationDesc(d.transformation_description || "");
        setBalanceColumn(d.balance_column || null);
        setSampleTransactions(d.sample_transactions || []);
        setTotalRows(d.total_rows || 0);
        setStep("preview");
      } else {
        toast.error(d.error || "Failed to process file. Try re-exporting from your bank.");
        setStep("upload");
      }
    } catch {
      toast.error("Analysis failed");
      setStep("upload");
    } finally {
      setIsLoading(false);
    }
  };

  const handleClarificationSubmit = async () => {
    if (!clarificationInput.trim()) return;
    setClarificationInput("");
    await runAnalysis(importId, clarificationInput.trim());
  };

  const handleApprove = async () => {
    setIsLoading(true);
    setStep("importing");

    try {
      const result = await approveAgenticImport(importId, selectedAccountId);

      if (!result.success || !result.data) {
        toast.error(result.error || "Import failed");
        setStep("preview");
        return;
      }

      setImportResult(result.data);
      setStep("result");
    } catch {
      toast.error("Import failed");
      setStep("preview");
    } finally {
      setIsLoading(false);
    }
  };

  if (!aiAvailable) {
    return (
      <>
        <Header title="Import Transactions" />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-4 pt-0">
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RiAlertLine className="h-5 w-5 text-amber-500" />
                AI Import Not Available
              </CardTitle>
              <CardDescription>
                The AI-powered import feature requires an OpenAI API key.
                Please configure the <code className="bg-muted px-1 rounded">OPENAI_API_KEY</code> environment variable to enable this feature.
              </CardDescription>
            </CardHeader>
            <CardFooter>
              <Button variant="outline" onClick={() => router.push("/transactions")}>
                <RiArrowLeftLine className="mr-2 h-4 w-4" /> Back to Transactions
              </Button>
            </CardFooter>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Header title="Import Transactions" />
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-4 pt-0">
        {/* STEP: Upload */}
        {step === "upload" && (
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RiSparklingLine className="h-5 w-5" />
                AI-Powered Import
              </CardTitle>
              <CardDescription>
                Upload a CSV or XLSX file from your bank. Our AI will automatically detect the
                format, map columns, and extract your transactions.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>Select Account</Label>
                {accounts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No accounts found. Please create an account first.
                  </p>
                ) : (
                  <Select value={selectedAccountId} onValueChange={(v) => v && setSelectedAccountId(v)}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select an account">
                        {accounts.find((a) => a.id === selectedAccountId)?.name ?? "Select an account"}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent className="w-auto min-w-[var(--anchor-width)] max-w-[90vw]">
                      {accounts.map((account) => (
                        <SelectItem key={account.id} value={account.id} className="pr-10">
                          {account.name} ({account.currency})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className="space-y-2">
                <Label>Upload File</Label>
                <CsvUploadDropzone onFileSelect={handleFileSelect} isUploading={isLoading} />
              </div>
            </CardContent>
            <CardFooter className="justify-between">
              <Button variant="outline" onClick={() => router.push("/transactions")}>
                <RiArrowLeftLine className="mr-2 h-4 w-4" /> Cancel
              </Button>
              <Button onClick={handleUpload} disabled={isLoading || !selectedFile || !selectedAccountId}>
                {isLoading ? "Processing…" : "Analyze & Import"}
                <RiArrowRightLine className="ml-2 h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        )}

        {/* STEP: Analyzing */}
        {step === "analyzing" && (
          <Card className="w-full max-w-2xl">
            <CardContent className="flex flex-col items-center gap-4 py-16">
              <RiLoader4Line className="h-10 w-10 animate-spin text-primary" />
              <div className="text-center">
                <p className="text-lg font-medium">Analyzing your file…</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Our AI is reading the file structure and generating a transformation script.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP: Clarification */}
        {step === "clarify" && (
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RiInformationLine className="h-5 w-5 text-blue-500" />
                Quick Question
              </CardTitle>
              <CardDescription>
                We need a bit more information to parse your file correctly.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg bg-muted p-4">
                <p className="text-sm">{question}</p>
              </div>
              <div className="flex gap-2">
                <Input
                  value={clarificationInput}
                  onChange={(e) => setClarificationInput(e.target.value)}
                  placeholder="Type your answer…"
                  onKeyDown={(e) => e.key === "Enter" && handleClarificationSubmit()}
                  disabled={isLoading}
                />
                <Button onClick={handleClarificationSubmit} disabled={isLoading || !clarificationInput.trim()}>
                  <RiSendPlane2Line className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP: Preview */}
        {step === "preview" && (
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RiCheckboxCircleLine className="h-5 w-5 text-green-500" />
                Import Preview
              </CardTitle>
              <CardDescription>
                {profileLabel
                  ? `We recognised this file format — using your saved profile: ${profileLabel}`
                  : "Review the mapping below and approve the import."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Mapping summary */}
              {mappingSummary && (
                <div className="rounded-lg border p-4 space-y-2">
                  <p className="text-sm font-medium">Column Mapping</p>
                  <p className="text-sm text-muted-foreground">{mappingSummary}</p>
                </div>
              )}

              {/* Transformation description */}
              {transformationDesc && (
                <div className="rounded-lg border p-4 space-y-2">
                  <p className="text-sm font-medium">Transformation Logic</p>
                  <p className="text-sm text-muted-foreground">{transformationDesc}</p>
                </div>
              )}

              {/* Balance callout */}
              {balanceColumn && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950 p-4 space-y-1">
                  <p className="text-sm font-medium flex items-center gap-2">
                    <RiScales3Line className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    Balance Anchors Detected
                  </p>
                  <p className="text-sm text-muted-foreground">
                    A balance column was found in your file. These values will be used as
                    authoritative balance reference points, taking priority over calculated balances.
                  </p>
                </div>
              )}

              {/* Transaction count */}
              <div className="rounded-lg border p-4">
                <p className="text-sm">
                  <span className="font-medium">{totalRows}</span> transaction{totalRows !== 1 ? "s" : ""} found in file
                </p>
              </div>

              {/* Sample transactions table */}
              {sampleTransactions.length > 0 && (
                <div className="rounded-lg border overflow-hidden">
                  <div className="px-4 py-2 bg-muted border-b">
                    <p className="text-xs font-medium text-muted-foreground">
                      Sample Transactions (first {sampleTransactions.length})
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="px-3 py-2 text-left font-medium">Date</th>
                          <th className="px-3 py-2 text-left font-medium">Description</th>
                          <th className="px-3 py-2 text-right font-medium">Amount</th>
                          {sampleTransactions[0]?.balance != null && (
                            <th className="px-3 py-2 text-right font-medium">Balance</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {sampleTransactions.map((tx, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="px-3 py-2 whitespace-nowrap">
                              {String(tx.date || "").slice(0, 10)}
                            </td>
                            <td className="px-3 py-2 truncate max-w-[200px]">
                              {String(tx.description || "")}
                            </td>
                            <td className={`px-3 py-2 text-right whitespace-nowrap ${Number(tx.amount) < 0 ? "text-red-600" : "text-green-600"}`}>
                              {Number(tx.amount).toFixed(2)}
                            </td>
                            {sampleTransactions[0]?.balance != null && (
                              <td className="px-3 py-2 text-right whitespace-nowrap">
                                {tx.balance != null ? Number(tx.balance).toFixed(2) : "—"}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
            <CardFooter className="justify-between">
              <Button variant="outline" onClick={() => { setStep("upload"); setSelectedFile(null); }}>
                <RiArrowLeftLine className="mr-2 h-4 w-4" /> Cancel
              </Button>
              <Button onClick={handleApprove} disabled={isLoading}>
                {isLoading ? (
                  <>
                    <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" /> Importing…
                  </>
                ) : (
                  <>
                    <RiCheckLine className="mr-2 h-4 w-4" /> Approve & Import
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>
        )}

        {/* STEP: Importing */}
        {step === "importing" && (
          <Card className="w-full max-w-2xl">
            <CardContent className="flex flex-col items-center gap-4 py-16">
              <RiLoader4Line className="h-10 w-10 animate-spin text-primary" />
              <div className="text-center">
                <p className="text-lg font-medium">Importing transactions…</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Running duplicate detection and importing {totalRows} transaction{totalRows !== 1 ? "s" : ""}.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP: Result */}
        {step === "result" && importResult && (
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RiCheckboxCircleLine className="h-5 w-5 text-green-500" />
                Import Complete
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold">{importResult.total_rows}</p>
                  <p className="text-xs text-muted-foreground">Total Rows</p>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-green-600">{importResult.imported}</p>
                  <p className="text-xs text-muted-foreground">Imported</p>
                </div>
              </div>

              {importResult.duplicates_skipped > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950 p-4">
                  <p className="text-sm">
                    <span className="font-medium">{importResult.duplicates_skipped}</span> duplicate{importResult.duplicates_skipped !== 1 ? "s" : ""} skipped
                  </p>
                </div>
              )}

              {importResult.balance_anchors_detected && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950 p-4">
                  <p className="text-sm flex items-center gap-2">
                    <RiScales3Line className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    Balance anchors were applied from file data.
                  </p>
                </div>
              )}

              {importResult.failed_rows.length > 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950 p-4 space-y-2">
                  <p className="text-sm font-medium">
                    {importResult.failed_rows.length} row{importResult.failed_rows.length !== 1 ? "s" : ""} failed:
                  </p>
                  <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
                    {importResult.failed_rows.map((f, i) => (
                      <li key={i}>
                        Row {f.row_number}: {f.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
            <CardFooter>
              <Button onClick={() => router.push("/transactions")} className="w-full">
                Go to Transactions
              </Button>
            </CardFooter>
          </Card>
        )}
      </div>
    </>
  );
}
