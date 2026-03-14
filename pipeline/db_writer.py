"""
Write pipeline output (list[CanonicalTransaction]) to the SQLite database.

Core responsibilities:
  1. Compute a content_hash for each transaction (SHA-256 of the "natural key")
  2. Insert new rows; for existing rows, backfill classification fields that
     are still NULL without overwriting values set by earlier runs or manual edits
  3. Track the pipeline run in the pipeline_runs table

The content_hash ensures that re-running the pipeline on the same statement
file never creates duplicates, while running on a *new* statement adds only
the new rows.  Re-running with an LLM after a rules-only pass will fill in
the fields the LLM resolved — but never clobber existing values.
"""

from __future__ import annotations

import datetime
import hashlib

from sqlmodel import Session, select

from api.models import PipelineRun, Transaction
from pipeline.models import CanonicalTransaction


def compute_content_hash(txn: CanonicalTransaction) -> str:
    """Deterministic hash from the fields that uniquely identify a transaction.

    Uses txn_date | raw_description | amount | account_id as the composite
    natural key.  Two rows with the same hash represent the same real-world
    transaction (even if classified differently across pipeline runs).
    """
    key = "|".join([
        txn.txn_date.isoformat(),
        txn.raw_description,
        str(txn.amount),
        txn.account_id,
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


_BACKFILL_FIELDS: list[tuple[str, str]] = [
    # (CanonicalTransaction attr, Transaction DB column)
    # These are the classification fields that can be incrementally enriched.
    # Core identity fields (txn_date, amount, raw_description, etc.) are never touched.
    ("txn_type",              "txn_type"),
    ("channel",               "channel"),
    ("upi_type",              "upi_type"),
    ("counterparty",          "counterparty"),
    ("counterparty_category", "counterparty_category"),
]


def _resolve_value(txn: CanonicalTransaction, attr: str) -> str | None:
    """Read a classification field from a CanonicalTransaction, converting enums to strings."""
    val = getattr(txn, attr, None)
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def write_to_db(
    txns: list[CanonicalTransaction],
    *,
    source_key: str,
    llm_model: str,
    session: Session,
) -> PipelineRun:
    """Insert new transactions and backfill NULLs on existing ones.

    Args:
        txns: Fully enriched transactions from the pipeline.
        source_key: Which source config was used (e.g. "hdfc_savings").
        llm_model: LLM model that was used (or "none").
        session: An open SQLModel Session (caller manages the engine).

    Returns:
        The PipelineRun row with final counts and status.
    """
    # Create the audit-trail row first so we can link transactions to it.
    run = PipelineRun(
        source_key=source_key,
        llm_model=llm_model,
        status="running",
    )
    session.add(run)
    session.flush()  # assigns run.id without committing

    new_count = 0
    updated_count = 0
    date_min: datetime.date | None = None
    date_max: datetime.date | None = None

    for txn in txns:
        content_hash = compute_content_hash(txn)

        existing = session.exec(
            select(Transaction).where(Transaction.content_hash == content_hash)
        ).first()

        if existing is not None:
            # Backfill: for each classification field, if the DB value is NULL
            # and the pipeline produced a value, fill it in.  Never overwrites
            # existing values (preserves manual edits and earlier enrichment).
            fields_touched = 0
            for canon_attr, db_col in _BACKFILL_FIELDS:
                if getattr(existing, db_col) is not None:
                    continue
                new_val = _resolve_value(txn, canon_attr)
                if new_val is not None:
                    setattr(existing, db_col, new_val)
                    fields_touched += 1

            if fields_touched > 0:
                existing.updated_at = datetime.datetime.now(datetime.UTC)
                session.add(existing)
                updated_count += 1
            continue

        # Brand-new row — insert it.
        db_txn = Transaction(
            content_hash=content_hash,
            txn_date=txn.txn_date,
            account_id=txn.account_id,
            source_statement=txn.source_statement,
            direction=txn.direction.value,
            amount=float(txn.amount),
            currency=txn.currency,
            txn_type=txn.txn_type.value if txn.txn_type else None,
            channel=txn.channel.value if txn.channel else None,
            upi_type=txn.upi_type.value if txn.upi_type else None,
            counterparty=txn.counterparty,
            counterparty_category=(
                txn.counterparty_category.value if txn.counterparty_category else None
            ),
            raw_description=txn.raw_description,
            ref_number=txn.ref_number,
            closing_balance=float(txn.closing_balance) if txn.closing_balance else None,
            value_date=txn.value_date,
            notes=txn.notes,
            is_reviewed=True,
            pipeline_run_id=run.id,
        )
        session.add(db_txn)
        new_count += 1

        # Track date range for coverage awareness
        if date_min is None or txn.txn_date < date_min:
            date_min = txn.txn_date
        if date_max is None or txn.txn_date > date_max:
            date_max = txn.txn_date

    # Finalise the pipeline run row
    run.txn_count = len(txns)
    run.new_count = new_count
    run.updated_count = updated_count
    run.txn_date_min = date_min
    run.txn_date_max = date_max
    run.status = "completed"
    run.completed_at = datetime.datetime.now(datetime.UTC)

    session.commit()
    session.refresh(run)
    return run
