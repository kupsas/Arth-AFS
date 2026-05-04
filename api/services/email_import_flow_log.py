"""
Append-only diagnostics for the onboarding **Import from email** flow.

Writes human-readable lines to ``data/logs/email-import.log`` (gitignored).
Each POST to ``POST /api/onboarding/backfill/{source}`` gets a short
``request_id`` so you can grep one chunk run while the UI polls.

This is intentionally separate from Python's ``logging`` module so you always
have a single file to tail while debugging stuck progress bars.
"""

from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Repo root: api/services/ -> parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "data" / "logs"
DEFAULT_LOG_PATH = LOG_DIR / "email-import.log"

_write_lock = threading.Lock()


class EmailImportFlowLog:
    """One instance per HTTP request; correlates lines with ``request_id``."""

    def __init__(
        self,
        *,
        request_id: str,
        user_id: str,
        source_key: str,
        path: Path | None = None,
    ) -> None:
        self.request_id = request_id
        self.user_id = user_id
        self.source_key = source_key
        self._path = path or DEFAULT_LOG_PATH

    def write(self, event: str, detail: str = "") -> None:
        """Append one tab-separated line. Never raises to callers (import must continue)."""
        # UTC timestamp so logs line up across machines and log viewers.
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{ts}\t{self.request_id}\t{self.user_id}\t{self.source_key}\t{event}"
        if detail:
            # Single line only — strip newlines so one event stays one row.
            safe = detail.replace("\n", " ").replace("\r", " ")
            line += f"\t{safe}"
        line += "\n"
        try:
            with _write_lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
        except OSError as exc:
            logger.warning("email import flow log write failed: %s", exc)
