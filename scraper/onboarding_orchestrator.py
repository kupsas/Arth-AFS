"""
Chunk-based onboarding backfill (Track 2 Phase 2b).

Wraps the same parse → classify → DB path as :mod:`scraper.orchestrator`, but:

  * Pulls Gmail history for **one** ``source_key`` (e.g. ``hdfc_savings``).
  * Processes **N messages per HTTP request** so the API stays responsive.
  * Persists queue + counters in :class:`~api.models.OnboardingState.backfill_progress_json`.
  * Pauses when “classification unknowns” for that source exceed a threshold.
  * **Statement-first:** monthly/quarterly senders are drained before InstaAlerts; after
    statements, alert IDs are optionally filtered with :func:`scraper.gap_detector.filter_onboarding_alert_ids_after_statements`.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import and_, or_
from sqlmodel import Session, col, func, select

from api.models import Transaction

from api.services.classifier_runtime import effective_onboarding_unknown_threshold
from api.services.email_import_flow_log import EmailImportFlowLog
from scraper.config_loader import BankSendersConfig, get_bank_senders_config
from scraper.email_router import _normalise_sender
from scraper.email_parsers import build_email_parser_registry
from scraper.gap_detector import filter_onboarding_alert_ids_after_statements
from scraper.gmail_client import GmailClient
from scraper.orchestrator import _get_processed_ids, _process_email, _record_email

logger = logging.getLogger(__name__)

# How many Gmail messages to drain per API call (tune for UX vs request time).
DEFAULT_CHUNK_SIZE = 10

# When unknown rows (per source_key) reach this count, pause for classification UI.
UNKNOWN_THRESHOLD = int(os.environ.get("ONBOARDING_UNKNOWN_THRESHOLD", "20"))

# Default historical sweep — wide window; callers can override with after/before.
_DEFAULT_LOOKBACK_YEARS = 15


ProgressCallback = Callable[[dict[str, Any]], None]


def _today_plus_one() -> datetime.date:
    """Gmail ``before:`` is exclusive — use tomorrow UTC date as a practical upper bound."""
    return datetime.date.today() + datetime.timedelta(days=1)


def sender_emails_for_source_key(bank: BankSendersConfig, source_key: str) -> list[str]:
    """Return configured sender addresses that feed a given ``source_key``."""
    found: list[str] = []
    for sender_email, cfg in bank.items():
        for acct in cfg.get("accounts", {}).values():
            if acct.get("source_key") == source_key:
                found.append(sender_email)
                break
    return sorted(set(found))


def account_ids_for_source_key(bank: BankSendersConfig, source_key: str) -> list[str]:
    """Return bank ``account_id`` strings associated with ``source_key``."""
    ids: set[str] = set()
    for cfg in bank.values():
        for acct in cfg.get("accounts", {}).values():
            if acct.get("source_key") == source_key:
                ids.add(str(acct["account_id"]))
    return sorted(ids)


def _sender_cadence(cfg: dict[str, Any]) -> str:
    return str(cfg.get("expected_cadence") or "per_transaction").lower().strip()


def _partition_senders_for_source(
    bank: BankSendersConfig, source_key: str
) -> tuple[list[str], list[str]]:
    """Split senders for ``source_key`` into (statement_senders, alert_senders)."""
    senders = sender_emails_for_source_key(bank, source_key)
    stmt: list[str] = []
    alert: list[str] = []
    for s in senders:
        cfg = bank.get(s) or {}
        c = _sender_cadence(cfg)
        if c in ("monthly", "quarterly"):
            stmt.append(s)
        else:
            alert.append(s)
    return sorted(set(stmt)), sorted(set(alert))


def count_classification_unknowns(
    session: Session,
    *,
    user_id: str,
    source_key: str,
) -> int:
    """Count email-sourced rows for this source that still need automation fields.

    Mirrors the pipeline notion of “LLM work remaining”: missing ``txn_type``,
    counterparty taxonomy, UPI subtype (when channel is UPI), or OUTFLOW spend tag.
    """
    q = (
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.source_statement == source_key)
        .where(Transaction.source_type == "email")
        .where(
            or_(
                col(Transaction.txn_type).is_(None),
                col(Transaction.counterparty).is_(None),
                col(Transaction.counterparty_category).is_(None),
                and_(col(Transaction.channel) == "UPI", col(Transaction.upi_type).is_(None)),
                and_(
                    col(Transaction.direction) == "OUTFLOW",
                    col(Transaction.spend_category).is_(None),
                ),
            )
        )
    )
    return int(session.exec(q).one())


def list_classification_unknown_transactions(
    session: Session,
    *,
    user_id: str,
    source_key: str,
    limit: int = 200,
) -> list[Transaction]:
    """Return recent rows that still match :func:`count_classification_unknowns` (for batch UI)."""
    lim = max(1, min(int(limit), 500))
    q = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.source_statement == source_key)
        .where(Transaction.source_type == "email")
        .where(
            or_(
                col(Transaction.txn_type).is_(None),
                col(Transaction.counterparty).is_(None),
                col(Transaction.counterparty_category).is_(None),
                and_(col(Transaction.channel) == "UPI", col(Transaction.upi_type).is_(None)),
                and_(
                    col(Transaction.direction) == "OUTFLOW",
                    col(Transaction.spend_category).is_(None),
                ),
            )
        )
        .order_by(col(Transaction.txn_date).desc(), col(Transaction.id).desc())
        .limit(lim)
    )
    return list(session.exec(q).all())


@dataclass
class CollectedQueue:
    """Gmail IDs split for statement-first onboarding import."""

    statement_ids: list[str]
    alert_items_full: list[dict[str, str]]  # each: id, received_at (ISO)
    had_statement_ids_at_init: bool

    @property
    def total_planned(self) -> int:
        return len(self.statement_ids) + len(self.alert_items_full)


def _collect_pending_queue(
    client: GmailClient,
    bank: BankSendersConfig,
    source_key: str,
    *,
    after: datetime.date,
    before: datetime.date,
    session: Session,
    import_flow_log: EmailImportFlowLog | None = None,
) -> CollectedQueue:
    """Gather Gmail message IDs: statements (monthly/quarterly senders) then alert senders.

    Within each bucket, messages are **oldest first**.  Dedupes against ``processed_emails``.
    """
    stmt_senders, alert_senders = _partition_senders_for_source(bank, source_key)
    all_senders = sender_emails_for_source_key(bank, source_key)
    if not all_senders:
        raise ValueError(
            f"No configured bank sender maps to source_key={source_key!r}. "
            "Check scraper account mappings."
        )

    already_done = _get_processed_ids(session)
    after_s = after.strftime("%Y/%m/%d")
    before_s = before.strftime("%Y/%m/%d")

    stmt_msgs: dict[str, Any] = {}
    alert_msgs: dict[str, Any] = {}

    if import_flow_log:
        import_flow_log.write(
            "gmail_search_plan",
            f"source_key={source_key} statement_senders={len(stmt_senders)} "
            f"alert_senders={len(alert_senders)} after={after_s} before={before_s}",
        )

    for group_name, raw_list in (
        ("statement", stmt_senders),
        ("alert", alert_senders),
    ):
        for raw_sender in raw_list:
            query = f"from:{raw_sender} after:{after_s} before:{before_s}"
            batch = client.search_messages(
                query,
                paginate=True,
                max_results_per_page=100,
                max_total=None,
            )
            if import_flow_log:
                import_flow_log.write(
                    "gmail_search_done",
                    f"phase={group_name!r} sender={raw_sender!r} messages_in_date_range={len(batch)} "
                    f"query={query!r}",
                )
            bucket = stmt_msgs if group_name == "statement" else alert_msgs
            for m in batch:
                bucket[m.id] = m

    stmt_pending = sorted(stmt_msgs.values(), key=lambda m: m.received_at)
    alert_pending = sorted(alert_msgs.values(), key=lambda m: m.received_at)

    stmt_ids = [m.id for m in stmt_pending if m.id not in already_done]
    stmt_set = set(stmt_ids)
    alert_items_full = [
        {"id": m.id, "received_at": m.received_at.isoformat()}
        for m in alert_pending
        if m.id not in already_done and m.id not in stmt_set
    ]

    if import_flow_log:
        n_stmt = len(stmt_ids)
        n_alert = len(alert_items_full)
        import_flow_log.write(
            "gmail_dedupe",
            f"statement_pending={n_stmt} alert_pending_unfiltered={n_alert} "
            f"(skipped_already_in_ledger={len(stmt_msgs) + len(alert_msgs) - n_stmt - n_alert})",
        )

    return CollectedQueue(
        statement_ids=stmt_ids,
        alert_items_full=alert_items_full,
        had_statement_ids_at_init=len(stmt_ids) > 0,
    )


def _public_slice(src: dict[str, Any]) -> dict[str, Any]:
    """Strip underscore-prefixed internal keys before returning JSON to clients."""
    return {k: v for k, v in src.items() if not str(k).startswith("_")}


def _has_any_pending(src: dict[str, Any]) -> bool:
    if src.get("_pending_statement_ids"):
        return True
    if not src.get("_alerts_transitioned") and (src.get("_alert_items_full") or []):
        return True
    if src.get("_pending_alert_ids"):
        return True
    return False


def _ensure_alert_queue_ready(
    session: Session,
    user_id: str,
    source_key: str,
    bank: BankSendersConfig,
    src_state: dict[str, Any],
    *,
    import_flow_log: EmailImportFlowLog | None = None,
) -> None:
    if src_state.get("_alerts_transitioned"):
        return
    full = list(src_state.get("_alert_items_full") or [])
    had = bool(src_state.get("_had_statement_ids_at_init"))
    filtered_ids = filter_onboarding_alert_ids_after_statements(
        session,
        user_id,
        source_key,
        bank,
        full,
        had_statement_ids_at_init=had,
    )
    src_state["_pending_alert_ids"] = filtered_ids
    src_state["_alerts_transitioned"] = True
    if import_flow_log:
        import_flow_log.write(
            "gmail_alert_queue_after_gaps",
            f"alert_ids_after_gap_filter={len(filtered_ids)} (had_statement_phase={had})",
        )


def _active_drain_queue(src_state: dict[str, Any]) -> tuple[list[str], str]:
    """Return (ids_to_drain_head_slice, public_status_for_slice)."""
    stmt = list(src_state.get("_pending_statement_ids") or [])
    if stmt:
        return stmt, "processing_statements"
    alerts = list(src_state.get("_pending_alert_ids") or [])
    return alerts, "processing_alerts"


@dataclass
class OnboardingBackfillResult:
    """Return payload for one chunk step."""

    progress: dict[str, Any]

    @property
    def public_progress(self) -> dict[str, Any]:
        return _public_slice(self.progress)


def run_onboarding_backfill(
    *,
    session: Session,
    user_id: str,
    source_key: str,
    gmail_client: GmailClient,
    existing_progress: dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    after: datetime.date | None = None,
    before: datetime.date | None = None,
    resume_after_classification: bool = False,
    resume_from_pause: bool = False,
    unknown_threshold: int | None = None,
    progress_callback: ProgressCallback | None = None,
    import_flow_log: EmailImportFlowLog | None = None,
) -> OnboardingBackfillResult:
    """Advance onboarding backfill by **one chunk** (up to ``chunk_size`` emails).

    Args:
        session: Active SQLModel session (caller commits after persisting state).
        user_id: Authenticated Arth username (same as Gmail scraper mapping owner).
        source_key: Pipeline ``source_key`` e.g. ``hdfc_savings``.
        gmail_client: Authenticated Gmail client.
        existing_progress: Parsed ``backfill_progress_json[source_key]`` dict or ``{}``.
        chunk_size: Max messages to process this call.
        after / before: Gmail date window (inclusive ``after``, exclusive ``before``).
            Defaults to ~15 years through tomorrow when initializing a fresh run.
        resume_after_classification: When current status is ``needs_classification``,
            pass True to continue processing remaining queued IDs after the user
            fixed merchant rules (Phase 3 will set this from the classify endpoint).
        resume_from_pause: When status is ``paused``, pass True to clear the pause
            flag and continue chunk processing on the next call.
        unknown_threshold: Override env ``ONBOARDING_UNKNOWN_THRESHOLD``.
        progress_callback: Optional hook invoked after each email (tests / logging).
        import_flow_log: When provided (onboarding HTTP handler), append diagnostics to
            ``data/logs/email-import.log``.

    Returns:
        :class:`OnboardingBackfillResult` with updated progress dict (includes ``_``
        internal keys — strip with :meth:`OnboardingBackfillResult.public_progress`).
    """
    if unknown_threshold is not None:
        thresh = unknown_threshold
    else:
        thresh = effective_onboarding_unknown_threshold(session, user_id)
    bank = get_bank_senders_config(session, user_id)
    parser_registry = build_email_parser_registry(bank)

    src_state: dict[str, Any] = dict(existing_progress or {})
    status = str(src_state.get("status") or "idle")

    if import_flow_log:
        import_flow_log.write(
            "backfill_step",
            f"incoming_status={status!r} chunk_size={chunk_size} resume_after_classification={resume_after_classification} resume_from_pause={resume_from_pause}",
        )

    if status == "paused" and resume_from_pause:
        src_state = resume_backfill_state(src_state)
        status = str(src_state.get("status") or "processing")

    if status == "paused":
        if import_flow_log:
            import_flow_log.write("backfill_exit", "still paused — client must pass resume_from_pause=true")
        return OnboardingBackfillResult(
            progress={
                **src_state,
                "source": source_key,
                "status": "paused",
                "error_message": src_state.get("error_message"),
                "message": "Set resume_from_pause=true on the next POST to continue.",
            }
        )

    if status == "complete" and not _has_any_pending(src_state):
        unknowns_refresh = count_classification_unknowns(
            session, user_id=user_id, source_key=source_key
        )
        merged = {
            **src_state,
            "source": source_key,
            "status": "complete",
            "unknowns_pending": unknowns_refresh,
            "error_message": None,
        }
        if import_flow_log:
            import_flow_log.write("backfill_exit", f"already complete unknowns_pending={unknowns_refresh}")
        return OnboardingBackfillResult(progress=merged)

    if status == "needs_classification" and not resume_after_classification:
        unknowns = int(src_state.get("unknowns_pending") or 0)
        if import_flow_log:
            import_flow_log.write(
                "backfill_exit",
                f"waiting for classification UI unknowns_pending={unknowns} (pass resume_after_classification to continue)",
            )
        return OnboardingBackfillResult(
            progress={
                **src_state,
                "source": source_key,
                "status": "needs_classification",
                "unknowns_pending": unknowns,
                "error_message": src_state.get("error_message"),
                "message": "Pass resume_after_classification=true after resolving unknowns.",
            }
        )

    # Transition out of classification gate.
    if status == "needs_classification" and resume_after_classification:
        src_state["status"] = "processing_statements"
        stmt0 = list(src_state.get("_pending_statement_ids") or [])
        if not stmt0:
            _ensure_alert_queue_ready(
                session, user_id, source_key, bank, src_state, import_flow_log=import_flow_log
            )
            al0 = list(src_state.get("_pending_alert_ids") or [])
            src_state["status"] = "processing_alerts" if al0 else "processing"

    after_date = after
    before_date = before
    if after_date is None:
        after_date = datetime.date.today() - datetime.timedelta(days=365 * _DEFAULT_LOOKBACK_YEARS)
    if before_date is None:
        before_date = _today_plus_one()

    # Initialise queue on first chunk (do not rebuild after a finished run — caller clears JSON).
    need_init = not _has_any_pending(src_state) and status in ("idle", "error")
    if need_init:
        try:
            q = _collect_pending_queue(
                gmail_client,
                bank,
                source_key,
                after=after_date,
                before=before_date,
                session=session,
                import_flow_log=import_flow_log,
            )
        except Exception as exc:
            logger.exception("Failed to list Gmail messages for %s", source_key)
            if import_flow_log:
                import_flow_log.write("error", f"gmail list/build queue failed: {exc!r}")
            return OnboardingBackfillResult(
                progress={
                    "source": source_key,
                    "status": "error",
                    "emails_found": 0,
                    "emails_processed": 0,
                    "transactions_parsed": 0,
                    "unknowns_pending": 0,
                    "error_message": str(exc),
                    "current_phase": None,
                }
            )

        emails_found = q.total_planned
        if import_flow_log:
            import_flow_log.write(
                "gmail_queue_built",
                f"statements={len(q.statement_ids)} alerts_unfiltered={len(q.alert_items_full)} total_planned={emails_found}",
            )
        src_state.update(
            {
                "status": "processing_statements" if q.statement_ids else "processing_alerts",
                "current_phase": "statements" if q.statement_ids else "alerts",
                "emails_found": emails_found,
                "emails_processed": 0,
                "transactions_parsed": 0,
                "unknowns_pending": 0,
                "error_message": None,
                "_pending_statement_ids": list(q.statement_ids),
                "_alert_items_full": list(q.alert_items_full),
                "_had_statement_ids_at_init": q.had_statement_ids_at_init,
                "_alerts_transitioned": False,
                "_pending_alert_ids": [],
                "_after": after_date.isoformat(),
                "_before": before_date.isoformat(),
                "_initial_pending_total": emails_found,
            }
        )
        if not q.statement_ids:
            _ensure_alert_queue_ready(
                session, user_id, source_key, bank, src_state, import_flow_log=import_flow_log
            )
            al = list(src_state.get("_pending_alert_ids") or [])
            src_state["status"] = "processing_alerts" if al else "processing"
            src_state["current_phase"] = "alerts" if al else None

    # Prepare alert queue once statement tier is drained.
    if not (src_state.get("_pending_statement_ids") or []):
        _ensure_alert_queue_ready(
            session, user_id, source_key, bank, src_state, import_flow_log=import_flow_log
        )

    active_q, pub_status = _active_drain_queue(src_state)
    initial_total = int(src_state.get("_initial_pending_total") or len(active_q))

    if not active_q:
        unknowns = count_classification_unknowns(session, user_id=user_id, source_key=source_key)
        done = int(src_state.get("emails_processed") or 0)
        src_state.update(
            {
                "source": source_key,
                "status": "complete",
                "emails_found": max(initial_total, done),
                "emails_processed": done,
                "transactions_parsed": src_state.get("transactions_parsed", 0),
                "unknowns_pending": unknowns,
                "error_message": None,
                "current_phase": None,
            }
        )
        for k in (
            "_pending_statement_ids",
            "_pending_alert_ids",
            "_alert_items_full",
            "_alerts_transitioned",
            "_had_statement_ids_at_init",
        ):
            src_state.pop(k, None)
        if import_flow_log:
            import_flow_log.write(
                "backfill_exit",
                f"queue empty — status=complete unknowns_pending={unknowns}",
            )
        return OnboardingBackfillResult(progress=src_state)

    chunk_n = max(1, chunk_size)
    chunk = active_q[:chunk_n]
    rest = active_q[chunk_n:]

    tx_total = int(src_state.get("transactions_parsed") or 0)
    emails_done = int(src_state.get("emails_processed") or 0)

    src_state["status"] = pub_status
    src_state["current_phase"] = "statements" if pub_status == "processing_statements" else "alerts"

    for msg_id in chunk:
        try:
            if import_flow_log:
                import_flow_log.write(
                    "chunk_item",
                    f"fetch id={msg_id} (email {emails_done + 1} of this chunk, {len(chunk)} in batch) phase={pub_status!r}",
                )
            msg = gmail_client.fetch_message_by_id(msg_id)
            status_result, txn_count = _process_email(
                msg,
                client=gmail_client,
                session=session,
                parser_registry=parser_registry,
                user_id=user_id,
                import_flow_log=import_flow_log,
            )
            sender_norm = _normalise_sender(msg.sender)
            _record_email(
                session,
                msg,
                sender=sender_norm,
                status=status_result,
                txn_count=txn_count,
            )
            emails_done += 1
            if status_result == "processed":
                tx_total += txn_count

            slice_pub = _public_slice(
                {
                    **src_state,
                    "source": source_key,
                    "status": pub_status,
                    "emails_found": initial_total,
                    "emails_processed": emails_done,
                    "transactions_parsed": tx_total,
                    "current_phase": src_state.get("current_phase"),
                }
            )
            if progress_callback:
                progress_callback(slice_pub)

        except Exception as exc:
            logger.exception("Onboarding backfill failed on message %s", msg_id)
            if import_flow_log:
                import_flow_log.write("error", f"message_id={msg_id} {exc!r}")
            err_msg = str(exc)
            try:
                msg = gmail_client.fetch_message_by_id(msg_id)
                sender_norm = _normalise_sender(msg.sender)
                _record_email(
                    session,
                    msg,
                    sender=sender_norm,
                    status="failed",
                    error_message=err_msg,
                )
            except Exception:
                logger.warning("Could not record failed ProcessedEmail for %s", msg_id)

            emails_done += 1
            if pub_status == "processing_statements":
                src_state["_pending_statement_ids"] = rest
            else:
                src_state["_pending_alert_ids"] = rest
            src_state.update(
                {
                    "status": "error",
                    "emails_found": initial_total,
                    "emails_processed": emails_done,
                    "transactions_parsed": tx_total,
                    "unknowns_pending": count_classification_unknowns(
                        session, user_id=user_id, source_key=source_key
                    ),
                    "error_message": err_msg,
                }
            )
            return OnboardingBackfillResult(progress=src_state)

    if pub_status == "processing_statements":
        src_state["_pending_statement_ids"] = rest
    else:
        src_state["_pending_alert_ids"] = rest

    src_state["emails_processed"] = emails_done
    src_state["transactions_parsed"] = tx_total
    src_state["emails_found"] = initial_total

    unknowns = count_classification_unknowns(session, user_id=user_id, source_key=source_key)
    src_state["unknowns_pending"] = unknowns

    stmt_rest = list(src_state.get("_pending_statement_ids") or [])
    if not stmt_rest:
        _ensure_alert_queue_ready(
            session, user_id, source_key, bank, src_state, import_flow_log=import_flow_log
        )
    alert_rest = list(src_state.get("_pending_alert_ids") or [])

    if unknowns >= thresh:
        src_state["status"] = "needs_classification"
        if not stmt_rest and not alert_rest:
            for k in (
                "_pending_statement_ids",
                "_pending_alert_ids",
                "_alert_items_full",
                "_alerts_transitioned",
                "_had_statement_ids_at_init",
            ):
                src_state.pop(k, None)
    elif not stmt_rest and not alert_rest:
        src_state["status"] = "complete"
        src_state["current_phase"] = None
        for k in (
            "_pending_statement_ids",
            "_pending_alert_ids",
            "_alert_items_full",
            "_alerts_transitioned",
            "_had_statement_ids_at_init",
        ):
            src_state.pop(k, None)
    else:
        _next_ids, pub2 = _active_drain_queue(src_state)
        src_state["status"] = pub2
        src_state["current_phase"] = (
            "statements"
            if pub2 == "processing_statements"
            else ("alerts" if pub2 == "processing_alerts" else None)
        )

    src_state["source"] = source_key
    src_state["error_message"] = None
    if import_flow_log:
        import_flow_log.write(
            "backfill_step_done",
            f"status={src_state.get('status')!r} emails_processed={src_state.get('emails_processed')} "
            f"txns={src_state.get('transactions_parsed')} unknowns={unknowns} "
            f"stmt_remaining={len(stmt_rest)} alert_remaining={len(alert_rest)}",
        )
    return OnboardingBackfillResult(progress=src_state)


def pause_backfill_state(src: dict[str, Any]) -> dict[str, Any]:
    """Mark a single-source progress blob as paused (internal helper)."""
    out = dict(src or {})
    if out.get("status") in ("processing", "processing_statements", "processing_alerts"):
        out["status"] = "paused"
    return out


def resume_backfill_state(src: dict[str, Any]) -> dict[str, Any]:
    """Clear paused flag so the next POST processes chunks again."""
    out = dict(src or {})
    if out.get("status") == "paused":
        stmt = list(out.get("_pending_statement_ids") or [])
        if stmt:
            out["status"] = "processing_statements"
        elif out.get("_pending_alert_ids"):
            out["status"] = "processing_alerts"
        else:
            out["status"] = "processing"
    return out
