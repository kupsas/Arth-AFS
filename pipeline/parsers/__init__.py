"""Backward-compatible shim: upload parsers live under ``parsers.uploads``."""

from __future__ import annotations

import warnings

from parsers.uploads import (
    PARSER_REGISTRY,
    BaseParser,
    HDFCCreditCardParser,
    HDFCCreditCardPdfParser,
    HDFCSavingsParser,
    HDFCSavingsPdfParser,
    ICICISavingsParser,
)

__all__ = [
    "PARSER_REGISTRY",
    "BaseParser",
    "HDFCCreditCardParser",
    "HDFCCreditCardPdfParser",
    "HDFCSavingsParser",
    "HDFCSavingsPdfParser",
    "ICICISavingsParser",
]

warnings.warn(
    "Importing from pipeline.parsers is deprecated; use parsers.uploads instead.",
    DeprecationWarning,
    stacklevel=1,
)
