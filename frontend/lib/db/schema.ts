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
  numeric,
  date,
  uniqueIndex,
  primaryKey,
} from "drizzle-orm/pg-core";
import { relations, sql } from "drizzle-orm";

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
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at").notNull(),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

// ============================================================================
// BetterAuth OAuth Provider Plugin Tables (@better-auth/oauth-provider)
// ============================================================================
// Field (JS) names must match the plugin's schema field names exactly so that
// better-auth's drizzleAdapter can resolve them. Column names are snake_case.

export const oauthClient = pgTable("oauth_client", {
  id: text("id").primaryKey(),
  clientId: text("client_id").unique().notNull(),
  clientSecret: text("client_secret"),
  disabled: boolean("disabled").default(false),
  skipConsent: boolean("skip_consent"),
  enableEndSession: boolean("enable_end_session"),
  subjectType: text("subject_type"),
  scopes: text("scopes").array(),
  userId: text("user_id").references(() => users.id, { onDelete: "cascade" }),
  createdAt: timestamp("created_at"),
  updatedAt: timestamp("updated_at"),
  name: text("name"),
  uri: text("uri"),
  icon: text("icon"),
  contacts: text("contacts").array(),
  tos: text("tos"),
  policy: text("policy"),
  softwareId: text("software_id"),
  softwareVersion: text("software_version"),
  softwareStatement: text("software_statement"),
  redirectUris: text("redirect_uris").array().notNull(),
  postLogoutRedirectUris: text("post_logout_redirect_uris").array(),
  tokenEndpointAuthMethod: text("token_endpoint_auth_method"),
  grantTypes: text("grant_types").array(),
  responseTypes: text("response_types").array(),
  public: boolean("public"),
  type: text("type"),
  requirePKCE: boolean("require_pkce"),
  referenceId: text("reference_id"),
  metadata: jsonb("metadata"),
});

export const oauthAccessToken = pgTable("oauth_access_token", {
  id: text("id").primaryKey(),
  token: text("token").unique(),
  clientId: text("client_id")
    .references(() => oauthClient.clientId, { onDelete: "cascade" })
    .notNull(),
  sessionId: text("session_id").references(() => sessions.id, {
    onDelete: "set null",
  }),
  userId: text("user_id").references(() => users.id, { onDelete: "cascade" }),
  referenceId: text("reference_id"),
  refreshId: text("refresh_id"),
  expiresAt: timestamp("expires_at"),
  createdAt: timestamp("created_at"),
  scopes: text("scopes").array().notNull(),
});

export const oauthRefreshToken = pgTable("oauth_refresh_token", {
  id: text("id").primaryKey(),
  token: text("token").notNull(),
  clientId: text("client_id")
    .references(() => oauthClient.clientId, { onDelete: "cascade" })
    .notNull(),
  sessionId: text("session_id").references(() => sessions.id, {
    onDelete: "set null",
  }),
  userId: text("user_id")
    .references(() => users.id, { onDelete: "cascade" })
    .notNull(),
  referenceId: text("reference_id"),
  expiresAt: timestamp("expires_at"),
  createdAt: timestamp("created_at"),
  revoked: timestamp("revoked"),
  authTime: timestamp("auth_time"),
  scopes: text("scopes").array().notNull(),
});

export const oauthConsent = pgTable("oauth_consent", {
  id: text("id").primaryKey(),
  clientId: text("client_id")
    .references(() => oauthClient.clientId, { onDelete: "cascade" })
    .notNull(),
  userId: text("user_id").references(() => users.id, { onDelete: "cascade" }),
  referenceId: text("reference_id"),
  scopes: text("scopes").array().notNull(),
  createdAt: timestamp("created_at"),
  updatedAt: timestamp("updated_at"),
});

export const jwks = pgTable("jwks", {
  id: text("id").primaryKey(),
  publicKey: text("public_key").notNull(),
  privateKey: text("private_key").notNull(),
  createdAt: timestamp("created_at").notNull(),
  expiresAt: timestamp("expires_at"),
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
    logoId: uuid("logo_id").references(() => companyLogos.id, { onDelete: "set null" }),
    currency: char("currency", { length: 3 }).default("EUR"),
    provider: varchar("provider", { length: 50 }), // ponto, gocardless, manual
    externalId: varchar("external_id", { length: 255 }), // Provider's account ID
    externalIdCiphertext: text("external_id_ciphertext"),
    externalIdHash: varchar("external_id_hash", { length: 64 }),
    ibanCiphertext: text("iban_ciphertext"),
    ibanHash: varchar("iban_hash", { length: 64 }),
    bankConnectionId: uuid("bank_connection_id").references(() => bankConnections.id, { onDelete: "set null" }),
    balanceAvailable: decimal("balance_available", { precision: 15, scale: 2 }),
    startingBalance: decimal("starting_balance", { precision: 15, scale: 2 }).default("0"), // Starting balance for calculation
    functionalBalance: decimal("functional_balance", { precision: 15, scale: 2 }), // Calculated balance (sum of transactions + starting_balance)
    balanceIsAnchored: boolean("balance_is_anchored").default(false), // True when startingBalance is derived from known bank data (CSV with verified opening/closing balance)
    isActive: boolean("is_active").default(true),
    aliasPatterns: jsonb("alias_patterns").$type<string[]>().default([]).notNull(),
    lastSyncedAt: timestamp("last_synced_at"),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_accounts_user").on(table.userId),
    index("idx_accounts_bank_connection").on(table.bankConnectionId),
    unique("accounts_user_provider_external_id").on(
      table.userId,
      table.provider,
      table.externalId
    ),
    unique("accounts_user_provider_external_id_hash").on(
      table.userId,
      table.provider,
      table.externalIdHash
    ),
    index("idx_accounts_user_iban_hash").on(table.userId, table.ibanHash),
    // Prevent two concurrent create-pocket requests from racing and inserting
    // duplicate manual IBANs. Partial index scoped to provider='manual' so a
    // pocket and a synced-bank account can still share an IBAN.
    uniqueIndex("accounts_user_iban_hash_manual_uq")
      .on(table.userId, table.ibanHash)
      .where(sql`${table.provider} = 'manual' AND ${table.ibanHash} IS NOT NULL`),
  ]
);

export const bankConnections = pgTable(
  "bank_connections",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    provider: varchar("provider", { length: 50 }).notNull().default("enable_banking"),
    sessionId: varchar("session_id", { length: 255 }).notNull(),
    aspspName: varchar("aspsp_name", { length: 255 }).notNull(),
    aspspCountry: char("aspsp_country", { length: 2 }).notNull(),
    consentExpiresAt: timestamp("consent_expires_at"),
    consentNotifiedAt: timestamp("consent_notified_at"),
    status: varchar("status", { length: 20 }).notNull().default("active"),
    lastSyncedAt: timestamp("last_synced_at"),
    syncStartedAt: timestamp("sync_started_at"),
    lastSyncError: text("last_sync_error"),
    syncCursor: jsonb("sync_cursor"),
    rawSessionData: jsonb("raw_session_data"),
    initialSyncDays: integer("initial_sync_days").notNull().default(90),
    createdAt: timestamp("created_at").defaultNow(),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (table) => [
    index("idx_bank_connections_user").on(table.userId),
    index("idx_bank_connections_status").on(table.status),
    index("idx_bank_connections_consent_expires").on(table.consentExpiresAt),
    unique("bank_connections_user_session").on(table.userId, table.sessionId),
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
    filePathCiphertext: text("file_path_ciphertext"),
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
    creditor: varchar("creditor", { length: 255 }), // Counterparty name for debits (payee)
    debtor: varchar("debtor", { length: 255 }), // Counterparty name for credits (payer)
    counterpartyIbanCiphertext: text("counterparty_iban_ciphertext"),
    counterpartyIbanHash: varchar("counterparty_iban_hash", { length: 64 }),
    internalTransferId: uuid("internal_transfer_id"), // FK to internal_transfers.id (enforced at DB level in migration 0017)
    categoryId: uuid("category_id").references(() => categories.id), // User-overridden category
    categorySystemId: uuid("category_system_id").references(() => categories.id), // AI-assigned category (never updated by user)
    bookedAt: timestamp("booked_at").notNull(),
    pending: boolean("pending").default(false),
    categorizationInstructions: text("categorization_instructions"), // User instructions for AI categorization
    enrichmentData: jsonb("enrichment_data"), // Enriched merchant info, logos, etc.
    recurringTransactionId: uuid("recurring_transaction_id").references(() => recurringTransactions.id, { onDelete: "set null" }), // Link to recurring transaction label
    includeInAnalytics: boolean("include_in_analytics").default(true).notNull(), // Whether to include in analytics (charts, KPIs, etc.)
    csvImportId: uuid("csv_import_id").references(() => csvImports.id, { onDelete: "set null" }), // Source CSV import (null for manual/bank-synced transactions)
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
    index("idx_transactions_csv_import").on(table.csvImportId),
    unique("transactions_account_external_id").on(table.accountId, table.externalId),
    index("idx_transactions_user_counterparty_iban").on(table.userId, table.counterpartyIbanHash),
  ]
);

export const internalTransfers = pgTable(
  "internal_transfers",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    sourceTxnId: uuid("source_txn_id")
      .references(() => transactions.id, { onDelete: "cascade" })
      .notNull()
      .unique(),
    mirrorTxnId: uuid("mirror_txn_id")
      .references(() => transactions.id, { onDelete: "set null" })
      .unique(),
    sourceAccountId: uuid("source_account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    pocketAccountId: uuid("pocket_account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
    currency: char("currency", { length: 3 }).notNull(),
    detectedAt: timestamp("detected_at").defaultNow(),
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_internal_transfers_user").on(table.userId),
    index("idx_internal_transfers_pocket").on(table.pocketAccountId),
  ]
);

export const recurringTransactions = pgTable(
  "recurring_transactions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    accountId: uuid("account_id").references(() => accounts.id, { onDelete: "set null" }),
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
    index("idx_recurring_transactions_account").on(table.accountId),
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
    accountId: uuid("account_id").references(() => accounts.id, { onDelete: "set null" }),
    suggestedCategoryId: uuid("suggested_category_id").references(() => categories.id, { onDelete: "set null" }),

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
    index("idx_subscription_suggestions_account").on(table.accountId),
    index("idx_subscription_suggestions_category").on(table.suggestedCategoryId),
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

export const brokerConnections = pgTable("broker_connections", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  provider: text("provider").notNull(),
  credentialsEncrypted: text("credentials_encrypted").notNull(),
  lastSyncAt: timestamp("last_sync_at"),
  lastSyncStatus: text("last_sync_status").default("pending"),
  lastSyncError: text("last_sync_error"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const holdings = pgTable("holdings", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  name: text("name"),
  currency: text("currency").notNull(),
  instrumentType: text("instrument_type").notNull(),
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  avgCost: numeric("avg_cost", { precision: 28, scale: 8 }),
  asOfDate: date("as_of_date"),
  source: text("source").notNull(),
  lastPriceError: text("last_price_error"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
}, (t) => ({
  uniqHolding: uniqueIndex("holdings_account_symbol_type_uq").on(t.accountId, t.symbol, t.instrumentType),
  byAccount: index("idx_holdings_account").on(t.accountId),
}));

export const brokerTrades = pgTable("broker_trades", {
  id: uuid("id").primaryKey().defaultRandom(),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  tradeDate: date("trade_date").notNull(),
  side: text("side").notNull(),
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  price: numeric("price", { precision: 28, scale: 8 }).notNull(),
  currency: text("currency").notNull(),
  externalId: text("external_id").notNull(),
}, (t) => ({
  uniqTrade: uniqueIndex("broker_trades_account_external_uq").on(t.accountId, t.externalId),
}));

export const priceSnapshots = pgTable("price_snapshots", {
  id: uuid("id").primaryKey().defaultRandom(),
  symbol: text("symbol").notNull(),
  currency: text("currency").notNull(),
  date: date("date").notNull(),
  close: numeric("close", { precision: 28, scale: 8 }).notNull(),
  provider: text("provider").notNull(),
}, (t) => ({
  uniqSnap: uniqueIndex("price_snapshots_symbol_date_uq").on(t.symbol, t.date),
}));

export const holdingValuations = pgTable("holding_valuations", {
  id: uuid("id").primaryKey().defaultRandom(),
  holdingId: uuid("holding_id").notNull().references(() => holdings.id, { onDelete: "cascade" }),
  date: date("date").notNull(),
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  price: numeric("price", { precision: 28, scale: 8 }).notNull(),
  valueUserCurrency: numeric("value_user_currency", { precision: 15, scale: 2 }).notNull(),
  isStale: boolean("is_stale").default(false),
}, (t) => ({
  uniqVal: uniqueIndex("holding_valuations_holding_date_uq").on(t.holdingId, t.date),
}));

// ============================================================================
// People & Household Ownership
// ============================================================================

export const people = pgTable(
  "people",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    // 'self' = auto-created person representing the operator (one per user)
    // 'member' = anyone else in the household
    kind: varchar("kind", { length: 20 }).notNull().default("member"),
    color: varchar("color", { length: 7 }),
    // Storage path inside the configured storage provider (e.g. "people/<id>.jpg").
    // null = no avatar; UI falls back to a colored initial badge.
    avatarPath: text("avatar_path"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (t) => [
    index("idx_people_user").on(t.userId),
    uniqueIndex("people_user_self_uq")
      .on(t.userId)
      .where(sql`${t.kind} = 'self'`),
  ]
);

export const accountOwners = pgTable(
  "account_owners",
  {
    accountId: uuid("account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    personId: uuid("person_id")
      .references(() => people.id, { onDelete: "cascade" })
      .notNull(),
    share: decimal("share", { precision: 5, scale: 4 }),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.accountId, t.personId] }),
    index("idx_account_owners_person").on(t.personId),
  ]
);

export const propertyOwners = pgTable(
  "property_owners",
  {
    propertyId: uuid("property_id")
      .references(() => properties.id, { onDelete: "cascade" })
      .notNull(),
    personId: uuid("person_id")
      .references(() => people.id, { onDelete: "cascade" })
      .notNull(),
    share: decimal("share", { precision: 5, scale: 4 }),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.propertyId, t.personId] }),
    index("idx_property_owners_person").on(t.personId),
  ]
);

export const vehicleOwners = pgTable(
  "vehicle_owners",
  {
    vehicleId: uuid("vehicle_id")
      .references(() => vehicles.id, { onDelete: "cascade" })
      .notNull(),
    personId: uuid("person_id")
      .references(() => people.id, { onDelete: "cascade" })
      .notNull(),
    share: decimal("share", { precision: 5, scale: 4 }),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.vehicleId, t.personId] }),
    index("idx_vehicle_owners_person").on(t.personId),
  ]
);

// ============================================================================
// Routines & Digests
// ============================================================================

export const routines = pgTable(
  "routines",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id").references(() => users.id, { onDelete: "cascade" }).notNull(),
    name: varchar("name", { length: 255 }).notNull(),
    description: text("description"),
    prompt: text("prompt").notNull(),
    cron: varchar("cron", { length: 100 }).notNull(),
    timezone: varchar("timezone", { length: 64 }).notNull().default("UTC"),
    scheduleHuman: text("schedule_human").notNull(),
    recipientEmail: varchar("recipient_email", { length: 320 }).notNull(),
    model: varchar("model", { length: 100 }).notNull().default("claude-sonnet-4-6"),
    enabled: boolean("enabled").notNull().default(true),
    nextRunAt: timestamp("next_run_at"),
    lastRunAt: timestamp("last_run_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (t) => [
    index("idx_routines_user").on(t.userId),
    index("idx_routines_due").on(t.enabled, t.nextRunAt),
  ]
);

export const routineRuns = pgTable(
  "routine_runs",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    routineId: uuid("routine_id").references(() => routines.id, { onDelete: "cascade" }).notNull(),
    userId: text("user_id").references(() => users.id, { onDelete: "cascade" }).notNull(),
    status: varchar("status", { length: 20 }).notNull().default("queued"),
    promptSnapshot: text("prompt_snapshot").notNull(),
    modelSnapshot: varchar("model_snapshot", { length: 100 }).notNull(),
    output: jsonb("output"),
    transcript: jsonb("transcript"),
    emailMessageId: varchar("email_message_id", { length: 255 }),
    errorMessage: text("error_message"),
    costCents: integer("cost_cents"),
    startedAt: timestamp("started_at"),
    completedAt: timestamp("completed_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (t) => [
    index("idx_routine_runs_routine").on(t.routineId, t.createdAt),
    index("idx_routine_runs_user").on(t.userId, t.createdAt),
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
  bankConnections: many(bankConnections),
  people: many(people),
  routines: many(routines),
  routineRuns: many(routineRuns),
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
  logo: one(companyLogos, {
    fields: [accounts.logoId],
    references: [companyLogos.id],
  }),
  bankConnection: one(bankConnections, {
    fields: [accounts.bankConnectionId],
    references: [bankConnections.id],
  }),
  transactions: many(transactions),
  csvImports: many(csvImports),
  balances: many(accountBalances),
  recurringTransactions: many(recurringTransactions),
  owners: many(accountOwners),
}));

export const bankConnectionsRelations = relations(bankConnections, ({ one, many }) => ({
  user: one(users, {
    fields: [bankConnections.userId],
    references: [users.id],
  }),
  accounts: many(accounts),
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
  csvImport: one(csvImports, {
    fields: [transactions.csvImportId],
    references: [csvImports.id],
  }),
  internalTransfer: one(internalTransfers, {
    fields: [transactions.internalTransferId],
    references: [internalTransfers.id],
  }),
}));

export const internalTransfersRelations = relations(internalTransfers, ({ one }) => ({
  user: one(users, {
    fields: [internalTransfers.userId],
    references: [users.id],
  }),
  sourceTxn: one(transactions, {
    fields: [internalTransfers.sourceTxnId],
    references: [transactions.id],
    relationName: "internalTransferSource",
  }),
  mirrorTxn: one(transactions, {
    fields: [internalTransfers.mirrorTxnId],
    references: [transactions.id],
    relationName: "internalTransferMirror",
  }),
  sourceAccount: one(accounts, {
    fields: [internalTransfers.sourceAccountId],
    references: [accounts.id],
    relationName: "internalTransferSourceAccount",
  }),
  pocketAccount: one(accounts, {
    fields: [internalTransfers.pocketAccountId],
    references: [accounts.id],
    relationName: "internalTransferPocketAccount",
  }),
}));

export const recurringTransactionsRelations = relations(recurringTransactions, ({ one, many }) => ({
  user: one(users, {
    fields: [recurringTransactions.userId],
    references: [users.id],
  }),
  account: one(accounts, {
    fields: [recurringTransactions.accountId],
    references: [accounts.id],
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

export const csvImportsRelations = relations(csvImports, ({ one, many }) => ({
  user: one(users, {
    fields: [csvImports.userId],
    references: [users.id],
  }),
  account: one(accounts, {
    fields: [csvImports.accountId],
    references: [accounts.id],
  }),
  transactions: many(transactions),
}));

export const propertiesRelations = relations(properties, ({ one, many }) => ({
  user: one(users, {
    fields: [properties.userId],
    references: [users.id],
  }),
  owners: many(propertyOwners),
}));

export const vehiclesRelations = relations(vehicles, ({ one, many }) => ({
  user: one(users, {
    fields: [vehicles.userId],
    references: [users.id],
  }),
  owners: many(vehicleOwners),
}));

export const exchangeRatesRelations = relations(exchangeRates, () => ({}));

export const subscriptionSuggestionsRelations = relations(subscriptionSuggestions, ({ one }) => ({
  user: one(users, {
    fields: [subscriptionSuggestions.userId],
    references: [users.id],
  }),
  account: one(accounts, {
    fields: [subscriptionSuggestions.accountId],
    references: [accounts.id],
  }),
  suggestedCategory: one(categories, {
    fields: [subscriptionSuggestions.suggestedCategoryId],
    references: [categories.id],
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
  accounts: many(accounts),
  recurringTransactions: many(recurringTransactions),
}));

export const peopleRelations = relations(people, ({ one, many }) => ({
  user: one(users, { fields: [people.userId], references: [users.id] }),
  accountOwners: many(accountOwners),
  propertyOwners: many(propertyOwners),
  vehicleOwners: many(vehicleOwners),
}));

export const accountOwnersRelations = relations(accountOwners, ({ one }) => ({
  account: one(accounts, { fields: [accountOwners.accountId], references: [accounts.id] }),
  person: one(people, { fields: [accountOwners.personId], references: [people.id] }),
}));

export const propertyOwnersRelations = relations(propertyOwners, ({ one }) => ({
  property: one(properties, { fields: [propertyOwners.propertyId], references: [properties.id] }),
  person: one(people, { fields: [propertyOwners.personId], references: [people.id] }),
}));

export const vehicleOwnersRelations = relations(vehicleOwners, ({ one }) => ({
  vehicle: one(vehicles, { fields: [vehicleOwners.vehicleId], references: [vehicles.id] }),
  person: one(people, { fields: [vehicleOwners.personId], references: [people.id] }),
}));

export const routinesRelations = relations(routines, ({ one, many }) => ({
  user: one(users, { fields: [routines.userId], references: [users.id] }),
  runs: many(routineRuns),
}));

export const routineRunsRelations = relations(routineRuns, ({ one }) => ({
  routine: one(routines, { fields: [routineRuns.routineId], references: [routines.id] }),
  user: one(users, { fields: [routineRuns.userId], references: [users.id] }),
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

export type BankConnection = typeof bankConnections.$inferSelect;
export type NewBankConnection = typeof bankConnections.$inferInsert;

export type InternalTransfer = typeof internalTransfers.$inferSelect;
export type NewInternalTransfer = typeof internalTransfers.$inferInsert;
