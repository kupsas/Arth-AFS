"""PPF deployed capital from linked ledger rows (contributions only, no interest)."""

from __future__ import annotations

from sqlmodel import Session, select

from api.models import InvestmentTransaction
from pipeline.models import InvestmentTxnType

# Same inflow/outflow convention as ``returns_calculator._cost_basis_from_txns``,
# but **excluding** DIVIDEND — interest must not count as money you "invested".
_PPF_CONTRIBUTION_INFLOW = frozenset(
    {
        InvestmentTxnType.BUY.value,
        InvestmentTxnType.SIP.value,
        InvestmentTxnType.SWITCH_IN.value,
    }
)
_PPF_CONTRIBUTION_OUTFLOW = frozenset(
    {
        InvestmentTxnType.SELL.value,
        InvestmentTxnType.SWITCH_OUT.value,
    }
)


def ppf_net_contributions_from_ledger(session: Session, holding_id: int) -> float | None:
    """
    Net PPF contributions: sum(inflows) − sum(outflows) on ``holding_id``.

    Returns a positive INR amount when the ledger implies deployed capital; ``None``
    if there are no rows or the net is non‑positive (caller may fall back to
    ``Holding.principal_amount``).
    """
    rows = list(
        session.exec(
            select(InvestmentTransaction).where(InvestmentTransaction.holding_id == holding_id)
        ).all()
    )
    if not rows:
        return None
    inf = 0.0
    outf = 0.0
    for r in rows:
        amt = abs(float(r.total_amount))
        if r.txn_type in _PPF_CONTRIBUTION_INFLOW:
            inf += amt
        elif r.txn_type in _PPF_CONTRIBUTION_OUTFLOW:
            outf += amt
    net = round(inf - outf, 2)
    return net if net > 0 else None
