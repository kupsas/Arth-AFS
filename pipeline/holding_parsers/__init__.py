"""Backward-compatible shim: holding parsers live under ``parsers.holdings``."""

from __future__ import annotations

import warnings

from parsers.holdings import (
    HOLDING_PARSER_REGISTRY,
    BaseHoldingParser,
    ParsedHolding,
    ParsedInvestmentTxn,
    ParsedLiability,
    parse_bike_loan_txt,
    parse_term_insurance_pdf,
)

__all__ = [
    "BaseHoldingParser",
    "HOLDING_PARSER_REGISTRY",
    "ParsedHolding",
    "ParsedInvestmentTxn",
    "ParsedLiability",
    "parse_bike_loan_txt",
    "parse_term_insurance_pdf",
]

warnings.warn(
    "Importing from pipeline.holding_parsers is deprecated; use parsers.holdings instead.",
    DeprecationWarning,
    stacklevel=1,
)
