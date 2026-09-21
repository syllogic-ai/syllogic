export interface ReceiptScanAccount {
  id: string;
  name: string;
  currency: string | null;
}

export interface ReceiptLineItem {
  /** Stable client-side key so rows can be edited reliably. */
  key: string;
  /** The extraction's own line reference (e.g. "L1"). Every line the
   * backend returns has one -- it is how `groups[].lineRefs` (Phase 6) ties
   * a booked transaction back to the lines that make it up. */
  lineRef: string | null;
  description: string;
  amount: string;
  categoryId: string | null;
  categoryName: string | null;
  /** "high" | "medium" | "low" | null -- stage 2's own confidence in this
   * line's category, surfaced so a low-confidence guess is visibly a guess
   * rather than indistinguishable from a confident one. */
  categoryConfidence: string | null;
  categoryReason: string | null;
  /** True once the user has changed this line's category away from what
   * extraction/categorization assigned -- confirm sets this server-side
   * too (`ReceiptLineItem.user_edited`), this mirrors it for display. */
  userEdited: boolean;
  transactionType: "debit" | "credit";
}

export interface ReceiptValidationError {
  code: string;
  message: string;
  lineRefs: string[];
}

/** One category's worth of a receipt -- what `receipt_resolve.resolve`
 * (backend, Phase 6) calls a `TransactionGroup`. `lineRefs` is always a
 * subset of the current `ReceiptLineItem[]`'s line refs; groups are
 * recomputed (via `/resolve`) whenever a line's category changes, never
 * built independently in the client. */
export interface ReceiptGroup {
  categoryId: string | null;
  categoryName: string | null;
  amount: string;
  lineRefs: string[];
}

/** The collapsed-vs-uncollapsed comparison the review screen shows before
 * booking (spec 6.1/6.2): `uncollapsed` is the raw per-category grouping,
 * `resolved` is what confirm will actually book once the merchant/threshold
 * policy is applied. Only `resolved` is ever submitted to confirm -- the
 * policy that produces it lives once, server-side. */
export interface ReceiptGroupPreview {
  uncollapsed: ReceiptGroup[];
  resolved: ReceiptGroup[];
}

/** Mirrors `receipt_scans.status` (`pending | processed | needs_review |
 * completed | failed`) plus the frontend-only `"error"` used when the
 * upload/poll itself fails outside of any scan row. */
export type ReceiptScanStatus =
  | "pending"
  | "processed"
  | "needs_review"
  | "completed"
  | "failed"
  | "error";

export interface ReceiptScanResult {
  receiptScanId: string;
  status: ReceiptScanStatus;
  merchantName: string | null;
  receiptTotal: string | null;
  currency: string | null;
  items: ReceiptLineItem[];
  validationErrors: ReceiptValidationError[];
  errorMessage: string | null;
}

/** Phase 6.5: the only way to correct a `needs_review` scan (spec 1.2 --
 * refusing to book a misread receipt is only better than booking it
 * silently if correcting it is actually possible). Sent to
 * `PATCH /{id}/lines`, which re-runs validation server-side and flips
 * `status` both ways rather than trusting this payload's arithmetic.
 * `lineRef` is never assigned client-side for an insert -- the server
 * assigns it and the corrected `ReceiptScanResult` is the only place a new
 * line's `lineRef` is learned. */
export interface ReceiptLineCorrections {
  edits: Array<{ lineRef: string; name?: string; netAmount?: string }>;
  inserts: Array<{ name: string | null; netAmount: string }>;
  deletes: string[];
}
