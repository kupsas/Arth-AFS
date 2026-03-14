"""
FastAPI dependency injection providers.

The `get_session` dependency is the main one — it yields a SQLModel Session
per request.  Tests override this with an in-memory SQLite session so we
never touch the real database during automated runs.
"""

from __future__ import annotations

from api.database import get_session

# Re-export so routes can do: `from api.dependencies import get_session`
# and tests only need to override one symbol.
__all__ = ["get_session"]
