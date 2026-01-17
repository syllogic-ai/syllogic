"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { csvImports, accounts, transactions, type NewTransaction } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { storage } from "@/lib/storage";
import { detectDuplicates, markDuplicates } from "@/lib/utils/duplicate-detection";
import OpenAI from "openai";

// Column mapping types
export interface ColumnMapping {
  date: string | null;
  amount: string | null;
  description: string | null;
  merchant: string | null;
  transactionType: string | null;
  // For transaction type, we might need additional config
  typeConfig?: {
    creditValue?: string;
    debitValue?: string;
    isAmountSigned?: boolean; // If true, positive = credit, negative = debit
  };
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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, session.user.id)
      ),
    });

    if (!importSession || !importSession.filePath) {
      return { success: false, error: "Import session not found" };
    }

    // Read the CSV file
    const fileBuffer = await storage.download(importSession.filePath);
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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
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
- date: The transaction date column
- amount: The transaction amount column
- description: The transaction description/narrative column
- merchant: The merchant/payee name column (if separate from description)
- transactionType: The column indicating debit/credit (if exists)

Also determine:
- If amount is signed (positive for credits, negative for debits)
- If there's a separate column for transaction type, what values indicate credit vs debit

Respond ONLY with a valid JSON object in this exact format:
{
  "date": "column_name_or_null",
  "amount": "column_name_or_null",
  "description": "column_name_or_null",
  "merchant": "column_name_or_null",
  "transactionType": "column_name_or_null",
  "typeConfig": {
    "creditValue": "value_that_indicates_credit_or_null",
    "debitValue": "value_that_indicates_debit_or_null",
    "isAmountSigned": true_or_false
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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
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
        and(eq(csvImports.id, importId), eq(csvImports.userId, session.user.id))
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

export async function previewImportedTransactions(
  importId: string
): Promise<{ success: boolean; error?: string; transactions?: PreviewTransaction[] }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the import session
    const importSession = await db.query.csvImports.findFirst({
      where: and(
        eq(csvImports.id, importId),
        eq(csvImports.userId, session.user.id)
      ),
    });

    if (!importSession || !importSession.filePath || !importSession.columnMapping) {
      return { success: false, error: "Import session not found or mapping incomplete" };
    }

    const mapping = importSession.columnMapping as ColumnMapping;

    // Read and parse the CSV file
    const fileBuffer = await storage.download(importSession.filePath);
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

    if (dateIndex === -1 || amountIndex === -1 || descriptionIndex === -1) {
      return { success: false, error: "Required columns not mapped" };
    }

    // Parse transactions
    const previewTransactions: PreviewTransaction[] = [];

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (!row || row.length === 0) continue;

      const dateStr = row[dateIndex];
      const amountStr = row[amountIndex];
      const description = row[descriptionIndex];
      const merchant = merchantIndex >= 0 ? row[merchantIndex] : undefined;

      // Parse date
      let parsedDate: Date;
      try {
        // Try various date formats
        const cleaned = dateStr.replace(/['"]/g, "").trim();
        parsedDate = new Date(cleaned);
        if (isNaN(parsedDate.getTime())) {
          // Try DD/MM/YYYY format
          const parts = cleaned.split(/[\/\-\.]/);
          if (parts.length === 3) {
            const [day, month, year] = parts;
            parsedDate = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
          }
        }
      } catch {
        continue; // Skip invalid rows
      }

      // Parse amount
      const cleanedAmount = amountStr.replace(/[^0-9.\-,]/g, "").replace(",", ".");
      const amount = Math.abs(parseFloat(cleanedAmount));
      if (isNaN(amount)) continue;

      // Determine transaction type
      let transactionType: "debit" | "credit" = "debit";
      if (mapping.typeConfig?.isAmountSigned) {
        transactionType = parseFloat(cleanedAmount) >= 0 ? "credit" : "debit";
      } else if (typeIndex >= 0 && mapping.typeConfig) {
        const typeValue = row[typeIndex]?.toLowerCase();
        if (mapping.typeConfig.creditValue && typeValue?.includes(mapping.typeConfig.creditValue.toLowerCase())) {
          transactionType = "credit";
        } else if (mapping.typeConfig.debitValue && typeValue?.includes(mapping.typeConfig.debitValue.toLowerCase())) {
          transactionType = "debit";
        }
      }

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
        eq(transactions.userId, session.user.id)
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

    return { success: true, transactions: markedTransactions };
  } catch (error) {
    console.error("Failed to preview transactions:", error);
    return { success: false, error: "Failed to preview transactions" };
  }
}

export async function finalizeImport(
  importId: string,
  selectedIndices: number[]
): Promise<{ success: boolean; error?: string; importedCount?: number }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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

    // Insert transactions
    const transactionsToInsert: NewTransaction[] = selectedTransactions.map((tx) => ({
      userId: session.user.id,
      accountId: importSession.accountId,
      amount: tx.amount.toString(),
      description: tx.description,
      merchant: tx.merchant,
      bookedAt: new Date(tx.date),
      transactionType: tx.transactionType,
      currency: account.currency || "EUR",
    }));

    if (transactionsToInsert.length > 0) {
      await db.insert(transactions).values(transactionsToInsert);
    }

    // Update import session
    await db
      .update(csvImports)
      .set({
        status: "completed",
        importedRows: selectedTransactions.length,
        completedAt: new Date(),
      })
      .where(eq(csvImports.id, importId));

    revalidatePath("/transactions");
    return { success: true, importedCount: selectedTransactions.length };
  } catch (error) {
    console.error("Failed to finalize import:", error);
    return { success: false, error: "Failed to import transactions" };
  }
}

export async function getCsvImportSession(
  importId: string
): Promise<CsvImportSession | null> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return null;
  }

  const importSession = await db.query.csvImports.findFirst({
    where: and(
      eq(csvImports.id, importId),
      eq(csvImports.userId, session.user.id)
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

import { categories, type NewCategory } from "@/lib/db/schema";
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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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
        balanceCurrent: "0",
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
        balanceCurrent: lastBalance,
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
