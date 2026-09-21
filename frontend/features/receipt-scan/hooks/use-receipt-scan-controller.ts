"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { getUserAccounts } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";
import {
  filterSelectableCategories,
  filterCategoriesByType,
} from "@/lib/utils/category-utils";
import type { CategoryDisplay } from "@/shared/domain/display-contracts";
import {
  confirmReceiptScan,
  correctReceiptScanLines,
  getReceiptScanStatus,
  previewReceiptScanGroups,
  uploadAndExtractReceipt,
} from "../server/actions";
import type {
  ReceiptGroupPreview,
  ReceiptLineItem,
  ReceiptScanAccount,
  ReceiptScanResult,
  ReceiptValidationError,
} from "../domain/contracts";

type Step = "upload" | "extracting" | "reviewing" | "needs_review";

// Polling: 2s, backing off by 1.5x each attempt up to an 8s ceiling per
// attempt, giving up (leaving the scan `pending`, with a manual retry
// offered) at 90s total. A worker that hasn't answered by then should
// surface as a stuck scan, not spin the polling loop forever.
const POLL_INITIAL_DELAY_MS = 2000;
const POLL_MAX_DELAY_MS = 8000;
const POLL_BACKOFF_FACTOR = 1.5;
const POLL_CEILING_MS = 90000;

export function useReceiptScanController() {
  const router = useRouter();

  const [accounts, setAccounts] = useState<ReceiptScanAccount[]>([]);
  const [categories, setCategories] = useState<CategoryDisplay[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");

  const [step, setStep] = useState<Step>("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);

  const [receiptScanId, setReceiptScanId] = useState<string | null>(null);
  const [merchantName, setMerchantName] = useState<string | null>(null);
  const [receiptTotal, setReceiptTotal] = useState<string | null>(null);
  const [items, setItems] = useState<ReceiptLineItem[]>([]);
  // Snapshot of `items` as last returned by the server -- used to diff
  // against the live, editable `items` when building a correction payload
  // (Phase 6.5), so only lines that actually changed are sent rather than
  // the whole set every time.
  const [baselineItems, setBaselineItems] = useState<ReceiptLineItem[]>([]);
  const [validationErrors, setValidationErrors] = useState<
    ReceiptValidationError[]
  >([]);
  const [isSavingCorrections, setIsSavingCorrections] = useState(false);

  // The server-computed grouping (spec 6.1/6.2) for the *current* per-line
  // category assignments -- `groupPreview.resolved` is the only thing ever
  // submitted to confirm. Recomputed via `/resolve` on every category edit
  // so the grouping/collapse policy is never reimplemented here.
  const [groupPreview, setGroupPreview] = useState<ReceiptGroupPreview | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewRequestIdRef = useRef(0);

  const clearPoll = useCallback(() => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => clearPoll();
  }, [clearPoll]);

  useEffect(() => {
    void getUserAccounts().then((data) => {
      setAccounts(data);
      if (data[0]) setSelectedAccountId(data[0].id);
    });
    void getUserCategories().then((data) => {
      setCategories(
        filterSelectableCategories(filterCategoriesByType(data, "expense")),
      );
    });
  }, []);

  const selectFile = (file: File) => {
    setSelectedFile(file);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  };

  const clearFile = () => {
    setSelectedFile(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  };

  const refreshGroupPreview = useCallback(
    async (scanId: string, currentItems: ReceiptLineItem[]) => {
      const overrides = currentItems
        .filter((item): item is ReceiptLineItem & { lineRef: string } => !!item.lineRef)
        .map((item) => ({ lineRef: item.lineRef, categoryId: item.categoryId }));

      if (overrides.length === 0) {
        setGroupPreview(null);
        return;
      }

      const requestId = ++previewRequestIdRef.current;
      setIsPreviewing(true);
      try {
        const result = await previewReceiptScanGroups(scanId, overrides);
        // A newer edit may have fired another request while this one was
        // in flight -- only the latest response should ever land.
        if (requestId !== previewRequestIdRef.current) return;
        setGroupPreview(result.success && result.preview ? result.preview : null);
      } finally {
        if (requestId === previewRequestIdRef.current) setIsPreviewing(false);
      }
    },
    [],
  );

  const applyScanResult = useCallback(
    (scan: ReceiptScanResult) => {
      setMerchantName(scan.merchantName);
      setReceiptTotal(scan.receiptTotal);
      setValidationErrors(scan.validationErrors);
      setItems(scan.items);
      setBaselineItems(scan.items);
      setGroupPreview(null);

      if (scan.status === "needs_review") {
        setStep("needs_review");
        return;
      }
      // "processed" and "completed" (re-opening an already-confirmed scan)
      // both land on the ordinary review screen.
      setStep("reviewing");
      void refreshGroupPreview(scan.receiptScanId, scan.items);
    },
    [refreshGroupPreview],
  );

  const pollReceiptScan = useCallback(
    (scanId: string, startedAt: number, delayMs: number) => {
      clearPoll();
      pollTimeoutRef.current = setTimeout(() => {
        void (async () => {
          const result = await getReceiptScanStatus(scanId);

          if (!result.success || !result.result) {
            toast.error(result.error ?? "Failed to check receipt status");
            setStep("upload");
            return;
          }

          const scan = result.result;

          if (scan.status === "failed" || scan.status === "error") {
            toast.error(scan.errorMessage ?? "Failed to process receipt");
            setStep("upload");
            return;
          }

          if (scan.status !== "pending") {
            applyScanResult(scan);
            return;
          }

          if (Date.now() - startedAt >= POLL_CEILING_MS) {
            // Leave the scan `pending` and stop polling automatically --
            // the worker may still finish it later, but the UI must not
            // spin forever. `retryPolling` lets the user check again.
            setPollTimedOut(true);
            return;
          }

          pollReceiptScan(
            scanId,
            startedAt,
            Math.min(delayMs * POLL_BACKOFF_FACTOR, POLL_MAX_DELAY_MS),
          );
        })();
      }, delayMs);
    },
    [applyScanResult, clearPoll],
  );

  const retryPolling = () => {
    if (!receiptScanId) return;
    setPollTimedOut(false);
    pollReceiptScan(receiptScanId, Date.now(), POLL_INITIAL_DELAY_MS);
  };

  const extract = async () => {
    if (!selectedAccountId) {
      toast.error("Please select an account");
      return;
    }
    if (!selectedFile) {
      toast.error("Please upload a receipt photo");
      return;
    }
    setIsUploading(true);
    try {
      const fileBuffer = await selectedFile.arrayBuffer();
      const result = await uploadAndExtractReceipt(
        selectedAccountId,
        fileBuffer,
        selectedFile.type || "image/jpeg",
      );
      if (result.success && result.result) {
        setReceiptScanId(result.result.receiptScanId);
        setPollTimedOut(false);
        setStep("extracting");
        if (result.result.status === "pending") {
          pollReceiptScan(
            result.result.receiptScanId,
            Date.now(),
            POLL_INITIAL_DELAY_MS,
          );
        } else {
          applyScanResult(result.result);
        }
      } else {
        toast.error(result.error ?? "Failed to process receipt");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const updateItemCategory = (
    key: string,
    categoryId: string | null,
    categoryName: string | null,
  ) => {
    setItems((prev) => {
      const next = prev.map((item) =>
        item.key === key
          ? { ...item, categoryId, categoryName, userEdited: true }
          : item,
      );
      if (receiptScanId) void refreshGroupPreview(receiptScanId, next);
      return next;
    });
  };

  // --- Line corrections (Phase 6.5) ---------------------------------------
  // Only available in the `needs_review` view: editing a line's amount/name,
  // adding a missed line, or removing a hallucinated one. Category edits
  // above stay a separate, client-only concern until confirm time -- these
  // instead need to reach the server, since `receipt_validate.validate()`
  // (never the client) decides whether the correction actually reconciles.

  const updateItemAmount = (key: string, amount: string) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, amount } : item)),
    );
  };

  const updateItemDescription = (key: string, description: string) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, description } : item)),
    );
  };

  const addBlankItem = () => {
    setItems((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        lineRef: null,
        description: "",
        amount: "0",
        categoryId: null,
        categoryName: null,
        categoryConfidence: null,
        categoryReason: null,
        userEdited: true,
        transactionType: "debit",
      },
    ]);
  };

  const removeItem = (key: string) => {
    setItems((prev) => prev.filter((item) => item.key !== key));
  };

  const saveCorrections = async () => {
    if (!receiptScanId) return;

    const baselineByRef = new Map(
      baselineItems
        .filter((item): item is ReceiptLineItem & { lineRef: string } => !!item.lineRef)
        .map((item) => [item.lineRef, item]),
    );
    const currentRefs = new Set(
      items.filter((item) => !!item.lineRef).map((item) => item.lineRef as string),
    );

    const edits = items
      .filter((item): item is ReceiptLineItem & { lineRef: string } => !!item.lineRef)
      .map((item) => {
        const baseline = baselineByRef.get(item.lineRef);
        if (!baseline) return null;
        const amountChanged = baseline.amount !== item.amount;
        const nameChanged = baseline.description !== item.description;
        if (!amountChanged && !nameChanged) return null;
        return {
          lineRef: item.lineRef,
          ...(nameChanged ? { name: item.description } : {}),
          ...(amountChanged ? { netAmount: item.amount || "0" } : {}),
        };
      })
      .filter((edit): edit is NonNullable<typeof edit> => edit !== null);

    const inserts = items
      .filter((item) => !item.lineRef)
      .map((item) => ({
        name: item.description || null,
        netAmount: item.amount || "0",
      }));

    const deletes = [...baselineByRef.keys()].filter((ref) => !currentRefs.has(ref));

    if (edits.length === 0 && inserts.length === 0 && deletes.length === 0) {
      toast.error("No changes to save");
      return;
    }

    setIsSavingCorrections(true);
    try {
      const result = await correctReceiptScanLines(receiptScanId, {
        edits,
        inserts,
        deletes,
      });
      if (result.success && result.result) {
        applyScanResult(result.result);
        toast.success(
          result.result.status === "needs_review"
            ? "Saved -- some lines still don't add up"
            : "Corrections saved",
        );
      } else {
        toast.error(result.error ?? "Failed to save your corrections");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsSavingCorrections(false);
    }
  };

  const itemsTotal = items.reduce(
    (sum, item) => sum + (Number(item.amount) || 0),
    0,
  );

  const detectedTotal = receiptTotal ? Number(receiptTotal) : null;

  const canConfirm =
    step !== "needs_review" &&
    !isPreviewing &&
    !!groupPreview &&
    groupPreview.resolved.length > 0;

  const flaggedLineRefs = new Set(
    validationErrors.flatMap((error) => error.lineRefs),
  );

  const confirm = async () => {
    if (!receiptScanId) return;
    if (!groupPreview || groupPreview.resolved.length === 0) {
      toast.error("Still computing how this receipt will be booked -- try again in a moment");
      return;
    }
    setIsSubmitting(true);
    try {
      const result = await confirmReceiptScan(receiptScanId, groupPreview.resolved);
      if (result.success) {
        toast.success(
          result.alreadyBooked
            ? "This receipt was already booked"
            : `Created ${result.transactionCount ?? groupPreview.resolved.length} transaction(s)`,
        );
        router.push("/transactions");
      } else {
        toast.error(result.error ?? "Failed to save transactions");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const goBack = () => {
    if (step === "extracting") {
      clearPoll();
    }
    if (step !== "upload") {
      setStep("upload");
      return;
    }
    router.push("/transactions");
  };

  return {
    accounts,
    categories,
    selectedAccountId,
    setSelectedAccountId,
    step,
    selectedFile,
    previewUrl,
    isUploading,
    isSubmitting,
    pollTimedOut,
    retryPolling,
    selectFile,
    clearFile,
    extract,
    merchantName,
    receiptTotal,
    items,
    itemsTotal,
    detectedTotal,
    canConfirm,
    validationErrors,
    flaggedLineRefs,
    updateItemCategory,
    updateItemAmount,
    updateItemDescription,
    addBlankItem,
    removeItem,
    saveCorrections,
    isSavingCorrections,
    groupPreview,
    isPreviewing,
    confirm,
    goBack,
  };
}
