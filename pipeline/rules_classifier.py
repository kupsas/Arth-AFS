"""
Deterministic rules classifier.

Fills ``channel``, ``txn_type``, and ``upi_type`` on CanonicalTransaction
using pattern-matching on the raw_description (bank narration).

Design:
  - Classify as much as possible here to minimise LLM calls and cost.
  - Rules derived from inspecting the 647-row GSheet ground truth.
  - Where the rules can't decide (e.g. UPI_EXPENSE vs UPI_TRANSFER,
    or BANK_TRANSFER vs SELF_TRANSFER), leave the field as None so
    the LLM classifier can fill it.
"""

from __future__ import annotations

import re

from pipeline.models import (
    CanonicalTransaction,
    Channel,
    Direction,
    TxnType,
    UPIType,
)

# ---------------------------------------------------------------------------
# Self-transfer indicators (user's own name / aliases)
# ---------------------------------------------------------------------------
_SELF_INDICATORS = [
    "SASHANK",
    "MEICICI",         # HDFC's alias for the user's ICICI-linked account
    "SANDOZ",          # ICICI savings alias used for recurring transfers
]

_FAMILY_NAMES = [
    "KUPPA ADI LAKSHMI",
    "KUPPA SRINIVASA MURT",
    "KUPPA VENKATA VINOD KRISHNA",
]

# Salary identifiers (employer payroll platforms)
_SALARY_INDICATORS = ["TIDEPLATFO", "PAYROLL"]

# Patterns that reliably identify HDFC CC bill payments
_CARD_PAYMENT_RE = re.compile(r"IB BILLPAY DR", re.IGNORECASE)

# Patterns for rent / standing instruction expenses
_RENT_RE = re.compile(r"STERLING.*RENT|NET BANKING SI.*RENT", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_rules(txns: list[CanonicalTransaction]) -> list[CanonicalTransaction]:
    """Apply deterministic rules to a list of canonical transactions.

    Mutates the transactions in-place (sets channel, txn_type, upi_type)
    and returns the same list for chaining convenience.
    """
    for txn in txns:
        _classify_channel(txn)
        _classify_txn_type(txn)
        _classify_upi_type(txn)
    return txns


# ---------------------------------------------------------------------------
# Channel classification  (very high confidence — narration prefixes)
# ---------------------------------------------------------------------------

def _classify_channel(txn: CanonicalTransaction) -> None:
    desc = txn.raw_description.upper()

    # UPI-LITE must be checked before generic UPI
    if desc.startswith("UPI-LITE"):
        txn.channel = Channel.UPI_LITE
    elif desc.startswith("UPI"):
        txn.channel = Channel.UPI
    elif any(kw in desc for kw in ("NEFT ", "IMPS-", "ACH ", "RDA ", "IB BILLPAY")):
        txn.channel = Channel.BANK
    # UPI reversals (REV-UPI-...)
    elif desc.startswith("REV-UPI"):
        txn.channel = Channel.UPI
    # Third-party transfers (TPT) — bank-initiated rent payments etc.
    elif "-TPT-" in desc:
        txn.channel = Channel.BANK
    # Catch-all for remaining BANK-like patterns (standing instructions,
    # interest, processing fees, etc.)
    elif any(kw in desc for kw in (
        "NET BANKING SI",
        "INTEREST PAID",
        "PROCESSING FEE",
        "SI FAIL",
    )):
        txn.channel = Channel.BANK


# ---------------------------------------------------------------------------
# Transaction type classification
# ---------------------------------------------------------------------------

def _classify_txn_type(txn: CanonicalTransaction) -> None:
    desc = txn.raw_description
    desc_upper = desc.upper()

    # --- UPI-LITE is always a self-transfer (topping up the LITE wallet) ---
    if txn.channel == Channel.UPI_LITE:
        txn.txn_type = TxnType.SELF_TRANSFER
        return

    # --- ACH debits → loan / insurance payment ---
    if desc_upper.startswith("ACH "):
        txn.txn_type = TxnType.LOAN_INSURANCE_PAYMENT
        return

    # --- Credit card bill payments ---
    if _CARD_PAYMENT_RE.search(desc):
        txn.txn_type = TxnType.CARD_PAYMENT
        return

    # --- Salary (inflow from known payroll platforms) ---
    if txn.direction == Direction.INFLOW and any(
        kw in desc_upper for kw in _SALARY_INDICATORS
    ):
        txn.txn_type = TxnType.INCOME_SALARY
        return

    # --- Interest paid by the bank ---
    if "INTEREST PAID" in desc_upper:
        txn.txn_type = TxnType.EXPENSE_OTHER
        return

    # --- Processing fees ---
    if "PROCESSING FEE" in desc_upper:
        txn.txn_type = TxnType.EXPENSE_OTHER
        return

    # --- Standing instruction failures (bank noise, not a real expense) ---
    if "SI FAIL" in desc_upper:
        txn.txn_type = TxnType.EXPENSE_OTHER
        return

    # --- Rent via standing instruction / net banking ---
    if _RENT_RE.search(desc):
        txn.txn_type = TxnType.EXPENSE_OTHER
        return

    # --- Self-transfer detection (own name / aliases in narration) ---
    # For NEFT/IMPS with own name or aliases, and for family transfers
    # that are classified as SELF_TRANSFER in the ground truth.
    if txn.channel == Channel.BANK:
        if _is_self_transfer(desc_upper):
            txn.txn_type = TxnType.SELF_TRANSFER
            return
        # Inflows from RDA (remittance) → INCOME_OTHER
        if desc_upper.startswith("RDA "):
            txn.txn_type = TxnType.INCOME_OTHER
            return

    # --- UPI with self/family indicators ---
    if txn.channel == Channel.UPI:
        if _is_self_transfer(desc_upper):
            txn.txn_type = TxnType.SELF_TRANSFER
            return
        if any(name in desc_upper for name in _FAMILY_NAMES):
            txn.txn_type = TxnType.SELF_TRANSFER
            return
        # UPI distinction between EXPENSE and TRANSFER is hard with rules
        # alone (requires knowing if counterparty is a merchant or person).
        # Leave as None for the LLM to handle.


def _is_self_transfer(desc_upper: str) -> bool:
    """Check if narration indicates a transfer between own accounts."""
    return any(indicator in desc_upper for indicator in _SELF_INDICATORS)


# ---------------------------------------------------------------------------
# UPI type classification
# ---------------------------------------------------------------------------

def _classify_upi_type(txn: CanonicalTransaction) -> None:
    if txn.channel == Channel.UPI_LITE:
        txn.upi_type = UPIType.LITE_SELF_FUND
    elif txn.channel == Channel.UPI:
        # Can't distinguish P2P vs P2M from rules alone without a merchant
        # database. Leave as None for the LLM to handle.
        pass
    elif txn.channel in (Channel.BANK, Channel.CARD, Channel.BROKER):
        txn.upi_type = UPIType.NA
