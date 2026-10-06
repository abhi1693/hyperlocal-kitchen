from typing import Annotated

from fastapi import APIRouter, Depends
from kitchen_core.auth_schemas import UserIdentity
from kitchen_core.catalog_schemas import StrictRequest
from kitchen_core.db import get_session
from kitchen_core.models import User
from kitchen_http.auth import require_user
from pydantic import Field
from sqlalchemy.orm import Session

router = APIRouter(tags=["Profile"])


class ProfileUpdate(StrictRequest):
    name: str = Field(min_length=1, max_length=120)


@router.patch("/me", response_model=UserIdentity)
def update_profile(
    body: ProfileUpdate,
    session: Annotated[Session, Depends(get_session, scope="function")],
    user: Annotated[User, Depends(require_user)],
):
    user.name = body.name
    session.flush()
    return UserIdentity.model_validate(user)
