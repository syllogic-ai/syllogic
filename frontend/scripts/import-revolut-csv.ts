/**
 * Temporary script to import Revolut CSV data
 * Run with: npx tsx scripts/import-revolut-csv.ts
 * Delete after use.
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import { eq, and } from "drizzle-orm";
import * as fs from "fs/promises";
import * as dotenv from "dotenv";

// Load environment variables
dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

// Schema imports (inline to avoid module resolution issues)
import {
  pgTable,
  text,
  timestamp,
  boolean,
  uuid,
  varchar,
  char,
  decimal,
} from "drizzle-orm/pg-core";

// Define tables
const users = pgTable("users", {
  id: text("id").primaryKey(),
  name: text("name"),
  email: text("email").unique().notNull(),
});

const accounts = pgTable("accounts", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id").notNull(),
  name: varchar("name", { length: 255 }).notNull(),
  accountType: varchar("account_type", { length: 50 }).notNull(),
  institution: varchar("institution", { length: 255 }),
  currency: char("currency", { length: 3 }).default("EUR"),
  provider: varchar("provider", { length: 50 }),
  balanceCurrent: decimal("balance_current", { precision: 15, scale: 2 }).default("0"),
  lastSyncedAt: timestamp("last_synced_at"),
  updatedAt: timestamp("updated_at").defaultNow(),
});

const categories = pgTable("categories", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id").notNull(),
  name: varchar("name", { length: 255 }).notNull(),
  categoryType: varchar("category_type", { length: 20 }).default("expense"),
  color: varchar("color", { length: 7 }),
});

const transactions = pgTable("transactions", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id").notNull(),
  accountId: uuid("account_id").notNull(),
  externalId: varchar("external_id", { length: 255 }),
  transactionType: varchar("transaction_type", { length: 20 }),
  amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
  currency: char("currency", { length: 3 }).default("EUR"),
  description: text("description"),
  merchant: varchar("merchant", { length: 255 }),
  categorySystemId: uuid("category_system_id"),
  bookedAt: timestamp("booked_at").notNull(),
  pending: boolean("pending").default(false),
});

// Category definitions
const categoryDefinitions = [
  { name: "Transportation", type: "expense", color: "#3B82F6", patterns: ["OVpay", "Transport for London", "YORMA'S"] },
  { name: "Groceries", type: "expense", color: "#22C55E", patterns: ["Albert Heijn", "Jumbo", "Picnic", "SPAR", "Food & Fuel"] },
  { name: "Restaurants & Cafes", type: "expense", color: "#F97316", patterns: ["The Social Hub", "Coffee & Coconuts", "Anne&Max", "Coffeecompany", "De Keuken Van", "Bakkerij", "LOT61", "A Beautiful Mess", "Ikigai", "The Crib", "CHSD Restaurang", "bulk", "Nespresso"] },
  { name: "Shopping", type: "expense", color: "#8B5CF6", patterns: ["Amazon", "Zalando", "UNIQLO", "Skroutz", "HOBBY ART TRADE", "Gall & Gall"] },
  { name: "Subscriptions", type: "expense", color: "#EC4899", patterns: ["Apple", "Google", "PlayStation", "Premium plan fee", "Namecheap"] },
  { name: "Entertainment", type: "expense", color: "#F59E0B", patterns: ["Biercafé Doerak", "Sing A Long"] },
  { name: "Transfers", type: "transfer", color: "#6B7280", patterns: ["Transfer to Revolut user", "Transfer from Revolut user", "Transfer to ALIKI", "Transfer from ALIKI", "Tikkie", "Transfer to ILIAS", "Transfer from ILIAS", "Transfer to GEORGIA", "Transfer from GEORGIA", "Transfer to ZOI", "Transfer from ZOI", "Transfer to KONSTANTINOS", "Transfer from KONSTANTINOS", "Transfer to MENELAOS", "To EUR Pro", "Ministerie"] },
  { name: "Crypto", type: "transfer", color: "#14B8A6", patterns: ["Revolut Digital Assets"] },
  { name: "Income", type: "income", color: "#10B981", patterns: ["Apple Pay deposit", "Payment from AAB INZ TIKKIE"] },
  { name: "Travel", type: "expense", color: "#0EA5E9", patterns: ["Hotel", "Stockholm"] },
];

function categorizeTransaction(description: string): string | null {
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

function parseDate(dateStr: string): Date {
  const [datePart, timePart] = dateStr.split(" ");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute, second] = timePart.split(":").map(Number);
  return new Date(year, month - 1, day, hour, minute, second);
}

function determineTransactionType(amount: number, csvType: string): "debit" | "credit" {
  if (csvType === "Deposit" || csvType === "Refund" || csvType === "Card Refund") return "credit";
  if (csvType === "Transfer" && amount > 0) return "credit";
  return amount < 0 ? "debit" : "credit";
}

async function main() {
  const CSV_PATH = "/Users/gianniskotsas/Downloads/account-statement_2025-09-01_2026-01-17_en-us_63fb38.csv";

  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    console.error("DATABASE_URL not found in environment");
    process.exit(1);
  }

  console.log("Connecting to database...");
  const client = postgres(connectionString);
  const db = drizzle(client);

  try {
    // Get the first user (or specify a user ID)
    const [user] = await db.select().from(users).limit(1);
    if (!user) {
      console.error("No user found in database. Please sign up first.");
      process.exit(1);
    }
    console.log(`Using user: ${user.email}`);

    // Read CSV
    console.log("Reading CSV file...");
    const content = await fs.readFile(CSV_PATH, "utf-8");
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

    console.log(`Found ${dataLines.length} transactions in CSV`);

    // Create or get Revolut account
    console.log("Setting up Revolut account...");
    let [account] = await db
      .select()
      .from(accounts)
      .where(and(eq(accounts.userId, user.id), eq(accounts.name, "Revolut")))
      .limit(1);

    if (!account) {
      console.log("Creating Revolut account...");
      const [newAccount] = await db
        .insert(accounts)
        .values({
          userId: user.id,
          name: "Revolut",
          accountType: "checking",
          institution: "Revolut",
          currency: "EUR",
          provider: "manual",
          balanceCurrent: "0",
        })
        .returning();
      account = newAccount;
    }
    console.log(`Account ID: ${account.id}`);

    // Create categories
    console.log("Setting up categories...");
    const categoryMap = new Map<string, string>();
    let categoriesCreated = 0;

    for (const catDef of categoryDefinitions) {
      let [category] = await db
        .select()
        .from(categories)
        .where(and(eq(categories.userId, user.id), eq(categories.name, catDef.name)))
        .limit(1);

      if (!category) {
        const [newCategory] = await db
          .insert(categories)
          .values({
            userId: user.id,
            name: catDef.name,
            categoryType: catDef.type,
            color: catDef.color,
          })
          .returning();
        category = newCategory;
        categoriesCreated++;
      }
      categoryMap.set(catDef.name, category.id);
    }
    console.log(`Categories: ${categoryMap.size} total, ${categoriesCreated} created`);

    // Import transactions
    console.log("Importing transactions...");
    let importedCount = 0;
    let skippedCount = 0;

    for (const line of dataLines) {
      const values = line.split(",");

      const type = values[typeIdx];
      const completedDate = values[completedDateIdx];
      const description = values[descriptionIdx];
      const amount = parseFloat(values[amountIdx]);
      const fee = parseFloat(values[feeIdx]);
      const currency = values[currencyIdx];
      const state = values[stateIdx];

      if (state !== "COMPLETED") {
        skippedCount++;
        continue;
      }

      const categoryName = categorizeTransaction(description);
      const categoryId = categoryName ? categoryMap.get(categoryName) : null;
      const transactionType = determineTransactionType(amount, type);
      const totalAmount = amount - fee;
      const externalId = `revolut-${completedDate}-${description}-${amount}`;

      // Check for duplicate
      const [existing] = await db
        .select()
        .from(transactions)
        .where(and(eq(transactions.accountId, account.id), eq(transactions.externalId, externalId)))
        .limit(1);

      if (existing) {
        skippedCount++;
        continue;
      }

      await db.insert(transactions).values({
        userId: user.id,
        accountId: account.id,
        amount: totalAmount.toFixed(2),
        description: description,
        merchant: description,
        currency: currency,
        transactionType: transactionType,
        categorySystemId: categoryId,
        bookedAt: parseDate(completedDate),
        pending: false,
        externalId: externalId,
      });

      importedCount++;
      if (importedCount % 50 === 0) {
        console.log(`  Imported ${importedCount} transactions...`);
      }
    }

    // Update account balance
    const lastLine = dataLines[dataLines.length - 1];
    const lastValues = lastLine.split(",");
    const lastBalance = lastValues[balanceIdx];

    await db
      .update(accounts)
      .set({
        balanceCurrent: lastBalance,
        lastSyncedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, account.id));

    console.log("\n=== Import Complete ===");
    console.log(`Imported: ${importedCount} transactions`);
    console.log(`Skipped: ${skippedCount} (duplicates or non-completed)`);
    console.log(`Final balance: €${lastBalance}`);
    console.log("\nYou can now delete this script.");

  } catch (error) {
    console.error("Import failed:", error);
    process.exit(1);
  } finally {
    await client.end();
  }
}

main();
