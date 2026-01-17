/**
 * Temporary script to fix transaction types based on amount sign
 * Run with: npx tsx scripts/fix-transaction-types.ts
 * Delete after use.
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import { eq } from "drizzle-orm";
import * as dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

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

const transactions = pgTable("transactions", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id").notNull(),
  accountId: uuid("account_id").notNull(),
  transactionType: varchar("transaction_type", { length: 20 }),
  amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
  description: text("description"),
});

async function main() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    console.error("DATABASE_URL not found");
    process.exit(1);
  }

  console.log("Connecting to database...");
  const client = postgres(connectionString);
  const db = drizzle(client);

  try {
    // Get all transactions
    const allTransactions = await db.select().from(transactions);
    console.log(`Found ${allTransactions.length} transactions`);

    // Check current state
    let creditCount = 0;
    let debitCount = 0;
    let wrongCount = 0;

    for (const tx of allTransactions) {
      const amount = parseFloat(tx.amount);
      const shouldBeCredit = amount > 0;
      const isCredit = tx.transactionType === "credit";

      if (shouldBeCredit) creditCount++;
      else debitCount++;

      if (shouldBeCredit !== isCredit) wrongCount++;
    }

    console.log(`\nCurrent state:`);
    console.log(`  Positive amounts (should be credit): ${creditCount}`);
    console.log(`  Negative amounts (should be debit): ${debitCount}`);
    console.log(`  Incorrect transaction types: ${wrongCount}`);

    if (wrongCount === 0) {
      console.log("\nAll transaction types are correct!");
      await client.end();
      return;
    }

    // Fix transaction types
    console.log(`\nFixing ${wrongCount} transactions...`);
    let fixedCount = 0;

    for (const tx of allTransactions) {
      const amount = parseFloat(tx.amount);
      const correctType = amount > 0 ? "credit" : "debit";

      if (tx.transactionType !== correctType) {
        await db
          .update(transactions)
          .set({ transactionType: correctType })
          .where(eq(transactions.id, tx.id));
        fixedCount++;
      }
    }

    console.log(`Fixed ${fixedCount} transactions`);
    console.log("\nDone! You can delete this script.");

  } catch (error) {
    console.error("Error:", error);
    process.exit(1);
  } finally {
    await client.end();
  }
}

main();
