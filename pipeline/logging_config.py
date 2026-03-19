"""
Shared logging configuration for the Arth pipeline, API, and scraper.

Call ``setup_logging()`` once at application startup (e.g. in api/main.py's
lifespan, or at the top of pipeline/run.py's main()).  Every other module
just does ``logger = logging.getLogger(__name__)`` — no further config needed.

Output behaviour:
  - INFO and above → stdout (colourless, human-readable)
  - DEBUG and above → data/logs/arth.log  (rotating, 5MB × 3 backups)

Format:  2026-03-19 14:30:01 [INFO ] pipeline.run: Stage 1: parsing hdfc_savings
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

# Single shared formatter so stdout and file look identical (makes copy-pasting
# a log line from the terminal into the file — or vice versa — unambiguous).
_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Where on-disk logs land.  Relative to the repo root, not this file's location.
_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
_LOG_FILE = _LOG_DIR / "arth.log"

# Third-party libraries tend to be chatty at DEBUG level.  We silence them at
# WARNING so our own pipeline messages aren't drowned out in the log file.
_NOISY_LIBS = [
    "httpx",
    "httpcore",
    "urllib3",
    "google",
    "anthropic",
    "openai",
    "apscheduler",
    "multipart",
]


def setup_logging(*, log_level: int = logging.INFO) -> None:
    """Configure the root logger with a stdout handler and a rotating file handler.

    Idempotent: calling this more than once (e.g. in tests) is safe — it checks
    whether handlers are already attached before adding new ones.

    Args:
        log_level: The minimum level emitted to stdout.  The file handler always
                   captures DEBUG and above so nothing is lost permanently.
    """
    root = logging.getLogger()

    # Guard: don't add duplicate handlers if called a second time.
    if root.handlers:
        return

    # The root logger must be set to the lowest level we care about anywhere;
    # individual handlers then filter further.  DEBUG lets the file handler
    # capture everything even when stdout is set to INFO.
    root.setLevel(logging.DEBUG)

    # ── Stdout handler (INFO+) ────────────────────────────────────────────
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(_FORMATTER)
    root.addHandler(stream_handler)

    # ── Rotating file handler (DEBUG+) ────────────────────────────────────
    # maxBytes=5MB, backupCount=3 → keeps at most ~20MB of logs on disk.
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_FORMATTER)
    root.addHandler(file_handler)

    # ── Silence noisy third-party libs ───────────────────────────────────
    for lib in _NOISY_LIBS:
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.getLogger(__name__).debug("Logging initialised — file: %s", _LOG_FILE)
