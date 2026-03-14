"""
SQLModel table definitions for Arth's SQLite database.

Two tables:
  - PipelineRun  — audit trail of each pipeline execution
  - Transaction   — the core financial data, mirrors CanonicalTransaction
                    with DB-specific additions (id, content_hash, timestamps)

Design notes:
  - Enum fields are stored as VARCHAR (SQLite has no native enum type anyway).
    SQLModel coerces them automatically on read/write.
  - `amount` / `closing_balance` are stored as FLOAT because SQLite doesn't
    have DECIMAL.  For a personal finance app with INR values this is fine.
  - `content_hash` is a SHA-256 digest used for idempotent inserts (dedup).
  - We skip ORM-level Relationship() here because we don't need lazy-loaded
    navigation in either direction — the FK constraint is what matters, and
    queries use explicit joins or ID lookups.
"""

import datetime

from sqlmodel import Field, SQLModel


# ───────────────────────────────────────────────────────────────────────────
# PipelineRun — one row per pipeline execution
# ───────────────────────────────────────────────────────────────────────────

class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    id: int | None = Field(default=None, primary_key=True)
    source_key: str                                     # e.g. "hdfc_savings" or "all"
    llm_model: str = "auto"                             # model used, or "none"
    txn_count: int = 0                                  # total rows processed
    new_count: int = 0                                  # rows actually inserted (non-dupes)
    updated_count: int = 0                              # existing rows that had NULLs backfilled
    status: str = "running"                             # running | completed | failed
    txn_date_min: datetime.date | None = None           # earliest txn date in this run
    txn_date_max: datetime.date | None = None           # latest txn date in this run
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
    )
    completed_at: datetime.datetime | None = None
    error_message: str | None = None


# ───────────────────────────────────────────────────────────────────────────
# Transaction — the core financial data table
# ───────────────────────────────────────────────────────────────────────────

class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)

    # Dedup key: SHA-256(txn_date|raw_description|amount|account_id)
    content_hash: str = Field(unique=True, index=True)

    # Core fields (mirror CanonicalTransaction)
    txn_date: datetime.date = Field(index=True)
    account_id: str = Field(index=True)
    source_statement: str
    direction: str = Field(index=True)                  # INFLOW / OUTFLOW
    amount: float
    currency: str = "INR"

    # Classification fields (nullable — filled progressively by pipeline)
    txn_type: str | None = Field(default=None, index=True)
    channel: str | None = None
    upi_type: str | None = None
    counterparty: str | None = Field(default=None, index=True)
    counterparty_category: str | None = Field(default=None, index=True)

    # Raw / audit
    raw_description: str
    ref_number: str | None = None
    closing_balance: float | None = None
    value_date: datetime.date | None = None
    notes: str | None = None

    # DB-only metadata
    is_reviewed: bool = Field(default=True)
    pipeline_run_id: int | None = Field(default=None, foreign_key="pipeline_runs.id")
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
    )
