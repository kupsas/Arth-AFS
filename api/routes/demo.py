"""Public demo helpers — reset sandbox + status (no production impact)."""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from api.auth import get_current_user
from api.database import get_session
from api.demo import (
    DemoSessionManager,
    current_demo_browser_session_id,
    demo_chat_limit_total,
    demo_seed_path,
    demo_session_dir,
    is_demo_mode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["Demo"])


class DemoStatusResponse(BaseModel):
    demo_mode: bool
    chat_messages_remaining: int
    chat_messages_total: int
    session_id: str | None
    seed_exists: bool
    session_dir: str


def _require_demo() -> None:
    if not is_demo_mode():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo API is not enabled.",
        )


def _browser_session_id() -> str:
    sid = current_demo_browser_session_id()
    if not sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing demo session — refresh the page.",
        )
    return sid


@router.get("/status", response_model=DemoStatusResponse)
def demo_status(
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> DemoStatusResponse:
    """Return demo flags + remaining chat budget for the banner UI."""
    _require_demo()
    _ = session, current_user
    sid = current_demo_browser_session_id()
    seed = demo_seed_path()
    remaining = DemoSessionManager.chat_turns_remaining(sid) if sid else 0
    return DemoStatusResponse(
        demo_mode=True,
        chat_messages_remaining=remaining,
        chat_messages_total=demo_chat_limit_total(),
        session_id=sid,
        seed_exists=seed.is_file(),
        session_dir=str(demo_session_dir()),
    )


@router.post("/reset")
def demo_reset(
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete this visitor's SQLite copy and re-clone from the seed file."""
    _require_demo()
    _ = session, current_user
    sid = _browser_session_id()
    try:
        DemoSessionManager.reset_session(sid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        logger.error("Demo reset failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Demo seed database is missing on the server.",
        ) from e
    return {"status": "reset", "session_id": sid}


@router.get("/health")
def demo_health() -> dict:
    """Cheap probe for demo compose / load balancers (no DB)."""
    _require_demo()
    seed = demo_seed_path()
    ok = seed.is_file()
    return {
        "demo_mode": True,
        "seed_path": str(seed),
        "seed_ok": ok,
        "session_dir": str(demo_session_dir()),
        "time_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }
