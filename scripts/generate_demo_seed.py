#!/usr/bin/env python3
"""
Build ``data/arth_demo_seed.db`` — a self-contained SQLite snapshot for public demo.

Run from repo root (or anywhere):

    python scripts/generate_demo_seed.py

Requires **no** prior DB: we set ``ARTH_DB_PATH`` before importing project modules
so ``api.database`` binds to the seed file, then call :func:`api.database.init_db`
and insert synthetic Indian-household-shaped data keyed to user ``demo``.

The FastAPI demo server copies this file per browser session; visitors never write
to this golden seed on disk (only to their temp copy).
"""

from __future__ import annotations

import calendar
import datetime
import hashlib
import json
import math
import os
import random
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: point SQLite at the seed file **before** any Arth imports pull
# ``pipeline.config.DB_PATH`` into memory.
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
SEED_PATH = REPO / "data" / "arth_demo_seed.db"
SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
if SEED_PATH.exists():
    SEED_PATH.unlink()
os.environ["ARTH_DB_PATH"] = str(SEED_PATH)
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_SCRIPTS_DIR = REPO / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import demo_portfolio_plan as dpp  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from api.database import SQLiteSerializingSession, get_engine, init_db  # noqa: E402
from api.models import (  # noqa: E402
    AppUser,
    ChatMessage,
    ChatSession,
    FamilyMember,
    Goal,
    Holding,
    HoldingValueSnapshot,
    InvestmentTransaction,
    Liability,
    OnboardingState,
    PipelineRun,
    Price,
    RecurringPattern,
    Transaction,
    UserClassificationSettings,
    UserSimulationSandboxPreferences,
)
from api.services.user_classification import merge_starter_pack_for_user  # noqa: E402
from pipeline.models import (  # noqa: E402
    AssetClass,
    InvestmentTxnType,
    LiabilityType,
    LiquidityClass,
    ValuationMethod,
)

DEMO_USER = dpp.DEMO_USER_ID
ACCOUNT_SAV = "hdfc_savings_demo"
ACCOUNT_CC = "hdfc_cc_demo"
SOURCE = "demo_seed"

# ---------------------------------------------------------------------------
# Portfolio demo timeline (must stay **wider** than the UI's 12M trend window)
# ---------------------------------------------------------------------------
# ``market_position_quantities_as_of`` only sees quantities from investment rows
# dated on or before each chart point — if the first BUY is only 60 days ago,
# the whole prior year plots as flat zero.  Start positions here instead.
_DEMO_TODAY = datetime.date.today()
DEMO_HISTORY_START = dpp.demo_history_start(_DEMO_TODAY)
DEMO_COST_ANCHOR_DATE = dpp.demo_cost_anchor_date(_DEMO_TODAY)
DEMO_HOLDING_CREATED_AT = datetime.datetime.combine(
    DEMO_HISTORY_START, datetime.time.min, tzinfo=datetime.UTC
)

# Last N calendar months of synthetic bank rows — matches dashboard “12M” trend toggle.
DEMO_ROLLING_TXN_MONTHS = 12


def _month_labels_oldest_first(today: datetime.date, n_months: int = DEMO_ROLLING_TXN_MONTHS) -> list[tuple[int, int]]:
    """``(year, month)`` oldest → newest, same ordering as ``metrics._generate_month_labels``."""
    out: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(n_months):
        out.insert(0, (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def _demo_base_close(symbol: str) -> float:
    """Starting scale (INR) for synthetic demo closes — not real market levels."""
    if symbol.isdigit():
        # Mutual fund NAV-ish
        return 350.0 if symbol == "122639" else 780.0 if symbol == "118551" else 200.0
    bases = {
        "TCS": 3850.0,
        "INFY": 1520.0,
        "RELIANCE": 1380.0,
        "HDFCBANK": 1620.0,
        "ITC": 415.0,
        "SBIN": 820.0,
        "ASIANPAINT": 2850.0,
        "TATAMOTORS": 720.0,
    }
    return float(bases.get(symbol, 1000.0))


def _demo_synthetic_close(symbol: str, on: datetime.date, *, today: datetime.date) -> float:
    """Deterministic pseudo-price curve: slow drift up + tiny wiggle (demo only)."""
    span = max((today - DEMO_HISTORY_START).days, 1)
    t = (on - DEMO_HISTORY_START).days / span
    t = max(0.0, min(1.0, t))
    phase = (on - DEMO_HISTORY_START).days * 0.17
    wobble = 1.0 + 0.035 * math.sin(phase)
    drift = 1.0 + 0.18 * t
    return round(_demo_base_close(symbol) * drift * wobble, 4)


def _all_demo_price_symbols() -> list[str]:
    return dpp.demo_market_price_symbols()


def _txn_hash(txn_date: datetime.date, raw: str, amount: float, account_id: str) -> str:
    key = "|".join([txn_date.isoformat(), raw, str(amount), account_id])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _promote_local_install_to_demo(session: Session) -> None:
    """``init_db`` seeds ``local`` — rename that identity to ``demo`` everywhere."""
    u = session.exec(select(AppUser).where(AppUser.username == "local")).first()
    if u is not None:
        u.username = DEMO_USER
        u.setup_completed_at = datetime.datetime.now(datetime.UTC)
        session.add(u)

    tables = [
        "scraper_bank_senders",
        "scraper_account_mappings",
        "family_members",
        "transactions",
        "recurring_patterns",
        "goals",
        "goal_status_cache",
        "life_events",
        "reminders",
        "holdings",
        "liabilities",
        "user_contacts",
        "user_merchant_rules",
        "user_classification_settings",
        "user_simulation_sandbox_preferences",
        "onboarding_states",
        "user_pipeline_sources",
        "chat_sessions",
    ]
    for t in tables:
        try:
            session.execute(
                text(f"UPDATE {t} SET user_id = :d WHERE user_id = 'local'"),
                {"d": DEMO_USER},
            )
        except Exception:
            session.rollback()
            raise
    session.commit()

    fam = session.exec(
        select(FamilyMember).where(
            FamilyMember.user_id == DEMO_USER,
            FamilyMember.relationship == "SELF",
        )
    ).first()
    if fam is not None:
        fam.name = "Demo User"
        session.add(fam)
        session.commit()


def _seed_onboarding(session: Session) -> None:
    row = session.exec(select(OnboardingState).where(OnboardingState.user_id == DEMO_USER)).first()
    if row is None:
        row = OnboardingState(
            user_id=DEMO_USER,
            current_step="done",
            completed_steps_json=json.dumps(["welcome", "done"]),
            discovery_results_json="{}",
            backfill_progress_json="{}",
            persist_sources_status="idle",
            preclassification_raw_json="{}",
        )
    else:
        row.current_step = "done"
        row.completed_steps_json = json.dumps(["welcome", "done"])
    session.add(row)
    session.commit()


def _seed_simulation_sandbox_preferences(session: Session) -> None:
    """Persist ₹1.5L/mo surplus for the simulate page (matches SANDBOX_DEFAULT_MONTHLY_SURPLUS_INR)."""
    now = datetime.datetime.now(datetime.UTC)
    row = session.exec(
        select(UserSimulationSandboxPreferences).where(
            UserSimulationSandboxPreferences.user_id == DEMO_USER
        )
    ).first()
    if row is None:
        row = UserSimulationSandboxPreferences(
            user_id=DEMO_USER,
            monthly_surplus_inr=150_000.0,
            salary_growth_rate_pct=5.0,
            general_inflation_rate_pct=6.0,
        )
    else:
        row.monthly_surplus_inr = 150_000.0
        row.salary_growth_rate_pct = 5.0
        row.general_inflation_rate_pct = 6.0
    row.updated_at = now
    session.add(row)
    session.commit()


def _seed_classification_settings(session: Session) -> None:
    row = session.exec(
        select(UserClassificationSettings).where(UserClassificationSettings.user_id == DEMO_USER)
    ).first()
    if row is None:
        row = UserClassificationSettings(user_id=DEMO_USER)
    row.self_name = "Demo User"
    row.self_aliases_json = json.dumps(["DEMO USER"])
    row.rent_recipient = "LANDLORD"
    row.rent_pattern = "RENT"
    session.add(row)
    session.commit()


def _seed_pipeline_run(session: Session) -> int:
    pr = PipelineRun(
        source_key="demo_seed",
        llm_model="none",
        txn_count=0,
        new_count=0,
        updated_count=0,
        status="completed",
        txn_date_min=DEMO_HISTORY_START,
        txn_date_max=datetime.date.today(),
        completed_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(pr)
    session.commit()
    session.refresh(pr)
    assert pr.id is not None
    return pr.id


def _seed_transactions(session: Session, pipeline_run_id: int) -> None:
    rng = random.Random(42)
    today = datetime.date.today()
    # Subscriptions are seeded deterministically below — keep them out of the random pool
    # so each service appears exactly once per month with a realistic plan price.
    merchants_out = [
        ("UPI-SWIGGY", "Swiggy", "Food & Dining", "UPI_EXPENSE", "WANT"),
        ("UPI-ZOMATO", "Zomato", "Food & Dining", "UPI_EXPENSE", "WANT"),
        ("UPI-BIGBASKET", "BigBasket", "Shopping & E-commerce", "UPI_EXPENSE", "NEED"),
        ("UPI-ZEPTO", "Zepto", "Shopping & E-commerce", "UPI_EXPENSE", "NEED"),
        ("UPI-UBER", "Uber", "Transport & Fuel", "UPI_EXPENSE", "NEED"),
        ("UPI-RENT", "Rent Payment", "Rent & Housing", "BANK_TRANSFER", "NEED"),
        ("ACH-EMI", "Home Loan EMI", "Financial Services, Insurance & Banking", "BANK_TRANSFER", "NEED"),
        ("UPI-ELEC", "BESCOM Utility", "Utilities & Internet", "UPI_EXPENSE", "NEED"),
    ]

    # Exactly one charge per month, on the same billing date each month, at a fixed plan price.
    # Netflix Mobile plan: ₹149/mo; Hotstar Super: ₹299/mo; Spotify Individual: ₹119/mo.
    subscriptions = [
        # (prefix,   counterparty, amount, billing_day_of_month)
        ("UPI-NETFLIX", "Netflix", 149.0, 3),
        ("UPI-SPOTIFY", "Spotify", 119.0, 7),
        ("UPI-HOTSTAR", "Hotstar", 299.0, 12),
    ]

    n = 0
    tid = 0
    # Newest → oldest so salary creep matches the old ``month_offset`` semantics.
    for month_offset, (yy, mm) in enumerate(reversed(_month_labels_oldest_first(today))):
        last_dom = calendar.monthrange(yy, mm)[1]
        base = datetime.date(yy, mm, min(15, last_dom))
        # Salary inflow once per month
        tid += 1
        amt = 185000.0 + month_offset * 1500
        raw = f"NEFT CREDIT SALARY CORP ACME {base.isoformat()}"
        session.add(
            Transaction(
                content_hash=_txn_hash(base, raw, amt, ACCOUNT_SAV),
                txn_date=base,
                account_id=ACCOUNT_SAV,
                user_id=DEMO_USER,
                source_statement=SOURCE,
                direction="INFLOW",
                amount=amt,
                txn_type="INCOME_SALARY",
                channel="BANK",
                counterparty="Acme Corp",
                counterparty_category="Salary & Income",
                raw_description=raw,
                is_reviewed=True,
                source_type="statement",
                classification_source="RULES_GENERIC",
                pipeline_run_id=pipeline_run_id,
                spend_category=None,
            )
        )
        n += 1

        # One charge per subscription service, on a fixed billing day.
        for sub_prefix, sub_cp, sub_amt, bill_day in subscriptions:
            tid += 1
            d_sub = datetime.date(yy, mm, min(bill_day, last_dom))
            # Skip future months so we don't pre-charge subscriptions.
            if d_sub > today:
                continue
            raw_sub = f"{sub_prefix}-{d_sub.isoformat()}"
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_sub, raw_sub, sub_amt, ACCOUNT_SAV),
                    txn_date=d_sub,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=sub_amt,
                    txn_type="UPI_EXPENSE",
                    channel="UPI",
                    counterparty=sub_cp,
                    counterparty_category="Mobile, OTT & Subscriptions",
                    raw_description=raw_sub,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="WANT",
                )
            )
            n += 1

        # ~67 mixed spends per month on savings + a few on CC (kept total ~70 with subs above)
        for _ in range(67):
            tid += 1
            d = base - datetime.timedelta(days=rng.randint(0, 27))
            mraw, cp, cat, ttype, spend = rng.choice(merchants_out)
            raw_d = f"{mraw}-{tid}-{d.isoformat()}"
            amt_o = float(rng.choice([120, 249, 499, 899, 1299, 2199, 3499]))
            acct = ACCOUNT_CC if rng.random() < 0.15 else ACCOUNT_SAV
            email_row = rng.random() < 0.03 and acct == ACCOUNT_SAV
            session.add(
                Transaction(
                    content_hash=_txn_hash(d, raw_d, amt_o, acct),
                    txn_date=d,
                    account_id=acct,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=amt_o,
                    txn_type=ttype,
                    channel="UPI",
                    counterparty=cp,
                    counterparty_category=cat,
                    raw_description=raw_d,
                    is_reviewed=not email_row,
                    source_type="email" if email_row else "statement",
                    classification_source="RULES_GENERIC" if not email_row else "LLM",
                    review_confidence="MEDIUM" if email_row else None,
                    pipeline_run_id=pipeline_run_id,
                    spend_category=spend,
                    gmail_message_id=f"demo-{tid}" if email_row else None,
                )
            )
            n += 1

    session.commit()
    print(f"Inserted {n} demo transactions.")


def _seed_dashboard_chart_transactions(session: Session, pipeline_run_id: int) -> None:
    """Bank ``Transaction`` rows that feed dashboard charts (investment net + category trends).

    Covers **12** trailing calendar months (Expense Trends 12M toggle). Seeds routine category
    bars plus two **splurge** months: OLED TV (shopping / WANT) and international flights +
    hotel (travel / WANT), each with thin MF/equity buys and MF redemptions so investment **net**
    reads low compared with neighbours.

    The expense-trends page calls ``GET /api/metrics/investment-trend`` (MF/EQUITY purchase &
    sale txn_types) and ``GET /api/metrics/category-trend`` with filters from
    ``api.services.chart_metrics`` — e.g. counterparty must be exactly ``Swiggy Instamart``.
    """
    rng = random.Random(202)
    today = datetime.date.today()
    n = 0
    tid = 70_000

    month_labels = _month_labels_oldest_first(today)
    # Two “story” months: big discretionary spend + thin investing (net flow well below normal).
    splurge_tv = month_labels[4] if len(month_labels) > 4 else None
    splurge_travel = month_labels[9] if len(month_labels) > 9 else None

    def _dom(yy: int, mm: int, day: int) -> datetime.date:
        last = calendar.monthrange(yy, mm)[1]
        return datetime.date(yy, mm, min(day, last))

    for mi, (yy, mm) in enumerate(month_labels):
        key = (yy, mm)
        is_tv_month = splurge_tv is not None and key == splurge_tv
        is_travel_month = splurge_travel is not None and key == splurge_travel
        splurge = is_tv_month or is_travel_month

        # --- Investment net (purchases − sales) ---
        if splurge:
            # Small fresh buys + a chunky redemption → low / negative net “savings” vs other months.
            d_pur = _dom(yy, mm, 5)
            pur_amt = 2_600.0 + float(rng.randint(0, 900))
            raw_p = f"NEFT MF PURCHASE ZERODHA {pur_amt:.0f} {yy}-{mm:02d}-splurge"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_pur, raw_p, pur_amt, ACCOUNT_SAV),
                    txn_date=d_pur,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=pur_amt,
                    txn_type="MF_PURCHASE",
                    channel="BANK",
                    counterparty="Zerodha Coin",
                    counterparty_category="Financial Services, Insurance & Banking",
                    raw_description=raw_p,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="INVESTMENT",
                )
            )
            n += 1

            d_eq = _dom(yy, mm, 12)
            eq_amt = 1_800.0 + float(rng.randint(0, 600))
            raw_e = f"UPI ICICI DIRECT EQ BUY {eq_amt:.0f} {yy}-{mm:02d}-splurge"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_eq, raw_e, eq_amt, ACCOUNT_SAV),
                    txn_date=d_eq,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=eq_amt,
                    txn_type="EQUITY_PURCHASE",
                    channel="UPI",
                    counterparty="ICICI Direct",
                    counterparty_category="Financial Services, Insurance & Banking",
                    raw_description=raw_e,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="INVESTMENT",
                )
            )
            n += 1

            d_sale = _dom(yy, mm, 26)
            sale_amt = (42_000.0 if is_tv_month else 18_000.0) + float(rng.randint(0, 4_000))
            raw_s = f"MF REDEMPTION CAMS {sale_amt:.0f} {yy}-{mm:02d}-splurge"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_sale, raw_s, sale_amt, ACCOUNT_SAV),
                    txn_date=d_sale,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="INFLOW",
                    amount=sale_amt,
                    txn_type="MF_SALE",
                    channel="BANK",
                    counterparty="CAMS",
                    counterparty_category="Financial Services, Insurance & Banking",
                    raw_description=raw_s,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category=None,
                )
            )
            n += 1
        else:
            d_pur = _dom(yy, mm, 5)
            pur_amt = 12_000.0 + mi * 1_350.0 + float(rng.randint(0, 6_000))
            raw_p = f"NEFT MF PURCHASE ZERODHA {pur_amt:.0f} {yy}-{mm:02d}-demo"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_pur, raw_p, pur_amt, ACCOUNT_SAV),
                    txn_date=d_pur,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=pur_amt,
                    txn_type="MF_PURCHASE",
                    channel="BANK",
                    counterparty="Zerodha Coin",
                    counterparty_category="Financial Services, Insurance & Banking",
                    raw_description=raw_p,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="INVESTMENT",
                )
            )
            n += 1

            d_eq = _dom(yy, mm, 12)
            eq_amt = 8_500.0 + float(rng.randint(0, 4_000))
            raw_e = f"UPI ICICI DIRECT EQ BUY {eq_amt:.0f} {yy}-{mm:02d}-demo"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_eq, raw_e, eq_amt, ACCOUNT_SAV),
                    txn_date=d_eq,
                    account_id=ACCOUNT_SAV,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=eq_amt,
                    txn_type="EQUITY_PURCHASE",
                    channel="UPI",
                    counterparty="ICICI Direct",
                    counterparty_category="Financial Services, Insurance & Banking",
                    raw_description=raw_e,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="INVESTMENT",
                )
            )
            n += 1

            if mi % 3 == 2:
                d_sale = _dom(yy, mm, 24)
                sale_amt = 5_500.0 + float(rng.randint(0, 2_500))
                raw_s = f"MF REDEMPTION CAMS {sale_amt:.0f} {yy}-{mm:02d}-demo"
                tid += 1
                session.add(
                    Transaction(
                        content_hash=_txn_hash(d_sale, raw_s, sale_amt, ACCOUNT_SAV),
                        txn_date=d_sale,
                        account_id=ACCOUNT_SAV,
                        user_id=DEMO_USER,
                        source_statement=SOURCE,
                        direction="INFLOW",
                        amount=sale_amt,
                        txn_type="MF_SALE",
                        channel="BANK",
                        counterparty="CAMS",
                        counterparty_category="Financial Services, Insurance & Banking",
                        raw_description=raw_s,
                        is_reviewed=True,
                        source_type="statement",
                        classification_source="RULES_GENERIC",
                        pipeline_run_id=pipeline_run_id,
                        spend_category=None,
                    )
                )
                n += 1

        # --- One-off high “WANT” lines (stacked bar + category shopping/travel charts) ---
        if is_tv_month:
            d_tv = _dom(yy, mm, 19)
            tv_amt = 64_999.0
            raw_tv = f"UPI-CROMA-TV-OLED-{tid}-{d_tv.isoformat()}"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_tv, raw_tv, tv_amt, ACCOUNT_CC),
                    txn_date=d_tv,
                    account_id=ACCOUNT_CC,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=tv_amt,
                    txn_type="UPI_EXPENSE",
                    channel="UPI",
                    counterparty="Croma",
                    counterparty_category="Shopping & E-commerce",
                    raw_description=raw_tv,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="WANT",
                )
            )
            n += 1

        if is_travel_month:
            d_intl = _dom(yy, mm, 21)
            intl_amt = 88_500.0
            raw_intl = f"CARD-SG-AIRLINES-{tid}-{d_intl.isoformat()}"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_intl, raw_intl, intl_amt, ACCOUNT_CC),
                    txn_date=d_intl,
                    account_id=ACCOUNT_CC,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=intl_amt,
                    txn_type="UPI_EXPENSE",
                    channel="CARD",
                    counterparty="Singapore Airlines",
                    counterparty_category="Travel & Stay",
                    raw_description=raw_intl,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="WANT",
                )
            )
            n += 1
            d_hot = _dom(yy, mm, 22)
            hotel_amt = 24_000.0
            raw_hot = f"UPI-BOOKINGCOM-AMS-{tid}-{d_hot.isoformat()}"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_hot, raw_hot, hotel_amt, ACCOUNT_CC),
                    txn_date=d_hot,
                    account_id=ACCOUNT_CC,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=hotel_amt,
                    txn_type="UPI_EXPENSE",
                    channel="UPI",
                    counterparty="Booking.com",
                    counterparty_category="Travel & Stay",
                    raw_description=raw_hot,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="WANT",
                )
            )
            n += 1

        # --- Category trend: Swiggy Instamart (counterparty must match exactly) ---
        for day, lo, hi in ((8, 900, 2_400), (20, 1_200, 3_800)):
            d_sw = _dom(yy, mm, day)
            amt_sw = float(rng.randint(lo, hi))
            raw_sw = f"UPI-SWIGGYINSTAMART-{tid}-{d_sw.isoformat()}"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_sw, raw_sw, amt_sw, ACCOUNT_CC),
                    txn_date=d_sw,
                    account_id=ACCOUNT_CC,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=amt_sw,
                    txn_type="UPI_EXPENSE",
                    channel="UPI",
                    counterparty="Swiggy Instamart",
                    counterparty_category="Food & Dining",
                    raw_description=raw_sw,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="NEED",
                )
            )
            n += 1

        # --- Swiggy Food ---
        for day in (10, 23):
            d_sf = _dom(yy, mm, day)
            amt_sf = float(rng.randint(400, 2_800))
            raw_sf = f"UPI-SWIGGYFOOD-{tid}-{d_sf.isoformat()}"
            tid += 1
            session.add(
                Transaction(
                    content_hash=_txn_hash(d_sf, raw_sf, amt_sf, ACCOUNT_CC),
                    txn_date=d_sf,
                    account_id=ACCOUNT_CC,
                    user_id=DEMO_USER,
                    source_statement=SOURCE,
                    direction="OUTFLOW",
                    amount=amt_sf,
                    txn_type="UPI_EXPENSE",
                    channel="UPI",
                    counterparty="Swiggy Food",
                    counterparty_category="Food & Dining",
                    raw_description=raw_sf,
                    is_reviewed=True,
                    source_type="statement",
                    classification_source="RULES_GENERIC",
                    pipeline_run_id=pipeline_run_id,
                    spend_category="WANT",
                )
            )
            n += 1

        # --- Travel & stay (``counterparty_category`` must be exactly ``Travel & Stay``) ---
        d_tr = _dom(yy, mm, 16)
        amt_tr = float(rng.randint(3_500, 14_000))
        raw_tr = f"UPI-MAKEMYTRIP-{tid}-{d_tr.isoformat()}"
        tid += 1
        session.add(
            Transaction(
                content_hash=_txn_hash(d_tr, raw_tr, amt_tr, ACCOUNT_CC),
                txn_date=d_tr,
                account_id=ACCOUNT_CC,
                user_id=DEMO_USER,
                source_statement=SOURCE,
                direction="OUTFLOW",
                amount=amt_tr,
                txn_type="UPI_EXPENSE",
                channel="UPI",
                counterparty="MakeMyTrip",
                counterparty_category="Travel & Stay",
                raw_description=raw_tr,
                is_reviewed=True,
                source_type="statement",
                classification_source="RULES_GENERIC",
                pipeline_run_id=pipeline_run_id,
                spend_category="WANT",
            )
        )
        n += 1

    session.commit()
    print(f"Inserted {n} dashboard chart demo transactions.")


def _seed_prices(session: Session, symbols: list[str]) -> None:
    """Fill ``prices`` for every demo symbol from ``DEMO_HISTORY_START`` → today.

    Live Arth reads bhav/NAV into this table; the public demo instead ships a
    deterministic synthetic series so charts, CMP, and "cost as of anchor day"
    all resolve without calling external market APIs.
    """
    today = _DEMO_TODAY
    n = 0
    for sym in symbols:
        d = DEMO_HISTORY_START
        while d <= today:
            session.add(
                Price(
                    symbol=sym,
                    date=d,
                    close_price=float(_demo_synthetic_close(sym, d, today=today)),
                    source="demo_seed",
                )
            )
            n += 1
            d += datetime.timedelta(days=1)
    session.commit()
    print(f"Inserted {n} demo price rows ({len(symbols)} symbols).")


def _seed_holdings_and_inv(session: Session) -> None:
    """Layer-1 holdings + investment ledger so cost, gains, and history render."""
    today = _DEMO_TODAY
    sip_dates = dpp.monthly_investment_dates(
        DEMO_HISTORY_START, today, day_of_month=dpp.DEMO_MONTHLY_SIP_DOM
    )

    def _synthetic_close_resolver(sym: str, on: datetime.date) -> float | None:
        return float(_demo_synthetic_close(sym, on, today=today))

    rows: list[Holding] = []

    for spec in dpp.DEMO_EQUITY_SPECS:
        sym = str(spec["symbol"])
        rows.append(
            Holding(
                user_id=DEMO_USER,
                symbol=sym,
                name=str(spec["name"]),
                quantity=0.0,
                asset_class=AssetClass.EQUITY.value,
                account_platform=str(spec["platform"]),
                valuation_method=ValuationMethod.MARKET_PRICE.value,
                average_cost_per_unit=None,
                current_price_per_unit=None,
                current_value=0.0,
                last_valued_date=today,
                liquidity_class=LiquidityClass.T_PLUS_1.value,
                sector=str(spec["sector"]) if spec.get("sector") else None,
                market_cap_class=str(spec["market_cap_class"]) if spec.get("market_cap_class") else None,
                created_at=DEMO_HOLDING_CREATED_AT,
            )
        )

    for spec in dpp.DEMO_MF_SPECS:
        sym = str(spec["symbol"])
        rows.append(
            Holding(
                user_id=DEMO_USER,
                symbol=sym,
                name=str(spec["name"]),
                quantity=0.0,
                asset_class=AssetClass.MUTUAL_FUND.value,
                account_platform=str(spec["platform"]),
                valuation_method=ValuationMethod.MARKET_PRICE.value,
                average_cost_per_unit=None,
                current_price_per_unit=None,
                current_value=0.0,
                last_valued_date=today,
                liquidity_class=LiquidityClass.T_PLUS_3.value,
                fund_category=str(spec["fund_category"]) if spec.get("fund_category") else None,
                fund_house=str(spec["fund_house"]) if spec.get("fund_house") else None,
                created_at=DEMO_HOLDING_CREATED_AT,
            )
        )

    # --- Fixed income / wrappers ---
    rows.append(
        Holding(
            user_id=DEMO_USER,
            symbol=None,
            name="HDFC Bank FD",
            quantity=None,
            asset_class=AssetClass.FD.value,
            account_platform="HDFC Bank",
            valuation_method=ValuationMethod.FIXED_RETURN.value,
            principal_amount=500000.0,
            interest_rate=7.25,
            maturity_date=today + datetime.timedelta(days=365),
            compounding_frequency="QUARTERLY",
            current_value=500000.0,
            last_valued_date=today,
            liquidity_class=LiquidityClass.WEEKS.value,
            created_at=DEMO_HOLDING_CREATED_AT,
        )
    )

    ppf_contrib_dates = dpp.monthly_investment_dates(
        DEMO_HISTORY_START, today, day_of_month=7
    )
    ppf_monthly_inr = 10000.0
    ppf_interest_chunks = [44_000.0, 44_000.0, 44_000.0, 44_000.0, 44_000.0]
    ppf_principal = round(len(ppf_contrib_dates) * ppf_monthly_inr, 2)
    rows.append(
        Holding(
            user_id=DEMO_USER,
            symbol=None,
            name="Public Provident Fund",
            quantity=None,
            asset_class=AssetClass.PPF.value,
            account_platform="SBI",
            valuation_method=ValuationMethod.MANUAL.value,
            principal_amount=ppf_principal,
            current_value=850000.0,
            last_valued_date=today,
            liquidity_class=LiquidityClass.ILLIQUID.value,
            created_at=DEMO_HOLDING_CREATED_AT,
        )
    )

    rows.append(
        Holding(
            user_id=DEMO_USER,
            symbol=None,
            name="National Pension System Tier I",
            quantity=None,
            asset_class=AssetClass.NPS.value,
            account_platform="Protean",
            valuation_method=ValuationMethod.MANUAL.value,
            principal_amount=310000.0,
            current_value=420000.0,
            last_valued_date=today,
            liquidity_class=LiquidityClass.ILLIQUID.value,
            created_at=DEMO_HOLDING_CREATED_AT,
        )
    )

    for h in rows:
        session.add(h)
    session.commit()

    # Resolve ids after commit
    by_key: dict[tuple[str, str], int] = {}
    for spec in dpp.DEMO_EQUITY_SPECS:
        hid = session.exec(
            select(Holding.id).where(
                Holding.user_id == DEMO_USER,
                Holding.symbol == str(spec["symbol"]),
                Holding.asset_class == AssetClass.EQUITY.value,
            )
        ).first()
        if hid is not None:
            by_key[("eq", str(spec["symbol"]))] = int(hid)
    for spec in dpp.DEMO_MF_SPECS:
        hid = session.exec(
            select(Holding.id).where(
                Holding.user_id == DEMO_USER,
                Holding.symbol == str(spec["symbol"]),
                Holding.asset_class == AssetClass.MUTUAL_FUND.value,
            )
        ).first()
        if hid is not None:
            by_key[("mf", str(spec["symbol"]))] = int(hid)

    ppf_h = session.exec(
        select(Holding).where(
            Holding.user_id == DEMO_USER,
            Holding.asset_class == AssetClass.PPF.value,
        )
    ).first()
    nps_h = session.exec(
        select(Holding).where(
            Holding.user_id == DEMO_USER,
            Holding.asset_class == AssetClass.NPS.value,
        )
    ).first()

    inv_rows: list[InvestmentTransaction] = []
    holding_updates: dict[int, tuple[float, float, float, float]] = {}

    for spec in dpp.DEMO_EQUITY_SPECS:
        sym = str(spec["symbol"])
        hid = by_key.get(("eq", sym))
        if hid is None:
            continue
        plan_rows, qty, px_a, px_t = dpp.build_market_ledger_plan(
            spec=spec,
            holding_id=hid,
            sip_dates=sip_dates,
            close_on_or_before=_synthetic_close_resolver,
            anchor_date=DEMO_COST_ANCHOR_DATE,
            today=today,
        )
        for pr in plan_rows:
            inv_rows.append(InvestmentTransaction(**pr))
        if px_a is not None and px_t is not None and qty > 0:
            holding_updates[hid] = (qty, px_a, px_t, round(qty * px_t, 2))

    for spec in dpp.DEMO_MF_SPECS:
        sym = str(spec["symbol"])
        hid = by_key.get(("mf", sym))
        if hid is None:
            continue
        plan_rows, qty, px_a, px_t = dpp.build_market_ledger_plan(
            spec=spec,
            holding_id=hid,
            sip_dates=sip_dates,
            close_on_or_before=_synthetic_close_resolver,
            anchor_date=DEMO_COST_ANCHOR_DATE,
            today=today,
        )
        for pr in plan_rows:
            inv_rows.append(InvestmentTransaction(**pr))
        if px_a is not None and px_t is not None and qty > 0:
            holding_updates[hid] = (qty, px_a, px_t, round(qty * px_t, 2))

    if ppf_h is not None and ppf_h.id is not None:
        for d in ppf_contrib_dates:
            inv_rows.append(
                InvestmentTransaction(
                    txn_date=d,
                    symbol=None,
                    txn_type=InvestmentTxnType.BUY.value,
                    quantity=1.0,
                    price_per_unit=ppf_monthly_inr,
                    total_amount=ppf_monthly_inr,
                    account_platform=ppf_h.account_platform,
                    holding_id=ppf_h.id,
                    is_reviewed=True,
                    source_type="statement",
                )
            )
        for k, amt in enumerate(ppf_interest_chunks, start=1):
            inv_rows.append(
                InvestmentTransaction(
                    txn_date=DEMO_HISTORY_START + datetime.timedelta(days=100 * k + 40),
                    symbol=None,
                    txn_type=InvestmentTxnType.DIVIDEND.value,
                    quantity=1.0,
                    price_per_unit=amt,
                    total_amount=amt,
                    account_platform=ppf_h.account_platform,
                    holding_id=ppf_h.id,
                    is_reviewed=True,
                    source_type="statement",
                    notes=f"PPF interest accrual {k} (demo)",
                )
            )

    # NPS: statement snapshots interpolate Tier I value (CRA-style import).
    if nps_h is not None and nps_h.id is not None:
        start_v = 210000.0
        end_v = float(nps_h.current_value or 420000.0)
        d = DEMO_HISTORY_START
        month_i = 0
        total_months = max(int(round((today - DEMO_HISTORY_START).days / 30.0)), 1)
        while d <= today:
            alpha = min(1.0, month_i / total_months)
            v = round(start_v + (end_v - start_v) * alpha, 2)
            session.add(
                HoldingValueSnapshot(
                    holding_id=nps_h.id,
                    snapshot_date=d,
                    value=v,
                    source="demo_seed",
                    notes="Synthetic CRA statement balance",
                )
            )
            d += datetime.timedelta(days=30)
            month_i += 1

    for ir in inv_rows:
        session.add(ir)
    session.commit()

    for hid, (qty, px_a, px_t, cur) in holding_updates.items():
        h = session.get(Holding, hid)
        if h is None:
            continue
        h.quantity = qty
        h.average_cost_per_unit = px_a
        h.current_price_per_unit = px_t
        h.current_value = cur
        session.add(h)
    session.commit()

    print(
        "Seeded holdings + investment rows (equities="
        f"{len(dpp.DEMO_EQUITY_SPECS)}, mfs={len(dpp.DEMO_MF_SPECS)}, "
        f"investment_txn_rows={len(inv_rows)})."
    )


def _seed_goals(session: Session) -> None:
    """Financial goals aligned with production ``goals`` rows from ``data/arth_main.db``.

    Source of truth (queried 2026-05-12): ``SELECT ... FROM goals WHERE user_id='local'``
    — that user had the most goals in the file (7 rows; no other ``user_id`` had goals).
    We copy every field that exists on :class:`~api.models.Goal` and was set in SQLite.

    Not copied from SQLite (demo-specific): ``id``, ``user_id`` (we use ``demo`` after
    ``_promote_local_install_to_demo``), ``created_at`` / ``updated_at`` (ORM defaults).

    Production did not set ``pyramid_id`` (NULL on every row). The demo DB requires **unique**
    ``pyramid_id`` per user (see ``uq_goals_user_pyramid_id``), so we assign short stable ids
    ``H1`` … ``P1``. ``chart_key`` values must stay in ``KNOWN_CHART_KEYS`` in
    ``api.services.chart_metrics`` (``investment_net`` for retirement; ``category:*`` for spend caps).
    """
    goals = [
        # --- Row mirrored from prod id=1 (House down payment) ---
        Goal(
            user_id=DEMO_USER,
            name="House down payment",
            goal_type="SAVINGS",
            target_amount=10_000_000.0,
            target_date=datetime.date(2036, 5, 8),
            priority=1,
            linked_layer=3,
            progress_cadence="MONTHLY",
            current_value=5_000_000.0,
            status="ON_TRACK",
            pyramid_id="H1",
            time_horizon="MULTI_YEAR",
            funding_mode="ACCUMULATION",
            activation_status="ACTIVE",
            allocation_priority=2,
            interruptible=True,
            goal_class="POINT_IN_TIME",
            goal_specific_inflation_rate=8.0,
            expected_return_rate=10.0,
            starting_balance=5_000_000.0,
            goal_subtype="HOME_PURCHASE",
        ),
        # --- Prod id=2 ---
        Goal(
            user_id=DEMO_USER,
            name="Buy a car / vehicle",
            goal_type="SAVINGS",
            target_amount=1_000_000.0,
            target_date=datetime.date(2029, 2, 8),
            priority=2,
            linked_layer=3,
            progress_cadence="MONTHLY",
            current_value=660_000.0,
            status="ON_TRACK",
            pyramid_id="V1",
            time_horizon="MULTI_YEAR",
            funding_mode="ACCUMULATION",
            activation_status="ACTIVE",
            allocation_priority=4,
            interruptible=True,
            goal_class="POINT_IN_TIME",
            goal_specific_inflation_rate=3.4,
            expected_return_rate=7.0,
            starting_balance=660_000.0,
            goal_subtype="VEHICLE",
        ),
        # --- Prod id=3 ---
        Goal(
            user_id=DEMO_USER,
            name="Wedding fund",
            goal_type="SAVINGS",
            target_amount=500_000.0,
            target_date=datetime.date(2027, 5, 8),
            priority=2,
            linked_layer=3,
            progress_cadence="MONTHLY",
            current_value=500_000.0,
            status="ON_TRACK",
            pyramid_id="W1",
            time_horizon="MULTI_YEAR",
            funding_mode="EVENT",
            activation_status="ACTIVE",
            allocation_priority=6,
            interruptible=True,
            goal_class="POINT_IN_TIME",
            goal_specific_inflation_rate=3.4,
            expected_return_rate=7.0,
            starting_balance=500_000.0,
            goal_subtype="WEDDING",
        ),
        # --- Prod id=4 (only row with chart_key in prod) ---
        Goal(
            user_id=DEMO_USER,
            name="Retirement corpus",
            goal_type="INVESTMENT",
            target_amount=50_000_000.0,
            target_date=datetime.date(2046, 5, 8),
            priority=1,
            linked_layer=3,
            chart_key="investment_net",
            progress_cadence="MONTHLY",
            current_value=None,
            status="ON_TRACK",
            pyramid_id="R1",
            time_horizon="DECADE",
            funding_mode="ACCUMULATION",
            activation_status="ACTIVE",
            allocation_priority=1,
            interruptible=True,
            goal_class="POINT_IN_TIME",
            goal_specific_inflation_rate=3.4,
            expected_return_rate=10.0,
            goal_subtype="RETIREMENT",
        ),
        # --- Prod id=5 ---
        Goal(
            user_id=DEMO_USER,
            name="House EMI",
            goal_type="DEBT_PAYOFF",
            target_amount=300_000.0,
            target_date=datetime.date(2046, 2, 8),
            priority=1,
            linked_layer=3,
            progress_cadence="MONTHLY",
            status="ON_TRACK",
            pyramid_id="E1",
            time_horizon="MONTHLY",
            funding_mode="CONSTRAINT",
            activation_status="ACTIVE",
            allocation_priority=3,
            interruptible=True,
            goal_class="RECURRING_CASH_FLOW",
            recurrence_amount=300_000.0,
            recurrence_frequency="MONTHLY",
            recurrence_start=datetime.date(2036, 5, 8),
            recurrence_end=datetime.date(2046, 2, 8),
            goal_specific_inflation_rate=3.4,
            expected_return_rate=0.0,
            goal_subtype="LOAN_PAYOFF",
        ),
        # --- Prod id=6 ---
        Goal(
            user_id=DEMO_USER,
            name="Annual vacation & travel",
            goal_type="SAVINGS",
            target_amount=600_000.0,
            target_date=datetime.date(2066, 5, 8),
            priority=4,
            linked_layer=3,
            progress_cadence="MONTHLY",
            status="ON_TRACK",
            pyramid_id="T1",
            time_horizon="ANNUAL",
            funding_mode="EVENT",
            activation_status="ACTIVE",
            allocation_priority=5,
            interruptible=True,
            goal_class="RECURRING_CASH_FLOW",
            recurrence_amount=600_000.0,
            recurrence_frequency="ANNUAL",
            recurrence_start=datetime.date(2026, 5, 8),
            recurrence_end=datetime.date(2066, 5, 8),
            goal_specific_inflation_rate=6.0,
            expected_return_rate=4.0,
            goal_subtype="TRAVEL",
        ),
        # --- Prod id=7 (informal kid savings; typed DEBT_PAYOFF in prod) ---
        Goal(
            user_id=DEMO_USER,
            name="Kid money",
            goal_type="DEBT_PAYOFF",
            target_amount=None,
            target_date=None,
            priority=3,
            linked_layer=3,
            progress_cadence="MONTHLY",
            status="ON_TRACK",
            notes="This is for the kid",
            pyramid_id="K1",
            activation_status="ACTIVE",
            interruptible=True,
            goal_class="RECURRING_CASH_FLOW",
            recurrence_amount=100_000.0,
            recurrence_frequency="MONTHLY",
            recurrence_start=datetime.date(2030, 7, 29),
            recurrence_end=datetime.date(2048, 7, 29),
            goal_subtype="CUSTOM",
        ),
        # --- Monthly spend caps (EXPENSE_LIMIT) — progress from txn sums vs category charts ---
        Goal(
            user_id=DEMO_USER,
            name="Dining out",
            goal_type="EXPENSE_LIMIT",
            target_amount=25_000.0,
            target_date=None,
            priority=4,
            linked_layer=3,
            linked_category="Food & Dining",
            chart_key="category:food_and_dining",
            progress_cadence="MONTHLY",
            status="ON_TRACK",
            pyramid_id="D1",
            time_horizon="MONTHLY",
            funding_mode="CONSTRAINT",
            activation_status="ACTIVE",
            allocation_priority=8,
            interruptible=True,
            goal_subtype="CUSTOM",
        ),
        Goal(
            user_id=DEMO_USER,
            name="Shopping & e-commerce",
            goal_type="EXPENSE_LIMIT",
            target_amount=15_000.0,
            target_date=None,
            priority=4,
            linked_layer=3,
            linked_category="Shopping & E-commerce",
            chart_key="category:shopping",
            progress_cadence="MONTHLY",
            status="ON_TRACK",
            pyramid_id="P1",
            time_horizon="MONTHLY",
            funding_mode="CONSTRAINT",
            activation_status="ACTIVE",
            allocation_priority=9,
            interruptible=True,
            goal_subtype="CUSTOM",
        ),
    ]
    for g in goals:
        session.add(g)
    session.commit()


def _seed_recurring(session: Session) -> None:
    today = datetime.date.today()
    patterns = [
        RecurringPattern(
            user_id=DEMO_USER,
            counterparty="Acme Corp",
            counterparty_category="Salary & Income",
            direction="INFLOW",
            expected_amount=185000.0,
            frequency="MONTHLY",
            day_of_month=1,
            last_seen_date=today.replace(day=1),
            is_active=True,
            is_confirmed=True,
            match_count=12,
            total_amount=12 * 185000.0,
        ),
        RecurringPattern(
            user_id=DEMO_USER,
            counterparty="Rent Payment",
            counterparty_category="Rent & Housing",
            direction="OUTFLOW",
            expected_amount=35000.0,
            frequency="MONTHLY",
            day_of_month=5,
            last_seen_date=today.replace(day=5),
            is_active=True,
            is_confirmed=False,
            match_count=12,
            total_amount=12 * 35000.0,
        ),
        RecurringPattern(
            user_id=DEMO_USER,
            counterparty="Netflix",
            counterparty_category="Mobile, OTT & Subscriptions",
            direction="OUTFLOW",
            expected_amount=649.0,
            frequency="MONTHLY",
            day_of_month=12,
            last_seen_date=today.replace(day=12),
            is_active=True,
            is_confirmed=True,
            match_count=12,
            total_amount=12 * 649.0,
        ),
    ]
    for p in patterns:
        session.add(p)
    session.commit()


def _seed_liability(session: Session) -> None:
    session.add(
        Liability(
            user_id=DEMO_USER,
            name="Home loan — HDFC",
            liability_type=LiabilityType.SECURED_LOAN.value,
            principal_outstanding=2_650_000.0,
            interest_rate=8.4,
            emi_amount=42_500.0,
            tenure_remaining_months=180,
            emi_start_date=datetime.date(2022, 6, 1),
            emi_end_date=datetime.date(2037, 6, 1),
            is_active=True,
        )
    )
    session.commit()


def _seed_chat(session: Session) -> None:
    sid = str(uuid.uuid4())
    session.add(
        ChatSession(
            id=sid,
            user_id=DEMO_USER,
            title="What changed this month?",
            is_archived=0,
        )
    )
    session.add(
        ChatMessage(
            session_id=sid,
            role="user",
            content="Give me a quick read on my spending vs last month.",
            created_at=datetime.datetime.now(datetime.UTC),
        )
    )
    session.add(
        ChatMessage(
            session_id=sid,
            role="assistant",
            content=(
                "Here is a **sample** reply for the demo build.\n\n"
                "- Dining is up slightly — worth a look at weekend Swiggy/Zomato.\n"
                "- Rent + EMI are steady (good — predictable cash burn).\n"
                "- You are still funding SIPs — nice consistency.\n\n"
                "Ask me to drill into any category when you try the live demo."
            ),
            created_at=datetime.datetime.now(datetime.UTC),
        )
    )
    session.commit()


def main() -> None:
    print(f"Writing demo seed to {SEED_PATH} …")
    init_db()
    with SQLiteSerializingSession(get_engine()) as session:
        _promote_local_install_to_demo(session)
        _seed_onboarding(session)
        _seed_classification_settings(session)
        pr_id = _seed_pipeline_run(session)
        _seed_transactions(session, pr_id)
        _seed_dashboard_chart_transactions(session, pr_id)
        _seed_prices(session, _all_demo_price_symbols())
        _seed_holdings_and_inv(session)
        _seed_goals(session)
        _seed_simulation_sandbox_preferences(session)
        _seed_recurring(session)
        _seed_liability(session)
        _seed_chat(session)
        merge_starter_pack_for_user(session, DEMO_USER)
        session.commit()

    print("Demo seed ready:", SEED_PATH)


if __name__ == "__main__":
    main()
