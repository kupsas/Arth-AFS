/**
 * types.ts — shared TypeScript types for the Arth dashboard.
 *
 * These mirror the Python models in:
 *   - api/models.py          (Transaction SQLModel)
 *   - pipeline/models.py     (enums + CanonicalTransaction)
 *   - api/routes/transactions.py (PaginatedResponse, TransactionUpdate)
 *   - api/routes/metrics.py  (MetricsSummary, CategoryBreakdown, etc.)
 *
 * Design note: enum values are string union types (not TypeScript enums).
 * Reason: TypeScript enums compile to runtime objects and cause issues with
 * tree-shaking + exhaustive checks. String unions give us autocomplete,
 * type-safety, and zero runtime overhead.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Enum string union types  (one-to-one with Python enums in pipeline/models.py)
// ─────────────────────────────────────────────────────────────────────────────

/** Whether money is coming in or going out of the account. */
export type Direction = "INFLOW" | "OUTFLOW";

/**
 * The specific economic nature of a transaction.
 * CARD_PAYMENT = paying your CC bill → excluded from expense totals (self-transfer).
 * CARD_EXPENSE = actual purchase on CC → included in expense totals.
 */
export type TxnType =
  | "BANK_TRANSFER"
  | "CARD_EXPENSE"
  | "CARD_PAYMENT"
  | "EQUITY_PURCHASE"
  | "EQUITY_SALE"
  | "EXPENSE_OTHER"
  | "INCOME_DIVIDEND"
  | "INCOME_OTHER"
  | "INCOME_SALARY"
  | "LOAN_INSURANCE_PAYMENT"
  | "MF_PURCHASE"
  | "MF_SALE"
  | "SELF_TRANSFER"
  | "UPI_EXPENSE"
  | "UPI_TRANSFER";

/** The payment rail / channel used. */
export type Channel = "UPI" | "UPI-LITE" | "BANK" | "CARD" | "BROKER";

/** For UPI transactions: person-to-person, person-to-merchant, etc. */
export type UPIType = "P2P" | "P2M" | "LITE_SELF_FUND" | "NA";

/**
 * High-level spending category assigned by the LLM classifier.
 * These string values match the Python CounterpartyCategory enum exactly.
 */
export type CounterpartyCategory =
  | "Asset Markets"
  | "Entertainment & Events"
  | "Fees, Charges & Interest"
  | "Financial Services, Insurance & Banking"
  | "Food & Dining"
  | "Friends and Family"
  | "Gifts & Personal Transfers"
  | "Healthcare & Pharmacy"
  | "Miscellaneous"
  | "Mobile, OTT & Subscriptions"
  | "Personal Grooming"
  | "Rent & Housing"
  | "Salary & Income"
  | "Self Transfer"
  | "Shopping & E-commerce"
  | "Swiggy"
  | "Transport & Fuel"
  | "Travel & Stay"
  | "Utilities & Internet";

// ─────────────────────────────────────────────────────────────────────────────
// Core entity: Transaction
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A single financial transaction — mirrors the Transaction SQLModel in api/models.py.
 *
 * Date fields are ISO strings (e.g. "2025-03-15") because JSON has no native
 * Date type. Use `new Date(txn.txn_date)` or date-fns to parse them.
 */
export interface Transaction {
  id: number;
  content_hash: string;

  txn_date: string;           // "YYYY-MM-DD"
  account_id: string;
  source_statement: string;

  direction: Direction;
  amount: number;
  currency: string;           // "INR" for all current data

  txn_type: TxnType | null;
  channel: Channel | null;
  upi_type: UPIType | null;
  counterparty: string | null;
  counterparty_category: CounterpartyCategory | null;

  raw_description: string;
  ref_number: string | null;
  closing_balance: number | null;
  value_date: string | null;  // "YYYY-MM-DD" or null
  notes: string | null;

  is_reviewed: boolean;
  pipeline_run_id: number | null;
  created_at: string;         // ISO datetime string
  updated_at: string;         // ISO datetime string
}

/**
 * Fields the user is allowed to edit — mirrors TransactionUpdate in
 * api/routes/transactions.py.  All fields are optional (undefined = don't touch).
 */
export interface TransactionUpdate {
  counterparty?: string | null;
  counterparty_category?: CounterpartyCategory | null;
  txn_type?: TxnType | null;
  notes?: string | null;
  is_reviewed?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination wrapper
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Generic paginated response — mirrors PaginatedResponse in the backend.
 * T will usually be Transaction, but kept generic so it can wrap anything.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;        // total matching rows (across all pages)
  page: number;         // current page (1-indexed)
  page_size: number;    // rows per page
  total_pages: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Bulk update types
// ─────────────────────────────────────────────────────────────────────────────

export interface BulkUpdateRequest {
  ids: number[];
  update: TransactionUpdate;
}

export interface BulkUpdateResponse {
  updated: number[];    // IDs that were successfully updated
  not_found: number[];  // IDs that didn't exist in the DB
}

// ─────────────────────────────────────────────────────────────────────────────
// Query filter types (used by the API client and hooks)
// ─────────────────────────────────────────────────────────────────────────────

/** All available filters for GET /api/transactions */
export interface TransactionFilters {
  date_from?: string;       // "YYYY-MM-DD"
  date_to?: string;         // "YYYY-MM-DD"
  account_id?: string;
  direction?: Direction;
  category?: CounterpartyCategory | string;
  txn_type?: TxnType;
  is_reviewed?: boolean;
  search?: string;          // free-text search on counterparty + raw_description
  page?: number;            // 1-indexed, default 1
  page_size?: number;       // default 50, max 200
  sort_by?: "txn_date" | "amount" | "created_at" | "counterparty";
  sort_order?: "asc" | "desc";
}

/** Date range used for metrics endpoints */
export interface DateRange {
  date_from?: string;  // "YYYY-MM-DD"
  date_to?: string;    // "YYYY-MM-DD"
}

// ─────────────────────────────────────────────────────────────────────────────
// Metrics response types (mirrors /api/metrics/* endpoints added in Phase 3b)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /api/metrics/summary
 * High-level financial snapshot for a date range.
 *
 * Note: savings_rate is a 0–100 percentage (e.g. 42.5 = 42.5% saved),
 * NOT a 0–1 fraction. The backend computes: (income - expense) / income * 100
 */
export interface MetricsSummary {
  date_from: string;       // "YYYY-MM-DD" — echoed back from the request (or defaulted)
  date_to: string;         // "YYYY-MM-DD"
  total_income: number;
  total_expense: number;
  net: number;
  savings_rate: number;    // 0–100 percentage (e.g. 42.5 = 42.5% savings rate)
  txn_count: number;
}

/**
 * One row from GET /api/metrics/by-category
 * Sorted by amount descending.
 * category is null when transactions haven't been classified yet.
 */
export interface CategoryBreakdown {
  category: CounterpartyCategory | string | null;
  amount: number;
  percentage: number;    // 0–100 (e.g. 42.3 = 42.3% of total spend)
  txn_count: number;
}

/**
 * One row from GET /api/metrics/top-counterparties
 * Both counterparty and category may be null for unclassified transactions.
 */
export interface TopCounterparty {
  counterparty: string | null;
  category: CounterpartyCategory | string | null;
  amount: number;
  txn_count: number;
}

/**
 * One row from GET /api/metrics/monthly-trend
 * `month` is "YYYY-MM" (e.g. "2025-03").
 *
 * Note: savings_rate is a 0–100 percentage, same as MetricsSummary.
 * Zero-filled rows are returned for months with no transactions so the
 * frontend can render a smooth chart without gaps.
 */
export interface MonthlyTrend {
  month: string;
  income: number;
  expense: number;
  net: number;
  savings_rate: number;  // 0–100 percentage (e.g. 42.5 = 42.5% savings rate)
}

/**
 * One row from GET /api/metrics/accounts-summary
 */
export interface AccountSummary {
  account_id: string;
  txn_count: number;
  last_txn_date: string | null;  // "YYYY-MM-DD" or null
  total_inflow: number;
  total_outflow: number;
}

/**
 * One deficit month from GET /api/metrics/negative-surplus-months (Q11)
 * net is always negative here (expense exceeded income that month).
 */
export interface DeficitMonthRow {
  month: string;   // "YYYY-MM"
  income: number;
  expense: number;
  net: number;     // negative value
}

/**
 * GET /api/metrics/negative-surplus-months (Q11)
 * Answers: "How many of my recent months had a spending deficit?"
 *
 * total_deficit is the sum of |net| across all deficit months — a positive number
 * representing how much more was spent than earned across those bad months.
 */
export interface NegativeSurplusResponse {
  months_with_deficit: number;
  total_months: number;
  deficit_months: DeficitMonthRow[];
  total_deficit: number;  // always positive — the cumulative shortfall
}
