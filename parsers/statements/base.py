"""
Base class for **email statement** readers — PDF attachments on bank mail (monthly /
quarterly statements), not HTML transaction alerts.

HTML alert readers subclass :class:`~parsers.alerts.base.BaseEmailParser` and implement
``parse(html, date)``. Email statement readers subclass *this* class and implement
``parse_attachment(pdf_bytes, date, email_sender=…, email_subject=…)`` instead.

The orchestrator checks ``parse_type``:
  - ``"alert"`` (default on :class:`~parsers.alerts.base.BaseEmailParser`) → HTML via
    ``get_message_body``, then ``parse``.
  - ``"statement"`` → PDFs via ``get_attachments``, then ``parse_attachment`` per file
    (results concatenated).
"""

from __future__ import annotations

import datetime
from abc import abstractmethod
from typing import ClassVar

from parsers.alerts.base import BaseEmailParser

from pipeline.models import ParsedTransaction


class BaseStatementEmailParser(BaseEmailParser):
    """Email statement reader driven by PDF attachment(s), not HTML alerts."""

    parse_type: ClassVar[str] = "statement"

    @abstractmethod
    def parse_attachment(
        self,
        pdf_bytes: bytes,
        received_date: datetime.date,
        *,
        email_sender: str = "",
        email_subject: str = "",
    ) -> list[ParsedTransaction]:
        """Parse one PDF attachment into parsed transactions.

        Implementations typically decrypt with :func:`scraper.pdf_utils.decrypt_pdf`,
        run a pipeline PDF parser, and stamp ``metadata["account_id"]`` /
        ``metadata["source_key"]``.

        Args:
            pdf_bytes: Raw bytes of a single ``.pdf`` file.
            received_date: Date Gmail received the email (for fallbacks).
            email_sender: Normalised or raw ``From`` address (password/routing for ICICI).
            email_subject: Subject line (same — e.g. monthly vs annual statement).

        Returns:
            Zero or more :class:`~pipeline.models.ParsedTransaction` rows.
        """
        ...

    def parse(
        self, html_body: str, received_date: datetime.date
    ) -> list[ParsedTransaction]:
        """Not used for statement parsers — the orchestrator calls :meth:`parse_attachment`."""
        raise NotImplementedError(
            f"{type(self).__name__} uses PDF attachments only; "
            "the orchestrator should call parse_attachment(), not parse()."
        )

    def reset_attachment_outputs(self) -> None:
        """Optional: clear per-email attachment side-channels before processing PDFs.

        The orchestrator calls this once per Gmail message when ``parse_type == "statement"``
        so parsers that :meth:`extend` PPF / investment rows across multiple attachments
        do not leak state from the previous email.
        """
        pass
