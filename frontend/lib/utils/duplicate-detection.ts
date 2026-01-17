import type { Transaction } from "@/lib/db/schema";
import type { PreviewTransaction } from "@/lib/actions/csv-import";

/**
 * Calculate similarity between two strings using Levenshtein distance
 * Returns a value between 0 (completely different) and 1 (identical)
 */
function stringSimilarity(str1: string, str2: string): number {
  const s1 = str1.toLowerCase().trim();
  const s2 = str2.toLowerCase().trim();

  if (s1 === s2) return 1;
  if (s1.length === 0 || s2.length === 0) return 0;

  // Simple Levenshtein distance implementation
  const matrix: number[][] = [];

  for (let i = 0; i <= s1.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= s2.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= s1.length; i++) {
    for (let j = 1; j <= s2.length; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1, // deletion
        matrix[i][j - 1] + 1, // insertion
        matrix[i - 1][j - 1] + cost // substitution
      );
    }
  }

  const maxLength = Math.max(s1.length, s2.length);
  return 1 - matrix[s1.length][s2.length] / maxLength;
}

/**
 * Check if two dates are on the same day
 */
function isSameDay(date1: Date, date2: Date): boolean {
  return (
    date1.getFullYear() === date2.getFullYear() &&
    date1.getMonth() === date2.getMonth() &&
    date1.getDate() === date2.getDate()
  );
}

/**
 * Check if two amounts are equal (with small tolerance for floating point)
 */
function amountsEqual(amount1: number, amount2: number): boolean {
  return Math.abs(amount1 - amount2) < 0.01;
}

export interface DuplicateMatch {
  previewIndex: number;
  existingTransaction: Transaction;
  confidence: number; // 0-1 score
  reasons: string[];
}

/**
 * Detect potential duplicates between preview transactions and existing transactions
 * Criteria: same amount + same date + similar description (>85% fuzzy match)
 */
export function detectDuplicates(
  previewTransactions: PreviewTransaction[],
  existingTransactions: Transaction[],
  similarityThreshold: number = 0.85
): Map<number, DuplicateMatch> {
  const duplicates = new Map<number, DuplicateMatch>();

  for (const preview of previewTransactions) {
    const previewDate = new Date(preview.date);
    const previewAmount = preview.amount;
    const previewDescription = preview.description;

    for (const existing of existingTransactions) {
      const existingDate = new Date(existing.bookedAt);
      const existingAmount = Math.abs(parseFloat(existing.amount));
      const existingDescription = existing.description || "";

      // Check date match
      if (!isSameDay(previewDate, existingDate)) {
        continue;
      }

      // Check amount match
      if (!amountsEqual(previewAmount, existingAmount)) {
        continue;
      }

      // Check description similarity
      const descSimilarity = stringSimilarity(previewDescription, existingDescription);
      if (descSimilarity < similarityThreshold) {
        continue;
      }

      // Calculate overall confidence
      const reasons: string[] = [];
      reasons.push(`Same date: ${previewDate.toLocaleDateString()}`);
      reasons.push(`Same amount: ${previewAmount.toFixed(2)}`);
      reasons.push(`Description similarity: ${(descSimilarity * 100).toFixed(0)}%`);

      const confidence = descSimilarity;

      // Only add if this is a better match than any existing match
      const existingMatch = duplicates.get(preview.rowIndex);
      if (!existingMatch || confidence > existingMatch.confidence) {
        duplicates.set(preview.rowIndex, {
          previewIndex: preview.rowIndex,
          existingTransaction: existing,
          confidence,
          reasons,
        });
      }
    }
  }

  return duplicates;
}

/**
 * Mark preview transactions as duplicates based on detection results
 */
export function markDuplicates(
  previewTransactions: PreviewTransaction[],
  duplicateMatches: Map<number, DuplicateMatch>
): PreviewTransaction[] {
  return previewTransactions.map((tx) => {
    const match = duplicateMatches.get(tx.rowIndex);
    if (match) {
      return {
        ...tx,
        isDuplicate: true,
        duplicateOf: match.existingTransaction.id,
      };
    }
    return tx;
  });
}

/**
 * Simple hash function for quick pre-filtering
 * Creates a hash based on amount and date
 */
export function createTransactionHash(
  amount: number,
  date: Date
): string {
  const roundedAmount = Math.round(amount * 100);
  const dateStr = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  return `${roundedAmount}:${dateStr}`;
}
