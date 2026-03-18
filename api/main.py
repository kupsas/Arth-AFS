"""
FastAPI application for Arth — personal finance transaction API.

Run with:
    uvicorn api.main:app --reload --port 8000

Swagger docs at http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import init_db
from api.routes import metrics, pipeline, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure DB tables exist.  Shutdown: nothing special (yet)."""
    init_db()
    yield


app = FastAPI(
    title="Arth API",
    description="Personal finance transaction pipeline & query API",
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the future Next.js dashboard and Swagger UI
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev server (Phase 3)
        "http://localhost:8000",   # Swagger UI served by FastAPI itself
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["Metrics"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
def health_check():
    """Simple liveness probe — returns 200 if the server is up."""
    return {"status": "ok"}
