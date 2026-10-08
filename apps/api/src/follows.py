"""Kitchen following endpoints for the signed-in account."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from kitchen_core import follows
from kitchen_core.catalog_schemas import (
    FollowedKitchenOut,
    FollowedKitchenPage,
    KitchenFollowRequest,
)
from kitchen_core.db import get_session
from kitchen_core.models import User
from kitchen_http.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(tags=["kitchen follows"])
DB = Annotated[Session, Depends(get_session, scope="function")]
Resident = Annotated[User, Depends(require_user)]


@router.post("/kitchens/{kitchen_id}/follow", response_model=FollowedKitchenOut)
def follow(kitchen_id: UUID, session: DB, user: Resident, data: KitchenFollowRequest | None = None):
    return follows.follow_kitchen(session, user.id, kitchen_id, data)


@router.delete("/kitchens/{kitchen_id}/follow", status_code=204)
def unfollow(kitchen_id: UUID, session: DB, user: Resident):
    follows.unfollow_kitchen(session, user.id, kitchen_id)
    return Response(status_code=204)


@router.get("/me/followed-kitchens", response_model=FollowedKitchenPage)
def my_followed_kitchens(
    session: DB,
    user: Resident,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return follows.followed_kitchens(session, user.id, limit, offset)
