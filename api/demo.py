"""
Public demo mode: per-visitor ephemeral SQLite DB + rate limits.

Activated when ``ARTH_DEMO_MODE`` is truthy (``1`` / ``true`` / ``yes``).
Each browser gets a ``demo_session_id`` cookie (or ``arth_demo_sid`` on WebSocket URLs
when the cookie is not sent to the API host); the API copies the seed
database (``ARTH_DEMO_SEED_PATH`` or ``data/arth_demo_seed.db``) into a temp
file and serves all ORM traffic from that copy via :data:`api.database._demo_db_path`.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from pipeline.config import REPO_ROOT

logger = logging.getLogger(__name__)

# Cookie + identity (must match seeded ``arth_demo_seed.db`` rows).
DEMO_SESSION_COOKIE = "demo_session_id"
# When the dashboard opens WS directly to FastAPI (bypassing Next), some browsers send
# ``demo_session_id`` only for the page host (``localhost``) and not for ``127.0.0.1``.
# ``GET /api/chat/ws-ticket`` returns this value so the client can pass it on the WS URL.
ARTH_DEMO_SID_QUERY = "arth_demo_sid"
DEMO_USER_ID = "demo"

# Set together with ``_demo_db_path`` by :class:`DemoSessionASGIMiddleware`.
_demo_browser_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_demo_browser_session_id",
    default=None,
)


def current_demo_browser_session_id() -> str | None:
    """Visitor id (UUID) while handling an HTTP request or WebSocket in demo mode."""
    return _demo_browser_session_id.get()


def is_demo_mode() -> bool:
    raw = os.getenv("ARTH_DEMO_MODE", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def demo_chat_limit_total() -> int:
    try:
        return max(1, int(os.getenv("ARTH_DEMO_CHAT_LIMIT", "15").strip()))
    except ValueError:
        return 15


def demo_session_ttl_seconds() -> float:
    try:
        hours = float(os.getenv("ARTH_DEMO_SESSION_TTL_HOURS", "4").strip())
    except ValueError:
        hours = 4.0
    return max(300.0, hours * 3600.0)  # floor 5 minutes


def demo_session_dir() -> Path:
    raw = os.getenv("ARTH_DEMO_SESSION_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(tempfile.gettempdir()) / "arth_demo_sessions"


def demo_seed_path() -> Path:
    raw = os.getenv("ARTH_DEMO_SEED_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (REPO_ROOT / "data" / "arth_demo_seed.db").resolve()


_SESSION_ID_RE = re.compile(r"^[a-f0-9\-]{36}$")


def _safe_session_id(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if not _SESSION_ID_RE.match(s):
        return None
    return s


def _sqlite_wal_connect(dbapi_conn, _connection_record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


class DemoSessionManager:
    """Per-cookie SQLite file + engine cache + chat budget."""

    _engines: dict[str, Engine] = {}
    _chat_user_turns: dict[str, int] = {}

    @classmethod
    def ensure_session_db(cls, session_id: str) -> Path:
        """Return path to this visitor's SQLite file, copying the seed on first use."""
        sid = _safe_session_id(session_id) or str(uuid.uuid4())
        d = demo_session_dir()
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{sid}.db"
        seed = demo_seed_path()
        if not seed.is_file():
            raise FileNotFoundError(
                f"Demo seed database missing at {seed}. "
                "Run: python scripts/generate_demo_seed.py"
            )
        if not dest.is_file():
            shutil.copy2(seed, dest)
            logger.info("Demo: provisioned session DB for %s", sid)
        # Touch mtime for TTL sweeper.
        try:
            os.utime(dest, None)
        except OSError:
            pass
        return dest

    @classmethod
    def engine_for_path(cls, db_path: str) -> Engine:
        eng = cls._engines.get(db_path)
        if eng is not None:
            return eng
        eng = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        event.listens_for(eng, "connect")(_sqlite_wal_connect)
        cls._engines[db_path] = eng
        return eng

    @classmethod
    def dispose_engine(cls, db_path: str) -> None:
        eng = cls._engines.pop(db_path, None)
        if eng is not None:
            eng.dispose()

    @classmethod
    def reset_session(cls, session_id: str) -> Path:
        """Delete copy + chat budget; next ``ensure`` recopies seed."""
        sid = _safe_session_id(session_id)
        if not sid:
            raise ValueError("invalid session id")
        dest = demo_session_dir() / f"{sid}.db"
        p = str(dest.resolve())
        cls.dispose_engine(p)
        cls._chat_user_turns.pop(sid, None)
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            logger.warning("Demo: could not unlink %s", dest)
        return cls.ensure_session_db(sid)

    @classmethod
    def chat_turns_used(cls, session_id: str) -> int:
        sid = _safe_session_id(session_id) or session_id
        return int(cls._chat_user_turns.get(sid, 0))

    @classmethod
    def chat_turns_remaining(cls, session_id: str) -> int:
        return max(0, demo_chat_limit_total() - cls.chat_turns_used(session_id))

    @classmethod
    def record_chat_user_turn(cls, session_id: str) -> None:
        sid = _safe_session_id(session_id) or session_id
        cls._chat_user_turns[sid] = cls.chat_turns_used(sid) + 1

    @classmethod
    def cleanup_stale_files(cls) -> int:
        """Remove session DBs older than TTL. Returns files removed."""
        d = demo_session_dir()
        if not d.is_dir():
            return 0
        ttl = demo_session_ttl_seconds()
        now = time.time()
        removed = 0
        for f in d.glob("*.db"):
            try:
                age = now - f.stat().st_mtime
                if age <= ttl:
                    continue
            except OSError:
                continue
            key = str(f.resolve())
            cls.dispose_engine(key)
            # Strip chat counts for uuid filenames
            sid = f.stem
            cls._chat_user_turns.pop(sid, None)
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except OSError:
                logger.warning("Demo cleanup: could not remove %s", f)
        if removed:
            logger.info("Demo cleanup: removed %d stale session DB(s)", removed)
        return removed


def parse_cookie_header(scope: dict) -> dict[str, str]:
    """Parse Cookie header from ASGI scope into a dict (first value wins)."""
    out: dict[str, str] = {}
    for raw_key, raw_val in scope.get("headers") or []:
        if raw_key.decode("latin-1").lower() != "cookie":
            continue
        for part in raw_val.decode("latin-1").split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and k not in out:
                out[k] = v
    return out


def demo_browser_session_from_websocket_query(scope: dict) -> str | None:
    """Read ``ARTH_DEMO_SID_QUERY`` from a WebSocket scope (cookie fallback for demo DB binding)."""
    if scope.get("type") != "websocket":
        return None
    from urllib.parse import parse_qs

    raw = scope.get("query_string") or b""
    try:
        qs = parse_qs(raw.decode("latin-1"))
    except (UnicodeDecodeError, ValueError):
        return None
    vals = qs.get(ARTH_DEMO_SID_QUERY) or []
    if not vals:
        return None
    return _safe_session_id(vals[0])


class DemoSessionASGIMiddleware:
    """Bind ``api.database._demo_db_path`` for HTTP + WebSocket from ``demo_session_id``."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not is_demo_mode() or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        from api.database import _demo_db_path as db_path_var  # late import

        cookies = parse_cookie_header(scope)
        cookie_sid = _safe_session_id(cookies.get(DEMO_SESSION_COOKIE))
        query_sid = demo_browser_session_from_websocket_query(scope)
        # Prefer the HttpOnly cookie so a crafted WS URL cannot override an established session.
        sid = cookie_sid or query_sid
        new_cookie = sid is None
        if new_cookie:
            sid = str(uuid.uuid4())
        try:
            path = DemoSessionManager.ensure_session_db(sid)
        except FileNotFoundError as e:
            msg = str(e).encode("utf-8")
            if scope["type"] == "http":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [
                            (b"content-type", b"text/plain; charset=utf-8"),
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": msg,
                        "more_body": False,
                    }
                )
            return

        token = db_path_var.set(str(path.resolve()))
        sid_token = _demo_browser_session_id.set(sid)
        cookie_val = sid
        cookie_bytes = (
            f"{DEMO_SESSION_COOKIE}={cookie_val}; "
            "Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"
        ).encode("latin-1")

        def _inject_set_cookie(message: dict) -> dict:
            if not new_cookie:
                return message
            mtype = message.get("type")
            if mtype == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"set-cookie", cookie_bytes))
                return {**message, "headers": headers}
            if mtype == "websocket.accept":
                headers = list(message.get("headers") or [])
                headers.append((b"set-cookie", cookie_bytes))
                return {**message, "headers": headers}
            return message

        try:
            if new_cookie:

                async def send_wrapper(message):
                    await send(_inject_set_cookie(message))

                await self.app(scope, receive, send_wrapper)
            else:
                await self.app(scope, receive, send)
        finally:
            db_path_var.reset(token)
            _demo_browser_session_id.reset(sid_token)
