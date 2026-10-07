"""Application profiles linked to existing Zitadel identities."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from kitchen_admin_api.dependencies import DB
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import admin_people
from kitchen_core.admin_people_schemas import AdminUserOut, AdminUserUpdate
from kitchen_core.errors import DomainError
from kitchen_core.models import User
from kitchen_http.auth import Admin, require_admin
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


@router.delete("/{user_id}", status_code=204, operation_id="admin_delete_user")
def delete_user(user_id: UUID, session: DB, admin: Admin):
    user = record(session, User, user_id)
    if user.oidc_subject == admin.subject and user.oidc_issuer == admin.issuer:
        raise DomainError(409, "current_user", "You cannot delete your signed-in account.")
    admin_people.delete_user(session, user_id)
    return Response(status_code=204)
