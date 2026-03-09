"""
Transformer: ParsedTransaction → CanonicalTransaction.

This module is **bank-agnostic**. It works on the shared ParsedTransaction
model and never touches source-specific formats.

Responsibilities:
  - Assign sequential txn_id in insertion order (T_00000001, T_00000002, …).
  - Derive direction (INFLOW / OUTFLOW) from debit / credit amounts.
  - Derive a single positive amount.
  - Set account_id, currency, source_statement from source config.
  - Carry over raw_description, ref_number, closing_balance, value_date.
  - Leave classification fields (txn_type, channel, etc.) as None
    for the classifiers to fill.
"""

from __future__ import annotations

from decimal import Decimal

from pipeline.models import CanonicalTransaction, Direction, ParsedTransaction


def transform(
    parsed_rows: list[ParsedTransaction],
    *,
    account_id: str,
    currency: str = "INR",
    source_statement: str = "",
    start_id: int = 1,
) -> list[CanonicalTransaction]:
    """Convert a list of parsed rows into canonical transactions.

    ``start_id`` lets you continue numbering from a previous batch
    (e.g. HDFC loaded first → 1..648, then ICICI → 649..).
    """
    results: list[CanonicalTransaction] = []

    for i, p in enumerate(parsed_rows, start=start_id):
        direction, amount = _derive_direction_and_amount(p)

        txn = CanonicalTransaction(
            txn_id=f"T_{i:08d}",
            txn_date=p.txn_date,
            account_id=account_id,
            source_statement=source_statement,
            direction=direction,
            amount=amount,
            currency=currency,
            raw_description=p.raw_description,
            ref_number=p.ref_number,
            closing_balance=p.closing_balance,
            value_date=p.value_date,
        )
        results.append(txn)

    return results


def _derive_direction_and_amount(
    p: ParsedTransaction,
) -> tuple[Direction, Decimal]:
    """Decide INFLOW vs OUTFLOW and extract the positive amount."""
    if p.debit_amount > 0:
        return Direction.OUTFLOW, p.debit_amount
    return Direction.INFLOW, p.credit_amount
