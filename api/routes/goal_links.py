"""
GoalLink CRUD — Phase B.3

Parent → child edges in the goal pyramid. Cycle detection runs before insert
(see ``goal_graph.validate_link``). Duplicate (parent, child, link_type) hits
the DB unique index and is turned into HTTP 400.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.auth import get_current_user
from api.database import get_session
from api.models import GoalLink
from api.services.goal_graph import validate_link

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_LINK_TYPES = frozenset({"DECOMPOSES_INTO", "DEPENDS_ON", "CONTRIBUTES_TO"})


class GoalLinkCreate(BaseModel):
    parent_goal_id: int
    child_goal_id: int
    link_type: str = Field(max_length=32)
    description: str | None = Field(default=None, max_length=500)
    contribution_amount: float | None = Field(default=None, ge=0)


class GoalLinkPatch(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    contribution_amount: float | None = Field(default=None, ge=0)


def _link_to_api_dict(link: GoalLink) -> dict:
    return {
        "id": link.id,
        "parent_goal_id": link.parent_goal_id,
        "child_goal_id": link.child_goal_id,
        "link_type": link.link_type,
        "description": link.description,
        "contribution_amount": link.contribution_amount,
        "user_id": link.user_id,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.post("", status_code=201)
def create_goal_link(
    body: GoalLinkCreate,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> dict:
    if body.link_type not in _VALID_LINK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid link_type: {body.link_type!r}. Use one of {sorted(_VALID_LINK_TYPES)}.",
        )

    validate_link(session, body.parent_goal_id, body.child_goal_id, current_user)

    row = GoalLink(
        parent_goal_id=body.parent_goal_id,
        child_goal_id=body.child_goal_id,
        link_type=body.link_type,
        description=body.description,
        contribution_amount=body.contribution_amount,
        user_id=current_user,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        logger.info("GoalLink insert failed integrity: %s", e)
        raise HTTPException(
            status_code=400,
            detail="A link with the same parent, child, and link_type already exists.",
        ) from e
    session.refresh(row)
    return _link_to_api_dict(row)


@router.get("")
def list_goal_links(
    parent_goal_id: int | None = Query(None),
    child_goal_id: int | None = Query(None),
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    q = select(GoalLink).where(GoalLink.user_id == current_user)
    if parent_goal_id is not None:
        q = q.where(GoalLink.parent_goal_id == parent_goal_id)
    if child_goal_id is not None:
        q = q.where(GoalLink.child_goal_id == child_goal_id)
    q = q.order_by(col(GoalLink.id))
    rows = session.exec(q).all()
    return [_link_to_api_dict(r) for r in rows]


@router.patch("/{link_id}")
def patch_goal_link(
    link_id: int,
    body: GoalLinkPatch,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> dict:
    link = session.get(GoalLink, link_id)
    if not link or link.user_id != current_user:
        raise HTTPException(status_code=404, detail=f"Goal link {link_id} not found")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return _link_to_api_dict(link)

    for k, v in data.items():
        setattr(link, k, v)
    session.add(link)
    session.commit()
    session.refresh(link)
    return _link_to_api_dict(link)


@router.delete("/{link_id}", status_code=204)
def delete_goal_link(
    link_id: int,
    *,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
) -> None:
    link = session.get(GoalLink, link_id)
    if not link or link.user_id != current_user:
        raise HTTPException(status_code=404, detail=f"Goal link {link_id} not found")
    session.delete(link)
    session.commit()
