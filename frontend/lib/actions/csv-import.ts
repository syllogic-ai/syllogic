"use server";

import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { csvImports, accounts, transactions, type NewTransaction } from "@/lib/db/schema";
import { getAuthenticatedSession, requireAuth } from "@/lib/auth-helpers";
import { storage } from "@/lib/storage";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { detectDuplicates, markDuplicates } from "@/lib/utils/duplicate-detection";
import { decryptWithFallback, encryptValue } from "@/lib/security/data-encryption";
import OpenAI from "openai";

// Helper function to create date at midnight UTC to avoid timezone shifts
function createUTCDate(year: number, month: number, day: number): Date {
  return new Date(Date.UTC(year, month, day, 0, 0, 0, 0));
}

function resolveImportFilePath(importSession: {
  filePath: string | null;
  filePathCiphertext: string | null;
}): string | null {
  return decryptWithFallback(importSession.filePathCiphertext, importSession.filePath);
}

// Column mapping types
export interface ColumnMapping {
  date: string | null;
  amount: string | null;
  description: string | null;
  merchant: string | null;
  transactionType: string | null;
  // Fee column - fees are deducted from balance
  fee: string | null;
  // State column - for filtering COMPLETED vs PENDING/REVERTED transactions
  state: string | null;
  // Balance fields for verification
  startingBalance: string | null;
  endingBalance: string | null;
  // For transaction type, we might need additional config
  typeConfig?: {
    creditValue?: string;
    debitValue?: string;
    isAmountSigned?: boolean; // If true, positive = credit, negative = debit
    dateFormat?: "DD-MM-YYYY" | "MM-DD-YYYY"; // Date format for ambiguous dates
    completedStateValue?: string; // Value that indicates a completed transaction (e.g., "COMPLETED")
  };
}

// Balance verification result
export interface BalanceVerification {
  hasBalanceData: boolean;
  canVerify: boolean; // true if both starting and ending balance are available
  fileStartingBalance: number | null;
  fileEndingBalance: number | null;
  calculatedEndingBalance: number | null; // startingBalance + sum(transactions)
  discrepancy: number | null;
  isVerified: boolean; // true if discrepancy < 0.01
  // Fields for starting balance recalculation
  importedTransactionSum: number | null;
  suggestedStartingBalance: number | null; // fileEndingBalance - transactionSum
}

export interface ParsedCsvData {
  headers: string[];
  rows: string[][];
  sampleRows: string[][]; // First 5 rows for preview
}

export interface CsvImportSession {
  id: string;
  accountId: string;
  fileName: string;
  status: string;
  columnMapping: ColumnMapping | null;
  totalRows: number | null;
  parsedData?: ParsedCsvData;
}

export async function initializeCsvImport(
  accountId: string,
  fileName: string,
  fileContent: string
): Promise<{ success: boolean; error?: string; importId?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the account belongs to the user
    const account = await db.query.accounts.findFirst({
      where: and(
        eq(accounts.id, accountId),
        eq(accounts.userId, session.user.id)
      ),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Save the CSV file
    const filePath = `csv-imports/${session.user.id}/${Date.now()}-${fileName}`;
    const encryptedFilePath = encryptValue(filePath);
    await storage.upload(filePath, Buffer.from(fileContent), {
      contentType: "text/csv",
    });

    // Parse CSV to count rows
    const lines = fileContent.split("\n").filter((line) => line.trim());
    const totalRows = Math.max(0, lines.length - 1); // Exclude header

    // Create import session
    const [result] = await db
      .insert(csvImports)
      .values({
        userId: session.user.id,
        accountId,
        fileName,
        filePath,
        filePathCiphertext: encryptedFilePath,
        status: "pending",
        totalRows,
      })
      .returning({ id: csvImports.id });

    return { success: true, importId: result.id };
  } catch (error) {
    console.error("Failed to initialize CSV import:", error);
    return { success: false, error: "Failed to initialize CSV import" };
  }
}

export async function parseCsvHeaders(
  importId: string
): Promise<{ success: boolean; error?: string; data?: ParsedCsvData }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, userId)
      ),
    });

    if (!importSession) {
      return { success: false, error: "Import session not found" };
    }

    const filePath = resolveImportFilePath(importSession);
    if (!filePath) {
      return { success: false, error: "Import file path is unavailable" };
    }

    // Read the CSV file
    const fileBuffer = await storage.download(filePath);
    const fileContent = fileBuffer.toString("utf-8");

    // Parse CSV
    const lines = fileContent.split("\n").filter((line) => line.trim());
    if (lines.length === 0) {
      return { success: false, error: "CSV file is empty" };
    }

    const parseCSVLine = (line: string): string[] => {
      const result: string[] = [];
      let current = "";
      let inQuotes = false;

      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
          inQuotes = !inQuotes;
        } else if ((char === "," || char === ";") && !inQuotes) {
          result.push(current.trim());
          current = "";
        } else {
          current += char;
        }
      }
      result.push(current.trim());
      return result;
    };

    const headers = parseCSVLine(lines[0]);
    const rows = lines.slice(1).map(parseCSVLine);
    const sampleRows = rows.slice(0, 5);

    return {
      success: true,
      data: {
        headers,
        rows,
        sampleRows,
      },
    };
  } catch (error) {
    console.error("Failed to parse CSV headers:", error);
    return { success: false, error: "Failed to parse CSV file" };
  }
}

export async function getAiColumnMapping(
  importId: string,
  csvHeaders: string[],
  sampleRows: string[][]
): Promise<{ success: boolean; error?: string; mapping?: ColumnMapping }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  const openaiApiKey = process.env.OPENAI_API_KEY;
  if (!openaiApiKey) {
    return { success: false, error: "OpenAI API key not configured" };
  }

  try {
    const openai = new OpenAI({ apiKey: openaiApiKey });

    // Prepare sample data for the prompt
    const sampleData = sampleRows.slice(0, 3).map((row) => {
      const obj: Record<string, string> = {};
      csvHeaders.forEach((header, index) => {
        obj[header] = row[index] || "";
      });
      return obj;
    });

    const prompt = `You are a CSV column mapping assistant. Analyze these CSV headers and sample data to map them to transaction fields.

Headers: ${JSON.stringify(csvHeaders)}

Sample data (first 3 rows):
${JSON.stringify(sampleData, null, 2)}

Map these columns to the following transaction fields:
- date: The transaction date column (prefer "Completed Date" over "Started Date" if both exist)
- amount: The transaction amount column
- description: The transaction description/narrative column
- merchant: The merchant/payee name column (if separate from description)
- transactionType: The column indicating debit/credit (if exists)
- fee: Column containing transaction fees (if exists, e.g., "fee", "fees", "charge", "commission") - these are additional charges deducted from balance
- state: Column containing transaction state/status (if exists, e.g., "state", "status") - used to filter out pending/reverted transactions
- startingBalance: Column containing opening/starting balance (if exists, e.g., "startsaldo", "opening_balance", "balance_before")
- endingBalance: Column containing closing/ending balance (if exists, e.g., "endsaldo", "closing_balance", "balance_after", "balance")

Also determine:
- If amount is signed (positive for credits, negative for debits)
- If there's a separate column for transaction type, what values indicate credit vs debit
- The date format: analyze the date column values to determine if dates are in "DD-MM-YYYY" (European) or "MM-DD-YYYY" (US) format. Look at the date values carefully - if you see dates like "13/05/2025" or "25/12/2024", these are clearly DD-MM-YYYY. If all dates have first value ≤12, try to infer from context or default to "DD-MM-YYYY".
- If there's a state column, what value indicates a completed transaction (e.g., "COMPLETED", "Completed", "settled", "posted")

Respond ONLY with a valid JSON object in this exact format:
{
  "date": "column_name_or_null",
  "amount": "column_name_or_null",
  "description": "column_name_or_null",
  "merchant": "column_name_or_null",
  "transactionType": "column_name_or_null",
  "fee": "column_name_or_null",
  "state": "column_name_or_null",
  "startingBalance": "column_name_or_null",
  "endingBalance": "column_name_or_null",
  "typeConfig": {
    "creditValue": "value_that_indicates_credit_or_null",
    "debitValue": "value_that_indicates_debit_or_null",
    "isAmountSigned": true_or_false,
    "dateFormat": "DD-MM-YYYY" or "MM-DD-YYYY",
    "completedStateValue": "value_that_indicates_completed_or_null"
  }
}

Use null for columns that don't exist or can't be determined.`;

    const response = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
      temperature: 0,
    });

    const content = response.choices[0]?.message?.content;
    if (!content) {
      return { success: false, error: "No response from AI" };
    }

    // Parse the JSON response
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return { success: false, error: "Invalid AI response format" };
    }

    const mapping = JSON.parse(jsonMatch[0]) as ColumnMapping;

    // Update the import session with the mapping
    await db
      .update(csvImports)
      .set({
        columnMapping: mapping,
        status: "mapping",
      })
      .where(eq(csvImports.id, importId));

    return { success: true, mapping };
  } catch (error) {
    console.error("Failed to get AI column mapping:", error);
    return { success: false, error: "Failed to analyze CSV columns" };
  }
}

export async function saveColumnMapping(
  importId: string,
  mapping: ColumnMapping
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    await db
      .update(csvImports)
      .set({
        columnMapping: mapping,
        status: "previewing",
      })
      .where(
        and(eq(csvImports.id, importId), eq(csvImports.userId, userId))
      );

    return { success: true };
  } catch (error) {
    console.error("Failed to save column mapping:", error);
    return { success: false, error: "Failed to save column mapping" };
  }
}

export interface PreviewTransaction {
  rowIndex: number;
  date: string;
  amount: number;
  description: string;
  merchant?: string;
  transactionType: "debit" | "credit";
  isDuplicate?: boolean;
  duplicateOf?: string;
}

// Daily balance extracted from CSV
export interface DailyBalance {
  date: string;  // ISO date string (YYYY-MM-DD)
  balance: number;
}

export async function previewImportedTransactions(
  importId: string
): Promise<{ success: boolean; error?: string; transactions?: PreviewTransaction[]; balanceVerification?: BalanceVerification; dailyBalances?: DailyBalance[] }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, userId)
      ),
    });

    if (!importSession || !importSession.columnMapping) {
      return { success: false, error: "Import session not found or mapping incomplete" };
    }

    const filePath = resolveImportFilePath(importSession);
    if (!filePath) {
      return { success: false, error: "Import file path is unavailable" };
    }

    const mapping = importSession.columnMapping as ColumnMapping;

    // Read and parse the CSV file
    const fileBuffer = await storage.download(filePath);
    const fileContent = fileBuffer.toString("utf-8");

    const parseCSVLine = (line: string): string[] => {
      const result: string[] = [];
      let current = "";
      let inQuotes = false;

      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
          inQuotes = !inQuotes;
        } else if ((char === "," || char === ";") && !inQuotes) {
          result.push(current.trim());
          current = "";
        } else {
          current += char;
        }
      }
      result.push(current.trim());
      return result;
    };

    const lines = fileContent.split("\n").filter((line) => line.trim());
    const headers = parseCSVLine(lines[0]);
    const rows = lines.slice(1).map(parseCSVLine);

    // Get column indices
    const dateIndex = mapping.date ? headers.indexOf(mapping.date) : -1;
    const amountIndex = mapping.amount ? headers.indexOf(mapping.amount) : -1;
    const descriptionIndex = mapping.description ? headers.indexOf(mapping.description) : -1;
    const merchantIndex = mapping.merchant ? headers.indexOf(mapping.merchant) : -1;
    const typeIndex = mapping.transactionType ? headers.indexOf(mapping.transactionType) : -1;
    const stateIndex = mapping.state ? headers.indexOf(mapping.state) : -1;

    if (dateIndex === -1 || amountIndex === -1 || descriptionIndex === -1) {
      return { success: false, error: "Required columns not mapped" };
    }

    // Parse transactions
    const previewTransactions: PreviewTransaction[] = [];
    const completedStateValue = mapping.typeConfig?.completedStateValue?.toLowerCase();

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (!row || row.length === 0) continue;

      // Filter by state if state column is mapped
      // Skip non-completed transactions (PENDING, REVERTED, CANCELLED, etc.)
      if (stateIndex >= 0 && completedStateValue) {
        const rowState = row[stateIndex]?.toLowerCase()?.trim();
        if (rowState !== completedStateValue) {
          continue; // Skip non-completed transactions
        }
      }

      const dateStr = row[dateIndex];
      const amountStr = row[amountIndex];
      const description = row[descriptionIndex];
      const merchant = merchantIndex >= 0 ? row[merchantIndex] : undefined;

      // Parse date with multiple format support
      let parsedDate: Date | null = null;
      try {
        const cleaned = dateStr.replace(/['"]/g, "").trim();

        // Try YYYYMMDD format (e.g., 20250130)
        if (/^\d{8}$/.test(cleaned)) {
          const year = parseInt(cleaned.substring(0, 4));
          const month = parseInt(cleaned.substring(4, 6)) - 1;
          const day = parseInt(cleaned.substring(6, 8));
          parsedDate = createUTCDate(year, month, day);
        }
        // Try YYYY-MM-DD or YYYY/MM/DD (ISO format)
        else if (/^\d{4}[\-\/]\d{2}[\-\/]\d{2}/.test(cleaned)) {
          // Parse as UTC to avoid timezone issues
          const parts = cleaned.split(/[\-\/]/);
          const year = parseInt(parts[0]);
          const month = parseInt(parts[1]) - 1;
          const day = parseInt(parts[2]);
          parsedDate = createUTCDate(year, month, day);
        }
        // Try DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY, MM-DD-YYYY, etc. (with optional time)
        else if (/^\d{1,2}[\-\/\.]\d{1,2}[\-\/\.]\d{4}/.test(cleaned)) {
          // Extract just the date part (before any time component)
          const dateMatch = cleaned.match(/^(\d{1,2})[\-\/\.](\d{1,2})[\-\/\.](\d{4})/);
          if (dateMatch) {
            const first = parseInt(dateMatch[1]);
            const second = parseInt(dateMatch[2]);
            const year = parseInt(dateMatch[3]);

            // If first > 12, it must be day (European format)
            if (first > 12) {
              parsedDate = createUTCDate(year, second - 1, first);
            } else if (second > 12) {
              // US format: MM-DD-YYYY
              parsedDate = createUTCDate(year, first - 1, second);
            } else {
              // Ambiguous - use user preference
              const dateFormat = mapping.typeConfig?.dateFormat ?? "DD-MM-YYYY";
              if (dateFormat === "MM-DD-YYYY") {
                // US format: MM-DD-YYYY
                parsedDate = createUTCDate(year, first - 1, second);
              } else {
                // European format: DD-MM-YYYY
                parsedDate = createUTCDate(year, second - 1, first);
              }
            }
          }
        }
        // Try DD-MM-YY, DD/MM/YY, DD.MM.YY, MM-DD-YY, etc. (2-digit year with optional time)
        else if (/^\d{1,2}[\-\/\.]\d{1,2}[\-\/\.]\d{2}(?:\s|$)/.test(cleaned)) {
          // Extract just the date part (before any time component)
          const dateMatch = cleaned.match(/^(\d{1,2})[\-\/\.](\d{1,2})[\-\/\.](\d{2})/);
          if (dateMatch) {
            const first = parseInt(dateMatch[1]);
            const second = parseInt(dateMatch[2]);
            let year = parseInt(dateMatch[3]);
            // Assume 20xx for years 00-50, 19xx for 51-99
            year = year <= 50 ? 2000 + year : 1900 + year;

            // Determine day and month based on format
            let day: number, month: number;

            // If first > 12, it must be day (European format)
            if (first > 12) {
              day = first;
              month = second - 1;
            } else if (second > 12) {
              // US format: MM-DD-YY
              day = second;
              month = first - 1;
            } else {
              // Ambiguous - use user preference
              const dateFormat = mapping.typeConfig?.dateFormat ?? "DD-MM-YYYY";
              if (dateFormat === "MM-DD-YYYY") {
                // US format: MM-DD-YY
                day = second;
                month = first - 1;
              } else {
                // European format: DD-MM-YY
                day = first;
                month = second - 1;
              }
            }

            parsedDate = createUTCDate(year, month, day);
          }
        }
        // Try MM/DD/YYYY or DD/MM/YYYY - use user preference for ambiguous dates
        else if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(cleaned)) {
          const parts = cleaned.split("/");
          const first = parseInt(parts[0]);
          const second = parseInt(parts[1]);
          const year = parseInt(parts[2]);

          // If first > 12, it must be day (European format)
          if (first > 12) {
            parsedDate = createUTCDate(year, second - 1, first);
          } else if (second > 12) {
            // US format: MM/DD/YYYY
            parsedDate = createUTCDate(year, first - 1, second);
          } else {
            // Ambiguous - use user preference
            const dateFormat = mapping.typeConfig?.dateFormat ?? "DD-MM-YYYY";
            if (dateFormat === "MM-DD-YYYY") {
              // US format: MM/DD/YYYY
              parsedDate = createUTCDate(year, first - 1, second);
            } else {
              // European format: DD/MM/YYYY
              parsedDate = createUTCDate(year, second - 1, first);
            }
          }
        }
        // Try month name formats: "Feb 6, 2026", "February 6, 2026", "6 Feb 2026", etc.
        else {
          const monthNames = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
          ];
          const monthAbbrevs = [
            "jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec"
          ];
          
          // Try formats like "Feb 6, 2026" or "February 6, 2026"
          const monthNameMatch = cleaned.match(/^([a-z]+)\s+(\d{1,2}),?\s+(\d{4})/i);
          if (monthNameMatch) {
            const monthStr = monthNameMatch[1].toLowerCase();
            const day = parseInt(monthNameMatch[2]);
            const year = parseInt(monthNameMatch[3]);
            
            let monthIndex = monthAbbrevs.indexOf(monthStr);
            if (monthIndex === -1) {
              monthIndex = monthNames.indexOf(monthStr);
            }
            
            if (monthIndex !== -1 && day >= 1 && day <= 31 && year >= 1900) {
              parsedDate = createUTCDate(year, monthIndex, day);
            }
          }
          
          // Try formats like "6 Feb 2026" or "6 February 2026"
          if (!parsedDate) {
            const dayMonthMatch = cleaned.match(/^(\d{1,2})\s+([a-z]+)\s+(\d{4})/i);
            if (dayMonthMatch) {
              const day = parseInt(dayMonthMatch[1]);
              const monthStr = dayMonthMatch[2].toLowerCase();
              const year = parseInt(dayMonthMatch[3]);
              
              let monthIndex = monthAbbrevs.indexOf(monthStr);
              if (monthIndex === -1) {
                monthIndex = monthNames.indexOf(monthStr);
              }
              
              if (monthIndex !== -1 && day >= 1 && day <= 31 && year >= 1900) {
                parsedDate = createUTCDate(year, monthIndex, day);
              }
            }
          }
        }
        
        // Fallback: try parsing as ISO date or use UTC
        if (!parsedDate) {
          // Try to parse as YYYY-MM-DD format first
          if (/^\d{4}[\-\/]\d{2}[\-\/]\d{2}/.test(cleaned)) {
            const parts = cleaned.split(/[\-\/]/);
            const year = parseInt(parts[0]);
            const month = parseInt(parts[1]) - 1;
            const day = parseInt(parts[2]);
            parsedDate = createUTCDate(year, month, day);
          } else {
            // Fallback to native parsing (may have timezone issues, but better than nothing)
            parsedDate = new Date(cleaned);
          }
        }

        // Validate the parsed date
        if (!parsedDate || isNaN(parsedDate.getTime())) {
          continue; // Skip invalid rows
        }
      } catch {
        continue; // Skip invalid rows
      }

      // Parse amount (preserve sign for now to determine transaction type)
      const cleanedAmount = amountStr.replace(/[^0-9.\-,]/g, "").replace(",", ".");
      const parsedAmount = parseFloat(cleanedAmount);
      if (isNaN(parsedAmount)) continue;

      // Determine transaction type BEFORE calling Math.abs()
      let transactionType: "debit" | "credit" = "debit";

      // First check if there's an explicit transaction type column
      if (typeIndex >= 0 && mapping.typeConfig) {
        const typeValue = row[typeIndex]?.toLowerCase().trim();
        if (mapping.typeConfig.creditValue && typeValue?.includes(mapping.typeConfig.creditValue.toLowerCase())) {
          transactionType = "credit";
        } else if (mapping.typeConfig.debitValue && typeValue?.includes(mapping.typeConfig.debitValue.toLowerCase())) {
          transactionType = "debit";
        } else {
          // If type column exists but value doesn't match, check for common aliases
          if (typeValue && (typeValue.includes("expense") || typeValue.includes("debit") || typeValue.includes("outgoing") || typeValue.includes("payment"))) {
            transactionType = "debit";
          } else if (typeValue && (typeValue.includes("income") || typeValue.includes("credit") || typeValue.includes("incoming") || typeValue.includes("deposit"))) {
            transactionType = "credit";
          }
        }
      }

      // If no explicit type column, infer from amount sign (if amounts are signed)
      // Note: Negative amounts = expenses (debit), Positive amounts = income (credit)
      if (typeIndex === -1 && mapping.typeConfig?.isAmountSigned) {
        transactionType = parsedAmount >= 0 ? "credit" : "debit";
      }

      // Send amount with correct sign based on transaction_type
      // Backend expects: debit = negative, credit = positive
      const amount = transactionType === "debit" ? -Math.abs(parsedAmount) : Math.abs(parsedAmount);

      previewTransactions.push({
        rowIndex: i,
        date: parsedDate.toISOString(),
        amount,
        description,
        merchant,
        transactionType,
      });
    }

    // Detect duplicates against existing transactions in the same account
    const existingTransactions = await db.query.transactions.findMany({
      where: and(
        eq(transactions.accountId, importSession.accountId),
        eq(transactions.userId, userId)
      ),
    });

    // Run duplicate detection
    const duplicateMatches = detectDuplicates(previewTransactions, existingTransactions);
    const markedTransactions = markDuplicates(previewTransactions, duplicateMatches);

    // Update import session with duplicate count
    await db
      .update(csvImports)
      .set({
        duplicatesFound: duplicateMatches.size,
      })
      .where(eq(csvImports.id, importId));

    // Balance verification logic and daily balance extraction
    let balanceVerification: BalanceVerification | undefined;
    let dailyBalances: DailyBalance[] = [];

    const startBalIdx = mapping.startingBalance ? headers.indexOf(mapping.startingBalance) : -1;
    const endBalIdx = mapping.endingBalance ? headers.indexOf(mapping.endingBalance) : -1;
    const feeIdx = mapping.fee ? headers.indexOf(mapping.fee) : -1;

    // Helper to clean and parse balance amounts
    const cleanAmount = (str: string | undefined): number | null => {
      if (!str) return null;
      const cleaned = str.replace(/[^0-9.\-,]/g, "").replace(",", ".");
      const parsed = parseFloat(cleaned);
      return isNaN(parsed) ? null : parsed;
    };

    // Calculate total fees from CSV if fee column is mapped (only from COMPLETED transactions)
    let totalFees = 0;
    if (feeIdx >= 0) {
      for (const row of rows) {
        // Only count fees from completed transactions
        if (stateIndex >= 0 && completedStateValue) {
          const rowState = row[stateIndex]?.toLowerCase()?.trim();
          if (rowState !== completedStateValue) {
            continue; // Skip fees from non-completed transactions
          }
        }
        const fee = cleanAmount(row[feeIdx]);
        if (fee !== null && fee > 0) {
          totalFees += fee;
        }
      }
      totalFees = Math.round(totalFees * 100) / 100;
    }

    if (mapping.startingBalance || mapping.endingBalance) {
      // Get first row's starting balance, last row's ending balance
      const firstRow = rows[0];
      const lastRow = rows[rows.length - 1];

      const fileStartingBalance = startBalIdx >= 0 ? cleanAmount(firstRow?.[startBalIdx]) : null;
      const fileEndingBalance = endBalIdx >= 0 ? cleanAmount(lastRow?.[endBalIdx]) : null;

      // Calculate starting balance from first row's ending balance when no explicit starting balance
      // Formula: balance_before_first_tx = first_ending_balance - first_amount
      // This works because: first_ending_balance = balance_before_first_tx + first_amount
      // Note: Fees are not included here because they affect balance differently and are
      // captured in the daily balances from the CSV which are the source of truth.
      let calculatedStartingBalance: number | null = null;
      if (fileStartingBalance === null && endBalIdx >= 0) {
        const firstRowEndingBalance = cleanAmount(firstRow?.[endBalIdx]);
        const amountIdx = mapping.amount ? headers.indexOf(mapping.amount) : -1;
        const firstRowAmount = amountIdx >= 0 ? cleanAmount(firstRow?.[amountIdx]) : null;

        if (firstRowEndingBalance !== null && firstRowAmount !== null) {
          // first_ending_balance = starting_balance + first_amount
          // starting_balance = first_ending_balance - first_amount
          calculatedStartingBalance = Math.round((firstRowEndingBalance - firstRowAmount) * 100) / 100;
        }
      }

      // Calculate sum of transactions (credits positive, debits negative)
      const transactionSum = previewTransactions.reduce((sum, tx) => {
        return sum + (tx.transactionType === "credit" ? tx.amount : -Math.abs(tx.amount));
      }, 0);

      // Use explicit starting balance if available, otherwise use calculated
      const effectiveStartingBalance = fileStartingBalance ?? calculatedStartingBalance;

      // Calculate expected ending balance
      // Subtract fees since they affect the balance but aren't in the transaction amounts
      // (e.g., Premium plan fee with Amount=0.00 but Fee=9.99 reduces balance by 9.99)
      const calculatedEndingBalance = effectiveStartingBalance !== null
        ? Math.round((effectiveStartingBalance + transactionSum - totalFees) * 100) / 100
        : null;

      const discrepancy = (fileEndingBalance !== null && calculatedEndingBalance !== null)
        ? Math.round((fileEndingBalance - calculatedEndingBalance) * 100) / 100
        : null;

      const canVerify = effectiveStartingBalance !== null && fileEndingBalance !== null;

      // Calculate suggested starting balance for recalculation
      // Formula: startingBalance = fileEndingBalance - transactionSum
      const suggestedStartingBalance = fileEndingBalance !== null
        ? Math.round((fileEndingBalance - transactionSum) * 100) / 100
        : null;

      balanceVerification = {
        hasBalanceData: fileEndingBalance !== null || effectiveStartingBalance !== null,
        canVerify,
        fileStartingBalance: effectiveStartingBalance, // Use effective (calculated if needed)
        fileEndingBalance,
        calculatedEndingBalance,
        discrepancy,
        isVerified: canVerify && discrepancy !== null && Math.abs(discrepancy) < 0.01,
        importedTransactionSum: Math.round(transactionSum * 100) / 100,
        suggestedStartingBalance,
      };

      // Extract daily balances from CSV rows
      // For each row, we extract the ending balance (or calculate from starting balance + transaction)
      // The last transaction of each day becomes the authoritative balance for that day
      const dailyBalanceMap = new Map<string, number>();
      const dateIndex = mapping.date ? headers.indexOf(mapping.date) : -1;
      const amountIndex = mapping.amount ? headers.indexOf(mapping.amount) : -1;

      if (dateIndex >= 0 && (endBalIdx >= 0 || startBalIdx >= 0)) {
        for (let i = 0; i < rows.length; i++) {
          const row = rows[i];
          if (!row || row.length === 0) continue;

          // Only extract balances from completed transactions
          if (stateIndex >= 0 && completedStateValue) {
            const rowState = row[stateIndex]?.toLowerCase()?.trim();
            if (rowState !== completedStateValue) {
              continue; // Skip non-completed transactions for balance extraction
            }
          }

          const dateStr = row[dateIndex];
          if (!dateStr) continue;

          // Parse the date to get YYYY-MM-DD format
          let parsedDate: Date | null = null;
          try {
            const cleaned = dateStr.replace(/['"]/g, "").trim();

            // Try YYYYMMDD format
            if (/^\d{8}$/.test(cleaned)) {
              const year = parseInt(cleaned.substring(0, 4));
              const month = parseInt(cleaned.substring(4, 6)) - 1;
              const day = parseInt(cleaned.substring(6, 8));
              parsedDate = createUTCDate(year, month, day);
            }
            // Try YYYY-MM-DD or YYYY/MM/DD
            else if (/^\d{4}[\-\/]\d{2}[\-\/]\d{2}/.test(cleaned)) {
              const parts = cleaned.split(/[\-\/]/);
              const year = parseInt(parts[0]);
              const month = parseInt(parts[1]) - 1;
              const day = parseInt(parts[2]);
              parsedDate = createUTCDate(year, month, day);
            }
            // Try DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
            else if (/^\d{1,2}[\-\/\.]\d{1,2}[\-\/\.]\d{4}$/.test(cleaned)) {
              const parts = cleaned.split(/[\-\/\.]/);
              const day = parseInt(parts[0]);
              const month = parseInt(parts[1]) - 1;
              const year = parseInt(parts[2]);
              parsedDate = createUTCDate(year, month, day);
            }
            // Try DD-MM-YY, DD/MM/YY, DD.MM.YY
            else if (/^\d{1,2}[\-\/\.]\d{1,2}[\-\/\.]\d{2}$/.test(cleaned)) {
              const parts = cleaned.split(/[\-\/\.]/);
              const day = parseInt(parts[0]);
              const month = parseInt(parts[1]) - 1;
              let year = parseInt(parts[2]);
              year = year <= 50 ? 2000 + year : 1900 + year;
              parsedDate = createUTCDate(year, month, day);
            }
            // Fallback
            else {
              parsedDate = new Date(cleaned);
            }

            if (!parsedDate || isNaN(parsedDate.getTime())) continue;
          } catch {
            continue;
          }

          // Format as YYYY-MM-DD
          const isoDate = parsedDate.toISOString().split("T")[0];

          // Get balance for this row
          let dayBalance: number | null = null;

          if (endBalIdx >= 0) {
            // Use ending balance directly if available
            dayBalance = cleanAmount(row[endBalIdx]);
          } else if (startBalIdx >= 0 && amountIndex >= 0) {
            // Calculate ending balance from starting balance + transaction amount
            const startBal = cleanAmount(row[startBalIdx]);
            const amountStr = row[amountIndex];
            const cleanedAmount = amountStr?.replace(/[^0-9.\-,]/g, "").replace(",", ".");
            const txAmount = cleanedAmount ? parseFloat(cleanedAmount) : null;

            if (startBal !== null && txAmount !== null) {
              // For signed amounts, just add directly. For type-based, need to check type
              if (mapping.typeConfig?.isAmountSigned) {
                dayBalance = startBal + txAmount;
              } else {
                // Need to determine if credit or debit
                const typeIndex = mapping.transactionType ? headers.indexOf(mapping.transactionType) : -1;
                let isCredit = false;
                if (typeIndex >= 0 && mapping.typeConfig) {
                  const typeValue = row[typeIndex]?.toLowerCase();
                  if (mapping.typeConfig.creditValue && typeValue?.includes(mapping.typeConfig.creditValue.toLowerCase())) {
                    isCredit = true;
                  }
                }
                dayBalance = startBal + (isCredit ? Math.abs(txAmount) : -Math.abs(txAmount));
              }
            }
          }

          if (dayBalance !== null) {
            // Store balance - last transaction of each day wins (CSV is processed in order)
            dailyBalanceMap.set(isoDate, Math.round(dayBalance * 100) / 100);
          }
        }

        // Convert map to array
        dailyBalances = Array.from(dailyBalanceMap.entries())
          .map(([date, balance]) => ({ date, balance }));
      }
    }

    return { success: true, transactions: markedTransactions, balanceVerification, dailyBalances };
  } catch (error) {
    console.error("Failed to preview transactions:", error);
    return { success: false, error: "Failed to preview transactions" };
  }
}

/**
 * Generate a deterministic external_id for CSV-imported transactions.
 * This ensures duplicate prevention by creating a unique ID based on transaction data.
 * Format: csv-import-{hash}
 * Hash based on: accountId + date + amount + description + merchant
 * Uses multiple hash functions combined for collision resistance
 */
function generateCsvImportExternalId(
  accountId: string,
  date: string,
  amount: number,
  description: string | null,
  merchant: string | null = null
): string {
  // Create a string to hash - include merchant for better uniqueness
  const dateOnly = date.split('T')[0]; // Use only the date part (YYYY-MM-DD)
  const normalizedDesc = (description || '').trim().toLowerCase();
  const normalizedMerchant = (merchant || '').trim().toLowerCase();
  const dataToHash = `${accountId}|${dateOnly}|${amount.toFixed(2)}|${normalizedDesc}|${normalizedMerchant}`;

  // FNV-1a hash (32-bit)
  let hash1 = 2166136261;
  for (let i = 0; i < dataToHash.length; i++) {
    hash1 ^= dataToHash.charCodeAt(i);
    hash1 += (hash1 << 1) + (hash1 << 4) + (hash1 << 7) + (hash1 << 8) + (hash1 << 24);
  }

  // MurmurHash-inspired second hash (32-bit)
  let hash2 = 0;
  for (let i = 0; i < dataToHash.length; i++) {
    const char = dataToHash.charCodeAt(i);
    hash2 = ((hash2 << 5) - hash2) + char;
    hash2 = hash2 & hash2; // Convert to 32bit integer
  }

  // DJB2 third hash for additional entropy
  let hash3 = 5381;
  for (let i = 0; i < dataToHash.length; i++) {
    hash3 = ((hash3 << 5) + hash3) + dataToHash.charCodeAt(i);
  }

  // Convert all to unsigned 32-bit and combine into a longer hash
  const h1 = (hash1 >>> 0).toString(36);
  const h2 = (hash2 >>> 0).toString(36);
  const h3 = (hash3 >>> 0).toString(36);

  // Combine all three hashes for maximum uniqueness (collision probability ~2^-96)
  return `csv-import-${h1}${h2}${h3}`;
}

// Backend API transaction import item (snake_case format)
interface BackendTransactionImportItem {
  account_id: string;
  amount: number;
  description: string | null;
  merchant: string | null;
  booked_at: string; // ISO datetime string
  transaction_type: "credit" | "debit";
  currency: string;
  external_id: string | null;
}

// Backend daily balance import format
interface BackendDailyBalance {
  date: string;  // ISO date string (YYYY-MM-DD)
  balance: number;
}

// Backend API request format
interface BackendTransactionImportRequest {
  transactions: BackendTransactionImportItem[];
  user_id?: string;
  sync_exchange_rates: boolean;
  update_functional_amounts: boolean;
  calculate_balances: boolean;
  daily_balances?: BackendDailyBalance[];
  starting_balance?: number;  // Starting balance from CSV to update account
}

// Backend API response format
interface BackendTransactionImportResponse {
  success: boolean;
  message: string;
  transactions_inserted: number;
  transaction_ids: string[] | null;
  categorization_summary: {
    total: number;
    categorized: number;
    deterministic: number;
    llm: number;
    uncategorized: number;
    tokens_used: number;
    cost_usd: number;
  } | null;
  exchange_rates_synced: Record<string, unknown> | null;
  functional_amounts_updated: Record<string, unknown> | null;
  balances_calculated: Record<string, unknown> | null;
}

export async function finalizeImport(
  importId: string,
  selectedIndices: number[]
): Promise<{ success: boolean; error?: string; importedCount?: number; categorizationSummary?: BackendTransactionImportResponse["categorization_summary"] }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get preview transactions
    const previewResult = await previewImportedTransactions(importId);
    if (!previewResult.success || !previewResult.transactions) {
      return { success: false, error: previewResult.error || "Failed to get preview" };
    }

    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, session.user.id)
      ),
    });

    if (!importSession) {
      return { success: false, error: "Import session not found" };
    }

    // Get account for currency
    const account = await db.query.accounts.findFirst({
      where: eq(accounts.id, importSession.accountId),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Filter to selected transactions
    const selectedTransactions = previewResult.transactions.filter((tx) =>
      selectedIndices.includes(tx.rowIndex)
    );

    if (selectedTransactions.length === 0) {
      return { success: true, importedCount: 0 };
    }

    // Transform transactions to backend format (snake_case)
    // Generate deterministic external_id for each transaction to prevent duplicates
    // Track external_ids to handle same-day duplicate transactions
    const externalIdCounts = new Map<string, number>();

    const backendTransactions: BackendTransactionImportItem[] = selectedTransactions.map((tx) => {
      const bookedAt = new Date(tx.date).toISOString();
      const baseExternalId = generateCsvImportExternalId(
        importSession.accountId,
        bookedAt,
        tx.amount,
        tx.description || null,
        tx.merchant || null
      );

      // Check if we've seen this external_id before in this batch
      const count = externalIdCounts.get(baseExternalId) || 0;
      externalIdCounts.set(baseExternalId, count + 1);

      // If this is a duplicate within the batch, append a counter
      const externalId = count === 0
        ? baseExternalId
        : `${baseExternalId}-${count + 1}`;

      return {
        account_id: importSession.accountId,
        amount: tx.amount,
        description: tx.description || null,
        merchant: tx.merchant || null,
        booked_at: bookedAt,
        transaction_type: tx.transactionType,
        currency: account.currency || "EUR",
        external_id: externalId,
      };
    });

    // Batch the transactions to avoid request timeouts and large payload issues
    // For large imports (>500 transactions), split into batches
    const BATCH_SIZE = 500;
    const backendUrl = getBackendBaseUrl();

    let totalImported = 0;
    let aggregatedCategorizationSummary: BackendTransactionImportResponse["categorization_summary"] = null;

    // Split transactions into batches
    const batches: BackendTransactionImportItem[][] = [];
    for (let i = 0; i < backendTransactions.length; i += BATCH_SIZE) {
      batches.push(backendTransactions.slice(i, i + BATCH_SIZE));
    }

    // Importing transactions in batches

    try {
      for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
        const batch = batches[batchIndex];
        const isLastBatch = batchIndex === batches.length - 1;

        // Build the backend request for this batch
        const backendRequest: BackendTransactionImportRequest = {
          transactions: batch,
          // Only sync exchange rates and calculate balances on the last batch for efficiency
          sync_exchange_rates: isLastBatch,
          update_functional_amounts: isLastBatch,
          calculate_balances: isLastBatch,
          // Only include daily balances and starting balance on the last batch
          daily_balances: isLastBatch ? (previewResult.dailyBalances || undefined) : undefined,
          starting_balance: isLastBatch ? (previewResult.balanceVerification?.fileStartingBalance ?? undefined) : undefined,
        };

        // Call backend API with 5-minute timeout per batch
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000); // 5 minutes per batch

        const pathWithQuery = "/api/transactions/import";
        const response = await fetch(`${backendUrl}${pathWithQuery}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...createInternalAuthHeaders({
              method: "POST",
              pathWithQuery,
              userId: session.user.id,
            }),
          },
          body: JSON.stringify(backendRequest),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorText = await response.text();
          console.error(`Backend import failed for batch ${batchIndex + 1}/${batches.length}:`, response.status, errorText);
          return {
            success: false,
            error: `Import failed on batch ${batchIndex + 1}/${batches.length}: ${response.status} - ${errorText}. ${totalImported} transactions were imported before the failure.`
          };
        }

        const backendResponse: BackendTransactionImportResponse = await response.json();

        if (!backendResponse.success) {
          return {
            success: false,
            error: `Batch ${batchIndex + 1}/${batches.length} failed: ${backendResponse.message}. ${totalImported} transactions were imported before the failure.`
          };
        }

        totalImported += backendResponse.transactions_inserted;

        // Aggregate categorization summary from all batches
        if (backendResponse.categorization_summary) {
          if (!aggregatedCategorizationSummary) {
            aggregatedCategorizationSummary = { ...backendResponse.categorization_summary };
          } else {
            aggregatedCategorizationSummary.total += backendResponse.categorization_summary.total;
            aggregatedCategorizationSummary.categorized += backendResponse.categorization_summary.categorized;
            aggregatedCategorizationSummary.deterministic += backendResponse.categorization_summary.deterministic;
            aggregatedCategorizationSummary.llm += backendResponse.categorization_summary.llm;
            aggregatedCategorizationSummary.uncategorized += backendResponse.categorization_summary.uncategorized;
            aggregatedCategorizationSummary.tokens_used += backendResponse.categorization_summary.tokens_used;
            aggregatedCategorizationSummary.cost_usd += backendResponse.categorization_summary.cost_usd;
          }
        }

        // Batch completed successfully
      }

      // Update import session
      await db
        .update(csvImports)
        .set({
          status: "completed",
          importedRows: totalImported,
          completedAt: new Date(),
        })
        .where(eq(csvImports.id, importId));

      // Revalidate all relevant paths to ensure UI updates
      revalidatePath("/transactions");
      revalidatePath("/");
      revalidatePath("/dashboard");
      revalidatePath("/settings");

      return {
        success: true,
        importedCount: totalImported,
        categorizationSummary: aggregatedCategorizationSummary,
      };
    } catch (fetchError) {
      if (fetchError instanceof Error && fetchError.name === "AbortError") {
        console.error("Import timeout during batch processing");
        return {
          success: false,
          error: `Import timeout: The operation took too long. ${totalImported} transactions were imported before the timeout.`
        };
      }
      throw fetchError; // Re-throw to outer catch
    }
  } catch (error) {
    console.error("Failed to finalize import:", error);
    return { success: false, error: error instanceof Error ? error.message : "Failed to import transactions" };
  }
}

// Backend enqueue response type
interface BackendEnqueueResponse {
  success: boolean;
  import_id: string;
  task_id: string | null;
  message: string;
}

/**
 * Enqueue a CSV import for background processing.
 * This allows immediate redirect while the import processes in the background.
 *
 * @param importId - The CSV import session ID
 * @param selectedIndices - Array of row indices selected for import
 * @returns Success status with import details for SSE connection
 */
export async function enqueueBackgroundImport(
  importId: string,
  selectedIndices: number[]
): Promise<{
  success: boolean;
  error?: string;
  importId?: string;
  taskId?: string;
  totalTransactions?: number;
}> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get preview transactions
    const previewResult = await previewImportedTransactions(importId);
    if (!previewResult.success || !previewResult.transactions) {
      return { success: false, error: previewResult.error || "Failed to get preview" };
    }

    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, session.user.id)
      ),
    });

    if (!importSession) {
      return { success: false, error: "Import session not found" };
    }

    // Get account for currency
    const account = await db.query.accounts.findFirst({
      where: eq(accounts.id, importSession.accountId),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Filter to selected transactions
    const selectedTransactions = previewResult.transactions.filter((tx) =>
      selectedIndices.includes(tx.rowIndex)
    );

    if (selectedTransactions.length === 0) {
      return { success: true, importId, totalTransactions: 0 };
    }

    // Transform transactions to backend format
    const externalIdCounts = new Map<string, number>();

    const transactions = selectedTransactions.map((tx) => {
      const bookedAt = new Date(tx.date).toISOString();
      const baseExternalId = generateCsvImportExternalId(
        importSession.accountId,
        bookedAt,
        tx.amount,
        tx.description || null,
        tx.merchant || null
      );

      const count = externalIdCounts.get(baseExternalId) || 0;
      externalIdCounts.set(baseExternalId, count + 1);

      const externalId = count === 0
        ? baseExternalId
        : `${baseExternalId}-${count + 1}`;

      return {
        account_id: importSession.accountId,
        amount: tx.amount,
        description: tx.description || null,
        merchant: tx.merchant || null,
        booked_at: bookedAt,
        transaction_type: tx.transactionType,
        currency: account.currency || "EUR",
        external_id: externalId,
        category_id: null,
      };
    });

    // Build enqueue request
    const backendUrl = getBackendBaseUrl();
    const enqueueRequest = {
      csv_import_id: importId,
      transactions,
      daily_balances: previewResult.dailyBalances || undefined,
      starting_balance: previewResult.balanceVerification?.fileStartingBalance ?? undefined,
    };

    // Call backend enqueue endpoint
    const pathWithQuery = "/api/csv-import/enqueue";
    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
        }),
      },
      body: JSON.stringify(enqueueRequest),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend enqueue failed:", response.status, errorText);
      return {
        success: false,
        error: `Failed to start import: ${response.status} - ${errorText}`,
      };
    }

    const backendResponse: BackendEnqueueResponse = await response.json();

    if (!backendResponse.success) {
      return {
        success: false,
        error: backendResponse.message,
      };
    }

    // Background import enqueued successfully

    return {
      success: true,
      importId: backendResponse.import_id,
      taskId: backendResponse.task_id || undefined,
      totalTransactions: transactions.length,
    };
  } catch (error) {
    console.error("Failed to enqueue background import:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "Failed to start import",
    };
  }
}

export async function getCsvImportSession(
  importId: string
): Promise<CsvImportSession | null> {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  const importSession = await db.query.csvImports.findFirst({
    where: and(
      eq(csvImports.id, importId),
      eq(csvImports.userId, userId)
    ),
  });

  if (!importSession) {
    return null;
  }

  return {
    id: importSession.id,
    accountId: importSession.accountId,
    fileName: importSession.fileName,
    status: importSession.status || "pending",
    columnMapping: importSession.columnMapping as ColumnMapping | null,
    totalRows: importSession.totalRows,
  };
}

// ============================================================================
// Direct Import with Auto-Categorization (for Revolut CSV format)
// ============================================================================

import { categories } from "@/lib/db/schema";
import * as fs from "fs/promises";

// Category definitions with matching patterns
const categoryDefinitions: {
  name: string;
  type: "expense" | "income" | "transfer";
  color: string;
  patterns: string[];
}[] = [
  {
    name: "Transportation",
    type: "expense",
    color: "#3B82F6",
    patterns: ["OVpay", "Transport for London", "YORMA'S"],
  },
  {
    name: "Groceries",
    type: "expense",
    color: "#22C55E",
    patterns: ["Albert Heijn", "Jumbo", "Picnic", "SPAR", "Food & Fuel"],
  },
  {
    name: "Restaurants & Cafes",
    type: "expense",
    color: "#F97316",
    patterns: [
      "The Social Hub", "Coffee & Coconuts", "Anne&Max", "Coffeecompany",
      "De Keuken Van", "Bakkerij", "LOT61", "A Beautiful Mess", "Ikigai",
      "The Crib", "CHSD Restaurang", "bulk", "Nespresso"
    ],
  },
  {
    name: "Shopping",
    type: "expense",
    color: "#8B5CF6",
    patterns: ["Amazon", "Zalando", "UNIQLO", "Skroutz", "HOBBY ART TRADE", "Gall & Gall"],
  },
  {
    name: "Subscriptions",
    type: "expense",
    color: "#EC4899",
    patterns: ["Apple", "Google", "PlayStation", "Premium plan fee", "Namecheap"],
  },
  {
    name: "Entertainment",
    type: "expense",
    color: "#F59E0B",
    patterns: ["Biercafé Doerak", "Sing A Long"],
  },
  {
    name: "Transfers",
    type: "transfer",
    color: "#6B7280",
    patterns: [
      "Transfer to Revolut user", "Transfer from Revolut user",
      "Transfer to ALIKI", "Transfer from ALIKI", "Tikkie",
      "Transfer to ILIAS", "Transfer from ILIAS",
      "Transfer to GEORGIA", "Transfer from GEORGIA",
      "Transfer to ZOI", "Transfer from ZOI",
      "Transfer to KONSTANTINOS", "Transfer from KONSTANTINOS",
      "Transfer to MENELAOS", "To EUR Pro", "Ministerie"
    ],
  },
  {
    name: "Crypto",
    type: "transfer",
    color: "#14B8A6",
    patterns: ["Revolut Digital Assets"],
  },
  {
    name: "Income",
    type: "income",
    color: "#10B981",
    patterns: ["Apple Pay deposit", "Payment from AAB INZ TIKKIE"],
  },
  {
    name: "Travel",
    type: "expense",
    color: "#0EA5E9",
    patterns: ["Hotel", "Stockholm"],
  },
];

function categorizeTransactionByDescription(description: string): string | null {
  const descLower = description.toLowerCase();

  for (const cat of categoryDefinitions) {
    for (const pattern of cat.patterns) {
      if (descLower.includes(pattern.toLowerCase())) {
        return cat.name;
      }
    }
  }

  return null;
}

function parseRevolutDate(dateStr: string): Date {
  // Format: "2025-09-01 20:13:31"
  const [datePart, timePart] = dateStr.split(" ");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute, second] = timePart.split(":").map(Number);
  return new Date(year, month - 1, day, hour, minute, second);
}

function determineTransactionTypeFromCsv(amount: number, csvType: string): "debit" | "credit" {
  if (csvType === "Deposit" || csvType === "Refund" || csvType === "Card Refund") {
    return "credit";
  }
  if (csvType === "Transfer" && amount > 0) {
    return "credit";
  }
  return amount < 0 ? "debit" : "credit";
}

export async function importRevolutCsv(filePath: string): Promise<{
  success: boolean;
  error?: string;
  imported?: number;
  categoriesCreated?: number;
}> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Read and parse CSV
    const content = await fs.readFile(filePath, "utf-8");
    const lines = content.trim().split("\n");
    const headerLine = lines[0];
    const dataLines = lines.slice(1);

    // Parse header
    const csvHeaders = headerLine.split(",");
    const typeIdx = csvHeaders.indexOf("Type");
    const completedDateIdx = csvHeaders.indexOf("Completed Date");
    const descriptionIdx = csvHeaders.indexOf("Description");
    const amountIdx = csvHeaders.indexOf("Amount");
    const feeIdx = csvHeaders.indexOf("Fee");
    const currencyIdx = csvHeaders.indexOf("Currency");
    const stateIdx = csvHeaders.indexOf("State");
    const balanceIdx = csvHeaders.indexOf("Balance");

    // Create or get Revolut account
    let account = await db.query.accounts.findFirst({
      where: and(
        eq(accounts.userId, session.user.id),
        eq(accounts.name, "Revolut")
      ),
    });

    if (!account) {
      const [newAccount] = await db.insert(accounts).values({
        userId: session.user.id,
        name: "Revolut",
        accountType: "checking",
        institution: "Revolut",
        currency: "EUR",
        provider: "manual",
        startingBalance: "0",
        functionalBalance: "0",
      }).returning();
      account = newAccount;
    }

    // Create categories if they don't exist
    const categoryMap = new Map<string, string>();
    let categoriesCreated = 0;

    for (const catDef of categoryDefinitions) {
      let category = await db.query.categories.findFirst({
        where: and(
          eq(categories.userId, session.user.id),
          eq(categories.name, catDef.name)
        ),
      });

      if (!category) {
        const [newCategory] = await db.insert(categories).values({
          userId: session.user.id,
          name: catDef.name,
          categoryType: catDef.type,
          color: catDef.color,
        }).returning();
        category = newCategory;
        categoriesCreated++;
      }

      categoryMap.set(catDef.name, category.id);
    }

    // Parse and import transactions
    let importedCount = 0;

    for (const line of dataLines) {
      const values = line.split(",");

      const type = values[typeIdx];
      const completedDate = values[completedDateIdx];
      const description = values[descriptionIdx];
      const amount = parseFloat(values[amountIdx]);
      const fee = parseFloat(values[feeIdx]);
      const currency = values[currencyIdx];
      const state = values[stateIdx];

      if (state !== "COMPLETED") continue;

      const categoryName = categorizeTransactionByDescription(description);
      const categoryId = categoryName ? categoryMap.get(categoryName) : null;
      const transactionType = determineTransactionTypeFromCsv(amount, type);
      const totalAmount = amount - fee;

      const newTransaction: NewTransaction = {
        userId: session.user.id,
        accountId: account.id,
        amount: totalAmount.toFixed(2),
        description: description,
        merchant: description,
        currency: currency,
        transactionType: transactionType,
        categorySystemId: categoryId,
        bookedAt: parseRevolutDate(completedDate),
        pending: false,
        externalId: `revolut-${completedDate}-${description}-${amount}`,
      };

      const existing = await db.query.transactions.findFirst({
        where: and(
          eq(transactions.accountId, account.id),
          eq(transactions.externalId, newTransaction.externalId!)
        ),
      });

      if (!existing) {
        await db.insert(transactions).values(newTransaction);
        importedCount++;
      }
    }

    // Update account balance
    const lastLine = dataLines[dataLines.length - 1];
    const lastValues = lastLine.split(",");
    const lastBalance = lastValues[balanceIdx];

    await db.update(accounts)
      .set({
        functionalBalance: lastBalance,
        lastSyncedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, account.id));

    revalidatePath("/transactions");
    revalidatePath("/");

    return {
      success: true,
      imported: importedCount,
      categoriesCreated,
    };
  } catch (error) {
    console.error("Failed to import CSV:", error);
    return { success: false, error: error instanceof Error ? error.message : "Failed to import CSV" };
  }
}
