"""Existing Zitadel-backed accounts; identity creation remains with the provider."""

from uuid import UUID

from fastapi import APIRouter, Depends
from kitchen_admin_api.dependencies import DB
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import admin_people
from kitchen_core.admin_people_schemas import AdminUserOut, AdminUserUpdate
from kitchen_core.models import User
from kitchen_http.auth import require_admin
from sqlalchemy import or_, select

router = APIRouter(prefix="/users", tags=["admin-users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[AdminUserOut], operation_id="admin_list_users")
def list_users(session: DB, query: Listing, is_active: bool | None = None):
    statement = select(User)
    if is_active is not None:
        statement = statement.where(User.is_active.is_(is_active))
    if query.q:
        statement = statement.where(
            or_(
                User.name.icontains(query.q, autoescape=True),
                User.phone.icontains(query.q, autoescape=True),
            )
        )
    return paginate(
        session,
        statement,
        query,
        {"created_at": User.created_at, "name": User.name, "phone": User.phone},
    )


@router.get("/{user_id}", response_model=AdminUserOut, operation_id="admin_get_user")
def get_user(user_id: UUID, session: DB):
    return record(session, User, user_id)


@router.patch("/{user_id}", response_model=AdminUserOut, operation_id="admin_update_user")
def update_user(user_id: UUID, data: AdminUserUpdate, session: DB):
    return admin_people.update_user(session, user_id, data)


@router.post("/{user_id}/activate", response_model=AdminUserOut, operation_id="admin_activate_user")
def activate_user(user_id: UUID, session: DB):
    return admin_people.set_user_active(session, user_id, True)


@router.post(
    "/{user_id}/deactivate", response_model=AdminUserOut, operation_id="admin_deactivate_user"
)
def deactivate_user(user_id: UUID, session: DB):
    return admin_people.set_user_active(session, user_id, False)
