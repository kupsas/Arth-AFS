"""
Abstract base class that every statement parser must inherit.

The contract is simple:
  1. Implement ``parse(file_path)`` → returns a list of ParsedTransaction.
  2. Set ``source_id`` to a unique string (used for config lookup, logging, etc.)

Everything downstream (transformer, classifiers, writer) works on
ParsedTransaction and never needs to know which parser produced the data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pipeline.models import ParsedTransaction


class BaseParser(ABC):
    """Plug-in point for new statement formats.

    To add support for a new bank/card:
      1. Create a new file in ``pipeline/parsers/``.
      2. Subclass ``BaseParser`` and implement ``parse()`` + ``source_id``.
      3. Register it in ``pipeline/parsers/__init__.py:PARSER_REGISTRY``.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Short identifier like 'hdfc_savings', 'icici_savings', etc."""
        ...

    @abstractmethod
    def parse(self, file_path: str | Path) -> list[ParsedTransaction]:
        """Read *file_path* and return one ParsedTransaction per row.

        All source-specific logic (date formats, delimiters, whitespace,
        section skipping, multi-line joining) lives here.
        """
        ...
