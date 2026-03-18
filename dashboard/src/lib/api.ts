/**
 * api.ts — typed HTTP client for the Arth FastAPI backend.
 *
 * Architecture:
 *   - Two low-level helpers: get<T>() and patch<T>()
 *   - Typed functions on top that map to specific backend endpoints
 *   - All functions are async and return typed Promises
 *
 * The React Query hooks in src/hooks/ call these functions.
 * Components never call fetch() directly — they always go through a hook.
 *
 * Base URL is read from NEXT_PUBLIC_API_URL env var (falls back to localhost:8000).
 * In production you'd set this to your actual API domain.
 */

import type {
  AccountSummary,
  BulkUpdateRequest,
  BulkUpdateResponse,
  CategoryBreakdown,
  DateRange,
  Direction,
  MetricsSummary,
  MonthlyTrend,
  PaginatedResponse,
  TopCounterparty,
  Transaction,
  TransactionFilters,
  TransactionUpdate,
} from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─────────────────────────────────────────────────────────────────────────────
// Error type
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Thrown by get() and patch() when the server returns a non-2xx status.
 * You can catch this in React Query's onError handlers and inspect .status.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Core fetch helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A record type that only allows values that can appear in a URL query string.
 * undefined and null values are automatically filtered out before building the URL.
 */
type QueryParams = Record<string, string | number | boolean | undefined | null>;

/**
 * Performs a GET request, appends query params, and deserialises the JSON body.
 * Throws ApiError on non-2xx responses.
 */
async function get<T>(path: string, params?: QueryParams): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      // Skip undefined/null — those mean "don't filter by this param"
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const res = await fetch(url.toString(), {
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    // Try to extract a human-readable error message from the response body
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

/**
 * Performs a PATCH request with a JSON body and deserialises the response.
 * Throws ApiError on non-2xx responses.
 */
async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Transaction endpoints  →  /api/transactions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /api/transactions
 * Fetches a paginated, filtered list of transactions.
 * Accepts any combination of filters from TransactionFilters.
 */
export function fetchTransactions(
  filters: TransactionFilters = {},
): Promise<PaginatedResponse<Transaction>> {
  return get<PaginatedResponse<Transaction>>(
    "/api/transactions",
    filters as QueryParams,
  );
}

/**
 * GET /api/transactions/:id
 * Fetches a single transaction by its database ID.
 */
export function fetchTransaction(id: number): Promise<Transaction> {
  return get<Transaction>(`/api/transactions/${id}`);
}

/**
 * PATCH /api/transactions/:id
 * Updates user-editable fields on a single transaction.
 * Only send the fields you want to change — the rest are left untouched.
 */
export function updateTransaction(
  id: number,
  update: TransactionUpdate,
): Promise<Transaction> {
  return patch<Transaction>(`/api/transactions/${id}`, update);
}

/**
 * PATCH /api/transactions/bulk
 * Applies the same update to multiple transactions in one request.
 * Useful for "mark all selected as reviewed".
 */
export function bulkUpdateTransactions(
  request: BulkUpdateRequest,
): Promise<BulkUpdateResponse> {
  return patch<BulkUpdateResponse>("/api/transactions/bulk", request);
}

// ─────────────────────────────────────────────────────────────────────────────
// Metrics endpoints  →  /api/metrics  (added in Phase 3b)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /api/metrics/summary
 * Returns high-level financial totals for a date range.
 * Defaults to the current month if no date range is provided.
 */
export function fetchMetricsSummary(
  dateRange: DateRange = {},
): Promise<MetricsSummary> {
  return get<MetricsSummary>("/api/metrics/summary", dateRange as QueryParams);
}

/**
 * GET /api/metrics/by-category
 * Returns expense (or income) broken down by counterparty_category,
 * sorted by amount descending.
 *
 * @param dateRange  optional date_from / date_to
 * @param direction  "OUTFLOW" (default) or "INFLOW"
 */
export function fetchCategoryBreakdown(
  dateRange: DateRange = {},
  direction: Direction = "OUTFLOW",
): Promise<CategoryBreakdown[]> {
  return get<CategoryBreakdown[]>("/api/metrics/by-category", {
    ...dateRange,
    direction,
  } as QueryParams);
}

/**
 * GET /api/metrics/top-counterparties
 * Returns the top N merchants / payees by total spend.
 *
 * @param dateRange  optional date_from / date_to
 * @param limit      how many to return (default 10)
 */
export function fetchTopCounterparties(
  dateRange: DateRange = {},
  limit = 10,
): Promise<TopCounterparty[]> {
  return get<TopCounterparty[]>("/api/metrics/top-counterparties", {
    ...dateRange,
    limit,
  } as QueryParams);
}

/**
 * GET /api/metrics/monthly-trend
 * Returns month-by-month income / expense / net / savings_rate
 * for the trailing N months.
 *
 * @param months  how many months of history to return (default 12)
 */
export function fetchMonthlyTrend(months = 12): Promise<MonthlyTrend[]> {
  return get<MonthlyTrend[]>("/api/metrics/monthly-trend", {
    months,
  } as QueryParams);
}

/**
 * GET /api/metrics/accounts-summary
 * Returns one row per bank account with totals.
 * No date range filter — always returns lifetime aggregates.
 */
export function fetchAccountsSummary(): Promise<AccountSummary[]> {
  return get<AccountSummary[]>("/api/metrics/accounts-summary");
}
