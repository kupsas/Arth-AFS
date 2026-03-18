"""
SQLModel table definitions for Arth's SQLite database.

Three tables:
  - PipelineRun    — audit trail of each pipeline execution
  - Transaction    — the core financial data, mirrors CanonicalTransaction
                     with DB-specific additions (id, content_hash, timestamps,
                     source_type, gmail_message_id)
  - ProcessedEmail — dedup ledger for the Gmail scraper; one row per Gmail
                     message ID so the same email is never processed twice

Design notes:
  - Enum fields are stored as VARCHAR (SQLite has no native enum type anyway).
    SQLModel coerces them automatically on read/write.
  - `amount` / `closing_balance` are stored as FLOAT because SQLite doesn't
    have DECIMAL.  For a personal finance app with INR values this is fine.
  - `content_hash` is a SHA-256 digest used for idempotent inserts (dedup).
  - We skip ORM-level Relationship() here because we don't need lazy-loaded
    navigation in either direction — the FK constraint is what matters, and
    queries use explicit joins or ID lookups.
  - `source_type` on Transaction drives reconciliation logic:
      "statement"  — inserted by the file-based pipeline (default)
      "email"      — inserted by the Gmail scraper (is_reviewed=False)
      "reconciled" — was email-sourced, then upgraded when the matching
                     statement line arrived
"""

import datetime

from sqlalchemy import Index
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

    # Composite index used by the reconciliation query in db_writer.py.
    # When a statement row arrives, we look for an unreconciled email row
    # with (account_id, amount, txn_date ± 1 day, source_type='email').
    # This index makes that scan fast even with thousands of transactions.
    __table_args__ = (
        Index(
            "ix_txn_reconciliation",
            "account_id", "amount", "txn_date", "source_type",
        ),
    )

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

    # ── Email scraper additions ──────────────────────────────────────────
    # Where did this transaction come from?
    #   "statement"  — default, inserted by the file-based pipeline
    #   "email"      — inserted by the Gmail scraper (is_reviewed=False)
    #   "reconciled" — email row upgraded when matching statement arrived
    source_type: str = Field(default="statement", index=True)

    # Foreign key back to ProcessedEmail.gmail_message_id.
    # NULL for statement-sourced rows; set for email + reconciled rows.
    gmail_message_id: str | None = Field(default=None, index=True)


# ───────────────────────────────────────────────────────────────────────────
# ProcessedEmail — dedup ledger for the Gmail scraper
# ───────────────────────────────────────────────────────────────────────────

class ProcessedEmail(SQLModel, table=True):
    """One row per Gmail message that the scraper has attempted to process.

    Purpose: prevent double-processing on server restarts.  Before fetching
    a message body, the orchestrator checks this table.  If the message ID
    is already here (any status), the email is skipped.

    Status values:
      "processed" — parsed successfully; txn_count transactions were created
      "skipped"   — no matching parser (non-transaction email), or parser
                    returned [] (e.g. E-mandate with no amount)
      "failed"    — an exception was raised during parsing or DB write
    """

    __tablename__ = "processed_emails"

    id: int | None = Field(default=None, primary_key=True)

    # The Gmail message ID (e.g. "18e4f2a3b1c9d7e5").  Unique so the same
    # email can never be inserted twice regardless of race conditions.
    gmail_message_id: str = Field(unique=True, index=True)

    sender: str                             # normalised from-address
    subject: str
    received_at: datetime.datetime          # timestamp from the email header

    txn_count: int = 0                      # how many transactions were created
    status: str = "processed"              # processed | skipped | failed
    error_message: str | None = None        # populated on status='failed'

    processed_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
    )
