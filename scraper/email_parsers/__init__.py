"""
Backward-compatible shim: email parser implementations live under ``parsers.alerts``
and ``parsers.statements``. Prefer ``parsers.email_registry`` for new code.
"""

from __future__ import annotations

import warnings

from parsers.alerts.base import BaseEmailParser
from parsers.email_registry import EMAIL_PARSER_REGISTRY, build_email_parser_registry
from parsers.statements.base import BaseStatementEmailParser
from parsers.statements.base_broker import BaseBrokerStatementParser

__all__ = [
    "EMAIL_PARSER_REGISTRY",
    "BaseEmailParser",
    "BaseStatementEmailParser",
    "BaseBrokerStatementParser",
    "build_email_parser_registry",
]

warnings.warn(
    "Importing from scraper.email_parsers is deprecated; use parsers.alerts, "
    "parsers.statements, or parsers.email_registry instead.",
    DeprecationWarning,
    stacklevel=1,
)
