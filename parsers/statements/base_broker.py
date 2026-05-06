"""
Base class for **broker email statement** readers — PDFs that populate investment
side-channels (holdings / trades), not only bank cash rows.

:class:`~parsers.statements.base.BaseStatementEmailParser` is about
``parse_attachment`` → ``list[ParsedTransaction]`` (bank cash ledger). Some PDFs
instead (or in addition) produce :class:`~parsers.holdings.base.ParsedHolding`
/ :class:`~parsers.holdings.base.ParsedInvestmentTxn` rows, which the
orchestrator reads via :meth:`attachment_investment_outputs` after all attachments
on a message are processed.

This class centralises the repeated list storage and reset pattern used by
NSE trade emails, ICICI bank statements with PPF bands, and future ICICI Direct
equity/MF statement parsers.
"""

from __future__ import annotations

from parsers.holdings.base import ParsedHolding, ParsedInvestmentTxn
from parsers.statements.base import BaseStatementEmailParser


class BaseBrokerStatementParser(BaseStatementEmailParser):
    """Broker statement PDF reader with holdings / investment txn side channels."""

    def __init__(self, accounts: dict[str, dict]) -> None:
        super().__init__(accounts)
        self._attachment_holdings: list[ParsedHolding] = []
        self._attachment_inv_txns: list[ParsedInvestmentTxn] = []

    def attachment_investment_outputs(
        self,
    ) -> tuple[list[ParsedHolding], list[ParsedInvestmentTxn]]:
        """Holdings and investment txns accumulated while parsing this message's PDF(s)."""
        return (self._attachment_holdings, self._attachment_inv_txns)

    def reset_attachment_outputs(self) -> None:
        """Clear side channels before processing PDF(s) for a new Gmail message."""
        self._attachment_holdings = []
        self._attachment_inv_txns = []
