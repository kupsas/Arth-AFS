"""
Write a list of CanonicalTransactions to a clean CSV file.

Output column order matches the canonical schema. Dates are ISO 8601.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline.models import CanonicalTransaction

# Column order in the output CSV
_COLUMNS = [
    "txn_id",
    "txn_date",
    "account_id",
    "direction",
    "amount",
    "currency",
    "txn_type",
    "channel",
    "upi_type",
    "counterparty",
    "counterparty_category",
    "raw_description",
    "ref_number",
    "closing_balance",
    "value_date",
    "source_statement",
    "notes",
]


def write_csv(
    txns: list[CanonicalTransaction],
    output_path: str | Path,
) -> Path:
    """Write transactions to CSV and return the output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()

        for txn in txns:
            row = {
                "txn_id": txn.txn_id,
                "txn_date": txn.txn_date.isoformat(),
                "account_id": txn.account_id,
                "direction": txn.direction.value,
                "amount": str(txn.amount),
                "currency": txn.currency,
                "txn_type": txn.txn_type.value if txn.txn_type else "",
                "channel": txn.channel.value if txn.channel else "",
                "upi_type": txn.upi_type.value if txn.upi_type else "",
                "counterparty": txn.counterparty or "",
                "counterparty_category": (
                    txn.counterparty_category.value
                    if txn.counterparty_category
                    else ""
                ),
                "raw_description": txn.raw_description,
                "ref_number": txn.ref_number or "",
                "closing_balance": str(txn.closing_balance) if txn.closing_balance else "",
                "value_date": txn.value_date.isoformat() if txn.value_date else "",
                "source_statement": txn.source_statement,
                "notes": txn.notes or "",
            }
            writer.writerow(row)

    return output_path
