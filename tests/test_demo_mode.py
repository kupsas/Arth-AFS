"""Sanity checks for demo-only helpers (no full app import — ``api.main`` reads env at import time)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routes import demo as demo_routes


def test_require_demo_raises_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTH_DEMO_MODE", raising=False)
    with pytest.raises(HTTPException) as exc:
        demo_routes._require_demo()
    assert exc.value.status_code == 404


def test_require_demo_ok_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTH_DEMO_MODE", "1")
    demo_routes._require_demo()  # no exception


def test_demo_browser_session_from_websocket_query_ok() -> None:
    from api.demo import ARTH_DEMO_SID_QUERY, demo_browser_session_from_websocket_query

    sid = "550e8400-e29b-41d4-a716-446655440000"
    scope = {
        "type": "websocket",
        "query_string": f"ticket=x&{ARTH_DEMO_SID_QUERY}={sid}".encode("ascii"),
    }
    assert demo_browser_session_from_websocket_query(scope) == sid


def test_demo_browser_session_from_websocket_query_rejects_non_uuid() -> None:
    from api.demo import demo_browser_session_from_websocket_query

    scope = {
        "type": "websocket",
        "query_string": b"arth_demo_sid=not-a-uuid",
    }
    assert demo_browser_session_from_websocket_query(scope) is None


def test_demo_browser_session_from_websocket_query_http_scope() -> None:
    from api.demo import demo_browser_session_from_websocket_query

    assert demo_browser_session_from_websocket_query({"type": "http"}) is None
