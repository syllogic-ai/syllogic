import {
  pgTable,
  text,
  timestamp,
  boolean,
  uuid,
  varchar,
  char,
  decimal,
  integer,
  jsonb,
  index,
  unique,
} from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";

// ============================================================================
// BetterAuth Tables
// ============================================================================

export const users = pgTable("users", {
  id: text("id").primaryKey(),
  name: text("name"),
  email: text("email").unique().notNull(),
  emailVerified: boolean("email_verified").default(false),
  image: text("image"),
  onboardingStatus: varchar("onboarding_status", { length: 20 }).default("pending"), // pending, step_1, step_2, step_3, completed
  onboardingCompletedAt: timestamp("onboarding_completed_at"),
  functionalCurrency: char("functional_currency", { length: 3 }).default("EUR"),
  profilePhotoPath: text("profile_photo_path"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const sessions = pgTable("sessions", {
  id: text("id").primaryKey(),
  userId: text("user_id")
    .references(() => users.id, { onDelete: "cascade" })
    .notNull(),
  token: text("token").unique().notNull(),
  expiresAt: timestamp("expires_at").notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const authAccounts = pgTable("auth_accounts", {
  id: text("id").primaryKey(),
  userId: text("user_id")
    .references(() => users.id, { onDelete: "cascade" })
    .notNull(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  accessTokenExpiresAt: timestamp("access_token_expires_at"),
  refreshTokenExpiresAt: timestamp("refresh_token_expires_at"),
  scope: text("scope"),
  idToken: text("id_token"),
  password: text("password"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const verificationTokens = pgTable("verification_tokens", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  token: text("token").unique().notNull(),
  expiresAt: timestamp("expires_at").notNull(),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

// ============================================================================
// Application Tables
// ============================================================================

export const accounts = pgTable(
  "accounts",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    accountType: varchar("account_type", { length: 50 }).notNull(), // checking, savings, credit
    institution: varchar("institution", { length: 255 }),
    currency: char("currency", { length: 3 }).default("EUR"),
    provider: varchar("provider", { length: 50 }), // gocardless, manual
    externalId: varchar("external_id", { length: 255 }), // Provider's account ID
    balanceCurrent: decimal("balance_current", { precision: 15, scale: 2 }).default("0"),
    balanceAvailable: decimal("balance_available", { precision: 15, scale: 2 }),
    isActive: boolean("is_active").default(true),
    lastSyncedAt: timestamp("last_synced_at"),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_accounts_user").on(table.userId),
    unique("accounts_user_provider_external_id").on(
      table.userId,
      table.provider,
      table.externalId
    ),
  ]
);

export const categories = pgTable(
  "categories",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    parentId: uuid("parent_id"),
    categoryType: varchar("category_type", { length: 20 }).default("expense"), // expense, income, transfer
    color: varchar("color", { length: 7 }), // Hex color
    icon: varchar("icon", { length: 50 }), // Remix icon name
    description: text("description"),
    categorizationInstructions: text("categorization_instructions"),
    isSystem: boolean("is_system").default(false),
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_categories_user").on(table.userId),
    unique("categories_user_name_parent").on(table.userId, table.name, table.parentId),
  ]
);

export const transactions = pgTable(
  "transactions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    accountId: uuid("account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    externalId: varchar("external_id", { length: 255 }),
    transactionType: varchar("transaction_type", { length: 20 }), // debit, credit
    amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
    currency: char("currency", { length: 3 }).default("EUR"),
    description: text("description"),
    merchant: varchar("merchant", { length: 255 }),
    categoryId: uuid("category_id").references(() => categories.id), // User-overridden category
    categorySystemId: uuid("category_system_id").references(() => categories.id), // AI-assigned category (never updated by user)
    bookedAt: timestamp("booked_at").notNull(),
    pending: boolean("pending").default(false),
    categorizationInstructions: text("categorization_instructions"), // User instructions for AI categorization
    enrichmentData: jsonb("enrichment_data"), // Enriched merchant info, logos, etc.
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_transactions_user").on(table.userId),
    index("idx_transactions_account").on(table.accountId),
    index("idx_transactions_booked_at").on(table.bookedAt),
    index("idx_transactions_category").on(table.categoryId),
    index("idx_transactions_category_system").on(table.categorySystemId),
    unique("transactions_account_external_id").on(table.accountId, table.externalId),
  ]
);

export const categorizationRules = pgTable("categorization_rules", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id")
    .references(() => users.id, { onDelete: "cascade" })
    .notNull(),
  categoryId: uuid("category_id")
    .references(() => categories.id, { onDelete: "cascade" })
    .notNull(),
  instructions: text("instructions"), // User-provided instructions for AI categorization
  isActive: boolean("is_active").default(true),
  createdAt: timestamp("created_at").defaultNow(),
});

export const bankConnections = pgTable("bank_connections", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: text("user_id")
    .references(() => users.id, { onDelete: "cascade" })
    .notNull(),
  institutionId: varchar("institution_id", { length: 255 }).notNull(),
  institutionName: varchar("institution_name", { length: 255 }),
  requisitionId: varchar("requisition_id", { length: 255 }).unique(),
  status: varchar("status", { length: 50 }), // pending, linked, expired, revoked
  agreementId: varchar("agreement_id", { length: 255 }),
  link: text("link"), // Authorization link
  createdAt: timestamp("created_at").defaultNow(),
  expiresAt: timestamp("expires_at"),
});

export const csvImports = pgTable(
  "csv_imports",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    accountId: uuid("account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    fileName: varchar("file_name", { length: 255 }).notNull(),
    filePath: text("file_path"),
    status: varchar("status", { length: 20 }).default("pending"), // pending, mapping, previewing, importing, completed, failed
    columnMapping: jsonb("column_mapping"),
    totalRows: integer("total_rows"),
    importedRows: integer("imported_rows"),
    duplicatesFound: integer("duplicates_found"),
    errorMessage: text("error_message"),
    createdAt: timestamp("created_at").defaultNow(),
    completedAt: timestamp("completed_at"),
  },
  (table) => [
    index("idx_csv_imports_user").on(table.userId),
    index("idx_csv_imports_account").on(table.accountId),
  ]
);

// ============================================================================
// Relations
// ============================================================================

export const usersRelations = relations(users, ({ many }) => ({
  sessions: many(sessions),
  authAccounts: many(authAccounts),
  accounts: many(accounts),
  categories: many(categories),
  transactions: many(transactions),
  categorizationRules: many(categorizationRules),
  bankConnections: many(bankConnections),
  csvImports: many(csvImports),
}));

export const sessionsRelations = relations(sessions, ({ one }) => ({
  user: one(users, {
    fields: [sessions.userId],
    references: [users.id],
  }),
}));

export const authAccountsRelations = relations(authAccounts, ({ one }) => ({
  user: one(users, {
    fields: [authAccounts.userId],
    references: [users.id],
  }),
}));

export const accountsRelations = relations(accounts, ({ one, many }) => ({
  user: one(users, {
    fields: [accounts.userId],
    references: [users.id],
  }),
  transactions: many(transactions),
  csvImports: many(csvImports),
}));

export const categoriesRelations = relations(categories, ({ one, many }) => ({
  user: one(users, {
    fields: [categories.userId],
    references: [users.id],
  }),
  parent: one(categories, {
    fields: [categories.parentId],
    references: [categories.id],
    relationName: "categoryHierarchy",
  }),
  children: many(categories, { relationName: "categoryHierarchy" }),
  transactions: many(transactions),
  categorizationRules: many(categorizationRules),
}));

export const transactionsRelations = relations(transactions, ({ one }) => ({
  user: one(users, {
    fields: [transactions.userId],
    references: [users.id],
  }),
  account: one(accounts, {
    fields: [transactions.accountId],
    references: [accounts.id],
  }),
  category: one(categories, {
    fields: [transactions.categoryId],
    references: [categories.id],
    relationName: "transactionCategory",
  }),
  categorySystem: one(categories, {
    fields: [transactions.categorySystemId],
    references: [categories.id],
    relationName: "transactionCategorySystem",
  }),
}));

export const categorizationRulesRelations = relations(categorizationRules, ({ one }) => ({
  user: one(users, {
    fields: [categorizationRules.userId],
    references: [users.id],
  }),
  category: one(categories, {
    fields: [categorizationRules.categoryId],
    references: [categories.id],
  }),
}));

export const bankConnectionsRelations = relations(bankConnections, ({ one }) => ({
  user: one(users, {
    fields: [bankConnections.userId],
    references: [users.id],
  }),
}));

export const csvImportsRelations = relations(csvImports, ({ one }) => ({
  user: one(users, {
    fields: [csvImports.userId],
    references: [users.id],
  }),
  account: one(accounts, {
    fields: [csvImports.accountId],
    references: [accounts.id],
  }),
}));

// ============================================================================
// Type Exports
// ============================================================================

export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;

export type Session = typeof sessions.$inferSelect;
export type NewSession = typeof sessions.$inferInsert;

export type Account = typeof accounts.$inferSelect;
export type NewAccount = typeof accounts.$inferInsert;

export type Category = typeof categories.$inferSelect;
export type NewCategory = typeof categories.$inferInsert;

export type Transaction = typeof transactions.$inferSelect;
export type NewTransaction = typeof transactions.$inferInsert;

export type CategorizationRule = typeof categorizationRules.$inferSelect;
export type NewCategorizationRule = typeof categorizationRules.$inferInsert;

export type BankConnection = typeof bankConnections.$inferSelect;
export type NewBankConnection = typeof bankConnections.$inferInsert;

export type CsvImport = typeof csvImports.$inferSelect;
export type NewCsvImport = typeof csvImports.$inferInsert;
