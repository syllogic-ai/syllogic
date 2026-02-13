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
  // Required by BetterAuth admin plugin.
  role: text("role").default("user"),
  banned: boolean("banned").default(false),
  banReason: text("ban_reason"),
  banExpires: timestamp("ban_expires"),
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
  // Required by BetterAuth admin plugin (impersonation).
  impersonatedBy: text("impersonated_by"),
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

export const apiKeys = pgTable(
  "api_keys",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    keyHash: varchar("key_hash", { length: 64 }).notNull(),
    keyPrefix: varchar("key_prefix", { length: 12 }).notNull(),
    lastUsedAt: timestamp("last_used_at"),
    expiresAt: timestamp("expires_at"),
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_api_keys_user").on(table.userId),
    index("idx_api_keys_hash").on(table.keyHash),
  ]
);

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
    provider: varchar("provider", { length: 50 }), // ponto, gocardless, manual
    externalId: varchar("external_id", { length: 255 }), // Provider's account ID
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
    hideFromSelection: boolean("hide_from_selection").default(false),
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_categories_user").on(table.userId),
    index("idx_categories_user_type").on(table.userId, table.categoryType),
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
    // Composite indexes for common query patterns
    index("idx_transactions_user_category_system").on(table.userId, table.categorySystemId),
    index("idx_transactions_user_type_date").on(table.userId, table.transactionType, table.bookedAt),
    index("idx_transactions_merchant").on(table.merchant),
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
    logoId: uuid("logo_id").references(() => companyLogos.id, { onDelete: "set null" }),
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
    // Background worker fields
    celeryTaskId: varchar("celery_task_id", { length: 255 }),
    progressCount: integer("progress_count").default(0),
    selectedIndices: jsonb("selected_indices"), // Array of row indices selected for import
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
    // Composite index for efficient "latest balance" lookups
    index("idx_account_balances_account_date_desc").on(table.accountId, table.date),
    unique("account_balances_account_date").on(table.accountId, table.date),
  ]
);

export const transactionLinks = pgTable(
  "transaction_links",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    groupId: uuid("group_id").notNull(), // Groups linked transactions together
    transactionId: uuid("transaction_id")
      .references(() => transactions.id, { onDelete: "cascade" })
      .notNull(),
    linkRole: varchar("link_role", { length: 20 }).notNull(), // "primary" | "reimbursement" | "expense"
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_transaction_links_user").on(table.userId),
    index("idx_transaction_links_group").on(table.groupId),
    unique("transaction_links_transaction_unique").on(table.transactionId),
  ]
);

export const companyLogos = pgTable(
  "company_logos",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    domain: varchar("domain", { length: 255 }), // "netflix.com"
    companyName: varchar("company_name", { length: 255 }), // "Netflix"
    logoUrl: text("logo_url"), // Local path: "/uploads/logos/netflix.png"
    status: varchar("status", { length: 20 }).default("found").notNull(), // "found" | "not_found"
    lastCheckedAt: timestamp("last_checked_at").defaultNow(),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_company_logos_domain").on(table.domain),
    index("idx_company_logos_name").on(table.companyName),
    unique("company_logos_domain_unique").on(table.domain),
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
  csvImports: many(csvImports),
  properties: many(properties),
  vehicles: many(vehicles),
  subscriptionSuggestions: many(subscriptionSuggestions),
  apiKeys: many(apiKeys),
  transactionLinks: many(transactionLinks),
}));

export const apiKeysRelations = relations(apiKeys, ({ one }) => ({
  user: one(users, {
    fields: [apiKeys.userId],
    references: [users.id],
  }),
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
  transactionLink: one(transactionLinks, {
    fields: [transactions.id],
    references: [transactionLinks.transactionId],
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
  logo: one(companyLogos, {
    fields: [recurringTransactions.logoId],
    references: [companyLogos.id],
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

export const transactionLinksRelations = relations(transactionLinks, ({ one }) => ({
  user: one(users, {
    fields: [transactionLinks.userId],
    references: [users.id],
  }),
  transaction: one(transactions, {
    fields: [transactionLinks.transactionId],
    references: [transactions.id],
  }),
}));

export const companyLogosRelations = relations(companyLogos, ({ many }) => ({
  recurringTransactions: many(recurringTransactions),
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

export type ApiKey = typeof apiKeys.$inferSelect;
export type NewApiKey = typeof apiKeys.$inferInsert;

export type TransactionLink = typeof transactionLinks.$inferSelect;
export type NewTransactionLink = typeof transactionLinks.$inferInsert;

export type CompanyLogo = typeof companyLogos.$inferSelect;
export type NewCompanyLogo = typeof companyLogos.$inferInsert;
