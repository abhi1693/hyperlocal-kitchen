"""Society and resident administration, protected at each resource router."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from kitchen_admin_api.dependencies import DB
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import admin_people, catalog
from kitchen_core.admin_people_schemas import (
    MembershipCreate,
    MembershipUpdate,
    TowerUpdate,
)
from kitchen_core.catalog_schemas import (
    MembershipAdminOut,
    SocietyCreate,
    SocietyOut,
    SocietyUpdate,
    TowerCreate,
    TowerOut,
)
from kitchen_core.models import Membership, Society, Tower, User
from kitchen_http.auth import require_admin
from sqlalchemy import or_, select

societies_router = APIRouter(
    prefix="/societies", tags=["admin-societies"], dependencies=[Depends(require_admin)]
)
towers_router = APIRouter(
    prefix="/towers", tags=["admin-towers"], dependencies=[Depends(require_admin)]
)
memberships_router = APIRouter(
    prefix="/memberships", tags=["admin-memberships"], dependencies=[Depends(require_admin)]
)


@societies_router.get("", response_model=Page[SocietyOut], operation_id="admin_list_societies")
def list_societies(
    session: DB, query: Listing, status: Literal["draft", "active", "paused"] | None = None
):
    statement = select(Society)
    if query.q:
        statement = statement.where(
            or_(
                Society.name.icontains(query.q, autoescape=True),
                Society.city.icontains(query.q, autoescape=True),
            )
        )
    if status:
        statement = statement.where(Society.status == status)
    page = paginate(
        session,
        statement,
        query,
        {"created_at": Society.created_at, "name": Society.name, "city": Society.city},
    )
    page["items"] = [catalog.society_view(session, society) for society in page["items"]]
    return page


@societies_router.post(
    "", response_model=SocietyOut, status_code=201, operation_id="admin_create_society"
)
def create_society(data: SocietyCreate, session: DB):
    return catalog.create_society(session, data)


@societies_router.get("/{society_id}", response_model=SocietyOut, operation_id="admin_get_society")
def get_society(society_id: UUID, session: DB):
    return catalog.society_view(session, record(session, Society, society_id))


@societies_router.patch(
    "/{society_id}", response_model=SocietyOut, operation_id="admin_update_society"
)
def update_society(society_id: UUID, data: SocietyUpdate, session: DB):
    record(session, Society, society_id, lock=True)
    return catalog.update_society(session, society_id, data)


@societies_router.delete(
    "/{society_id}", status_code=204, response_class=Response, operation_id="admin_delete_society"
)
def delete_society(society_id: UUID, session: DB):
    admin_people.delete_society(session, society_id)
    return Response(status_code=204)


@societies_router.post(
    "/{society_id}/activate", response_model=SocietyOut, operation_id="admin_activate_society"
)
def activate_society(society_id: UUID, session: DB):
    record(session, Society, society_id, lock=True)
    return catalog.set_society_status(session, society_id, "active")


@societies_router.post(
    "/{society_id}/pause", response_model=SocietyOut, operation_id="admin_pause_society"
)
def pause_society(society_id: UUID, session: DB):
    record(session, Society, society_id, lock=True)
    return catalog.set_society_status(session, society_id, "paused")


def tower_page(session, query, society_id):
    statement = select(Tower)
    if society_id:
        record(session, Society, society_id)
        statement = statement.where(Tower.society_id == society_id)
    if query.q:
        statement = statement.where(Tower.name.icontains(query.q, autoescape=True))
    page = paginate(session, statement, query, {"created_at": Tower.created_at, "name": Tower.name})
    page["items"] = [admin_people.tower_view(tower) for tower in page["items"]]
    return page


@societies_router.get(
    "/{society_id}/towers", response_model=Page[TowerOut], operation_id="admin_list_society_towers"
)
def list_society_towers(society_id: UUID, session: DB, query: Listing):
    return tower_page(session, query, society_id)


@societies_router.post(
    "/{society_id}/towers",
    response_model=TowerOut,
    status_code=201,
    operation_id="admin_create_tower",
)
def create_tower(society_id: UUID, data: TowerCreate, session: DB):
    record(session, Society, society_id, lock=True)
    return catalog.add_tower(session, society_id, data)


@towers_router.get("", response_model=Page[TowerOut], operation_id="admin_list_towers")
def list_towers(session: DB, query: Listing, society_id: UUID | None = None):
    return tower_page(session, query, society_id)


@towers_router.get("/{tower_id}", response_model=TowerOut, operation_id="admin_get_tower")
def get_tower(tower_id: UUID, session: DB):
    return admin_people.tower_view(record(session, Tower, tower_id))


@towers_router.patch("/{tower_id}", response_model=TowerOut, operation_id="admin_update_tower")
def update_tower(tower_id: UUID, data: TowerUpdate, session: DB):
    return admin_people.update_tower(session, tower_id, data)


@towers_router.delete(
    "/{tower_id}", status_code=204, response_class=Response, operation_id="admin_delete_tower"
)
def delete_tower(tower_id: UUID, session: DB):
    admin_people.delete_tower(session, tower_id)
    return Response(status_code=204)


@memberships_router.get(
    "", response_model=Page[MembershipAdminOut], operation_id="admin_list_memberships"
)
def list_memberships(
    session: DB,
    query: Listing,
    society_id: UUID | None = None,
    user_id: UUID | None = None,
    status: Literal["active", "suspended"] | None = None,
):
    statement = (
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .join(Society, Society.id == Membership.society_id)
        .join(Tower, Tower.id == Membership.tower_id)
    )
    if society_id:
        record(session, Society, society_id)
        statement = statement.where(Membership.society_id == society_id)
    if user_id:
        record(session, User, user_id)
        statement = statement.where(Membership.user_id == user_id)
    if status:
        statement = statement.where(Membership.status == status)
    if query.q:
        statement = statement.where(
            or_(
                User.name.icontains(query.q, autoescape=True),
                User.phone.icontains(query.q, autoescape=True),
                Society.name.icontains(query.q, autoescape=True),
                Tower.name.icontains(query.q, autoescape=True),
                Membership.flat.icontains(query.q, autoescape=True),
            )
        )
    page = paginate(
        session,
        statement,
        query,
        {"created_at": Membership.created_at, "flat": Membership.flat, "name": User.name},
    )
    page["items"] = [
        catalog.membership_view(session, member, admin=True) for member in page["items"]
    ]
    return page


@memberships_router.post(
    "", response_model=MembershipAdminOut, status_code=201, operation_id="admin_create_membership"
)
def create_membership(data: MembershipCreate, session: DB):
    return admin_people.create_membership(session, data)


@memberships_router.get(
    "/{membership_id}", response_model=MembershipAdminOut, operation_id="admin_get_membership"
)
def get_membership(membership_id: UUID, session: DB):
    return catalog.membership_view(session, record(session, Membership, membership_id), admin=True)


@memberships_router.patch(
    "/{membership_id}", response_model=MembershipAdminOut, operation_id="admin_update_membership"
)
def update_membership(membership_id: UUID, data: MembershipUpdate, session: DB):
    return admin_people.update_membership(session, membership_id, data)


@memberships_router.delete(
    "/{membership_id}",
    status_code=204,
    response_class=Response,
    operation_id="admin_delete_membership",
)
def delete_membership(membership_id: UUID, session: DB):
    admin_people.delete_membership(session, membership_id)
    return Response(status_code=204)


@memberships_router.post(
    "/{membership_id}/activate",
    response_model=MembershipAdminOut,
    operation_id="admin_activate_membership",
)
def activate_membership(membership_id: UUID, session: DB):
    admin_people._locked_membership(session, membership_id)
    return catalog.set_membership_status(session, membership_id, "active")


@memberships_router.post(
    "/{membership_id}/suspend",
    response_model=MembershipAdminOut,
    operation_id="admin_suspend_membership",
)
def suspend_membership(membership_id: UUID, session: DB):
    admin_people._locked_membership(session, membership_id)
    return catalog.set_membership_status(session, membership_id, "suspended")


router = APIRouter()
for resource_router in (societies_router, towers_router, memberships_router):
    router.include_router(resource_router)
