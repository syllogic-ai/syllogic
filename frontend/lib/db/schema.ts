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
  functionalCurrency: char("functional_currency", { length: 3 }).default("EUR"), // User's functional currency for reporting
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
    bankConnectionId: uuid("bank_connection_id").references(() => bankConnections.id, { onDelete: "set null" }),
    balanceAvailable: decimal("balance_available", { precision: 15, scale: 2 }),
    startingBalance: decimal("starting_balance", { precision: 15, scale: 2 }).default("0"), // Starting balance for calculation
    functionalBalance: decimal("functional_balance", { precision: 15, scale: 2 }), // Calculated balance (sum of transactions + starting_balance)
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
    functionalAmount: decimal("functional_amount", { precision: 15, scale: 2 }), // Amount converted to user's functional currency
    description: text("description"),
    merchant: varchar("merchant", { length: 255 }),
    categoryId: uuid("category_id").references(() => categories.id), // User-overridden category
    categorySystemId: uuid("category_system_id").references(() => categories.id), // AI-assigned category (never updated by user)
    bookedAt: timestamp("booked_at").notNull(),
    pending: boolean("pending").default(false),
    categorizationInstructions: text("categorization_instructions"), // User instructions for AI categorization
    enrichmentData: jsonb("enrichment_data"), // Enriched merchant info, logos, etc.
    recurringTransactionId: uuid("recurring_transaction_id").references(() => recurringTransactions.id, { onDelete: "set null" }), // Link to recurring transaction label
    includeInAnalytics: boolean("include_in_analytics").default(true).notNull(), // Whether to include in analytics (charts, KPIs, etc.)
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_transactions_user").on(table.userId),
    index("idx_transactions_account").on(table.accountId),
    index("idx_transactions_booked_at").on(table.bookedAt),
    index("idx_transactions_category").on(table.categoryId),
    index("idx_transactions_category_system").on(table.categorySystemId),
    index("idx_transactions_recurring").on(table.recurringTransactionId),
    unique("transactions_account_external_id").on(table.accountId, table.externalId),
  ]
);

export const recurringTransactions = pgTable(
  "recurring_transactions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    merchant: varchar("merchant", { length: 255 }),
    amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
    currency: char("currency", { length: 3 }).default("EUR"),
    categoryId: uuid("category_id").references(() => categories.id),
    importance: integer("importance").notNull().default(3), // 1-5 scale
    frequency: varchar("frequency", { length: 20 }).notNull(), // monthly, weekly, yearly, quarterly, biweekly
    isActive: boolean("is_active").default(true),
    description: text("description"),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_recurring_transactions_user").on(table.userId),
    index("idx_recurring_transactions_category").on(table.categoryId),
    index("idx_recurring_transactions_active").on(table.isActive),
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
  provider: varchar("provider", { length: 50 }), // gocardless, ponto, etc.
  syncStatus: varchar("sync_status", { length: 50 }), // syncing, synced, failed
  lastSyncedAt: timestamp("last_synced_at"),
  errorMessage: text("error_message"),
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

export const properties = pgTable(
  "properties",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    propertyType: varchar("property_type", { length: 50 }).notNull(), // residential, commercial, land, other
    address: text("address"),
    currentValue: decimal("current_value", { precision: 15, scale: 2 }).default("0"),
    currency: char("currency", { length: 3 }).default("EUR"),
    isActive: boolean("is_active").default(true),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [index("idx_properties_user").on(table.userId)]
);

export const vehicles = pgTable(
  "vehicles",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    vehicleType: varchar("vehicle_type", { length: 50 }).notNull(), // car, motorcycle, boat, rv, other
    make: varchar("make", { length: 100 }),
    model: varchar("model", { length: 100 }),
    year: integer("year"),
    currentValue: decimal("current_value", { precision: 15, scale: 2 }).default("0"),
    currency: char("currency", { length: 3 }).default("EUR"),
    isActive: boolean("is_active").default(true),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [index("idx_vehicles_user").on(table.userId)]
);

export const exchangeRates = pgTable(
  "exchange_rates",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    date: timestamp("date").notNull(), // Date of the exchange rate
    baseCurrency: char("base_currency", { length: 3 }).notNull(), // Source currency (transaction currency)
    targetCurrency: char("target_currency", { length: 3 }).notNull(), // Target currency (EUR or USD)
    rate: decimal("rate", { precision: 18, scale: 8 }).notNull(), // Exchange rate (how many target currency = 1 base currency)
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_exchange_rates_date").on(table.date),
    index("idx_exchange_rates_base").on(table.baseCurrency),
    index("idx_exchange_rates_target").on(table.targetCurrency),
    unique("exchange_rates_date_base_target").on(
      table.date,
      table.baseCurrency,
      table.targetCurrency
    ),
  ]
);

export const subscriptionSuggestions = pgTable(
  "subscription_suggestions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),

    // Suggestion details
    suggestedName: varchar("suggested_name", { length: 255 }).notNull(),
    suggestedMerchant: varchar("suggested_merchant", { length: 255 }),
    suggestedAmount: decimal("suggested_amount", { precision: 15, scale: 2 }).notNull(),
    currency: char("currency", { length: 3 }).default("EUR").notNull(),
    detectedFrequency: varchar("detected_frequency", { length: 20 }).notNull(), // weekly, biweekly, monthly, quarterly, yearly
    confidence: integer("confidence").notNull(), // 0-100

    // Linked transactions (stored as JSON array of IDs)
    matchedTransactionIds: text("matched_transaction_ids").notNull(), // JSON array

    // Status
    status: varchar("status", { length: 20 }).default("pending").notNull(), // pending, approved, dismissed

    // Timestamps
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => [
    index("idx_subscription_suggestions_user").on(table.userId),
    index("idx_subscription_suggestions_status").on(table.status),
  ]
);

export const accountBalances = pgTable(
  "account_balances",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    accountId: uuid("account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    date: timestamp("date").notNull(), // Date of the balance snapshot
    balanceInAccountCurrency: decimal("balance_in_account_currency", { precision: 15, scale: 2 }).notNull(), // Balance in account's currency
    balanceInFunctionalCurrency: decimal("balance_in_functional_currency", { precision: 15, scale: 2 }).notNull(), // Balance converted to functional currency
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_account_balances_account").on(table.accountId),
    index("idx_account_balances_date").on(table.date),
    unique("account_balances_account_date").on(table.accountId, table.date),
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
  properties: many(properties),
  vehicles: many(vehicles),
  subscriptionSuggestions: many(subscriptionSuggestions),
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
  balances: many(accountBalances),
}));

export const accountBalancesRelations = relations(accountBalances, ({ one }) => ({
  account: one(accounts, {
    fields: [accountBalances.accountId],
    references: [accounts.id],
  }),
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
  recurringTransaction: one(recurringTransactions, {
    fields: [transactions.recurringTransactionId],
    references: [recurringTransactions.id],
    relationName: "recurringTransactionLink",
  }),
}));

export const recurringTransactionsRelations = relations(recurringTransactions, ({ one, many }) => ({
  user: one(users, {
    fields: [recurringTransactions.userId],
    references: [users.id],
  }),
  category: one(categories, {
    fields: [recurringTransactions.categoryId],
    references: [categories.id],
  }),
  linkedTransactions: many(transactions),
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

export const propertiesRelations = relations(properties, ({ one }) => ({
  user: one(users, {
    fields: [properties.userId],
    references: [users.id],
  }),
}));

export const vehiclesRelations = relations(vehicles, ({ one }) => ({
  user: one(users, {
    fields: [vehicles.userId],
    references: [users.id],
  }),
}));

export const exchangeRatesRelations = relations(exchangeRates, () => ({}));

export const subscriptionSuggestionsRelations = relations(subscriptionSuggestions, ({ one }) => ({
  user: one(users, {
    fields: [subscriptionSuggestions.userId],
    references: [users.id],
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

export type RecurringTransaction = typeof recurringTransactions.$inferSelect;
export type NewRecurringTransaction = typeof recurringTransactions.$inferInsert;

export type CategorizationRule = typeof categorizationRules.$inferSelect;
export type NewCategorizationRule = typeof categorizationRules.$inferInsert;

export type BankConnection = typeof bankConnections.$inferSelect;
export type NewBankConnection = typeof bankConnections.$inferInsert;

export type CsvImport = typeof csvImports.$inferSelect;
export type NewCsvImport = typeof csvImports.$inferInsert;

export type Property = typeof properties.$inferSelect;
export type NewProperty = typeof properties.$inferInsert;

export type Vehicle = typeof vehicles.$inferSelect;
export type NewVehicle = typeof vehicles.$inferInsert;

export type ExchangeRate = typeof exchangeRates.$inferSelect;
export type NewExchangeRate = typeof exchangeRates.$inferInsert;

export type AccountBalance = typeof accountBalances.$inferSelect;
export type NewAccountBalance = typeof accountBalances.$inferInsert;

export type SubscriptionSuggestion = typeof subscriptionSuggestions.$inferSelect;
export type NewSubscriptionSuggestion = typeof subscriptionSuggestions.$inferInsert;
