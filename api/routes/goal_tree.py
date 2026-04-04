"""
Goal hierarchy read API — Phase B.3

Mounted under ``/api/goals`` **before** the generic ``/{goal_id}`` routes in
``goals.py`` so paths like ``/tree`` are not parsed as integer IDs.

Enriches graph payloads with live progress from ``goal_evaluator.compute_progress``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.auth import get_current_user
from api.database import get_session
from api.models import Goal
from api.routes.goals import _goal_to_dict
from api.services.goal_evaluator import compute_progress
from api.services.goal_graph import (
    get_allocation_summary,
    get_ancestors,
    get_descendants,
    get_goal_tree,
    get_impact,
)

router = APIRouter()


def _enrich_goal_dicts(session: Session, goal_dicts: list[dict]) -> list[dict]:
    """Turn raw graph-layer goal dicts into the same shape as ``GET /api/goals/{id}``."""
    out: list[dict] = []
    for gd in goal_dicts:
        gid = gd.get("id")
        if gid is None:
            continue
        goal = session.get(Goal, gid)
        if goal is None:
            continue
        prog = compute_progress(goal, session)
        out.append(_goal_to_dict(goal, prog))
    return out


def _enrich_tree(session: Session, tree: dict) -> dict:
    keys = ("l1", "l2", "l3", "l4", "untiered")
    result = {k: _enrich_goal_dicts(session, tree[k]) for k in keys}
    result["links"] = tree["links"]
    return result


@router.get("/tree")
def goal_tree(
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> dict:
    raw = get_goal_tree(session, current_user)
    return _enrich_tree(session, raw)


@router.get("/allocation")
def goal_allocation(
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> dict:
    return get_allocation_summary(session, current_user)


@router.get("/{goal_id}/ancestors")
def goal_ancestors(
    goal_id: int,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    goals = get_ancestors(session, goal_id, current_user)
    return [_goal_to_dict(g, compute_progress(g, session)) for g in goals]


@router.get("/{goal_id}/descendants")
def goal_descendants(
    goal_id: int,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    goals = get_descendants(session, goal_id, current_user)
    return [_goal_to_dict(g, compute_progress(g, session)) for g in goals]


@router.get("/{goal_id}/impact")
def goal_impact(
    goal_id: int,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    rows = get_impact(session, goal_id, current_user)
    enriched = []
    for row in rows:
        gdict = row["goal"]
        gid = gdict.get("id")
        goal = session.get(Goal, gid) if gid is not None else None
        if goal is None:
            continue
        enriched.append({
            "goal": _goal_to_dict(goal, compute_progress(goal, session)),
            "direction": row["direction"],
            "distance": row["distance"],
            "link_type": row["link_type"],
        })
    return enriched
