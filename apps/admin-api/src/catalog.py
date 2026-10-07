"""Community and resident administration, protected at each resource router."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from kitchen_admin_api.dependencies import DB
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import admin_people, catalog, pickup_points
from kitchen_core.admin_people_schemas import (
    CommunityZoneUpdate,
    MembershipCreate,
    MembershipUpdate,
)
from kitchen_core.catalog_schemas import (
    CommunityCreate,
    CommunityOut,
    CommunityUpdate,
    CommunityZoneCreate,
    CommunityZoneOut,
    MembershipAdminOut,
    PickupPointCreate,
    PickupPointOut,
    PickupPointUpdate,
)
from kitchen_core.models import Community, CommunityZone, Membership, User
from kitchen_http.auth import require_admin
from sqlalchemy import or_, select

communities_router = APIRouter(
    prefix="/communities", tags=["admin-communities"], dependencies=[Depends(require_admin)]
)
zones_router = APIRouter(
    prefix="/zones", tags=["admin-zones"], dependencies=[Depends(require_admin)]
)
memberships_router = APIRouter(
    prefix="/memberships", tags=["admin-memberships"], dependencies=[Depends(require_admin)]
)


@communities_router.get(
    "", response_model=Page[CommunityOut], operation_id="admin_list_communities"
)
def list_communities(
    session: DB, query: Listing, status: Literal["draft", "active", "paused"] | None = None
):
    statement = select(Community)
    if query.q:
        statement = statement.where(
            or_(
                Community.name.icontains(query.q, autoescape=True),
                Community.city.icontains(query.q, autoescape=True),
            )
        )
    if status:
        statement = statement.where(Community.status == status)
    page = paginate(
        session,
        statement,
        query,
        {"created_at": Community.created_at, "name": Community.name, "city": Community.city},
    )
    page["items"] = [catalog.community_view(session, community) for community in page["items"]]
    return page


@communities_router.post(
    "", response_model=CommunityOut, status_code=201, operation_id="admin_create_community"
)
def create_community(data: CommunityCreate, session: DB):
    return catalog.create_community(session, data)


@communities_router.get(
    "/{community_id}", response_model=CommunityOut, operation_id="admin_get_community"
)
def get_community(community_id: UUID, session: DB):
    return catalog.community_view(session, record(session, Community, community_id))


@communities_router.patch(
    "/{community_id}", response_model=CommunityOut, operation_id="admin_update_community"
)
def update_community(community_id: UUID, data: CommunityUpdate, session: DB):
    record(session, Community, community_id, lock=True)
    return catalog.update_community(session, community_id, data)


@communities_router.delete(
    "/{community_id}",
    status_code=204,
    response_class=Response,
    operation_id="admin_delete_community",
)
def delete_community(community_id: UUID, session: DB):
    admin_people.delete_community(session, community_id)
    return Response(status_code=204)


@communities_router.post(
    "/{community_id}/activate", response_model=CommunityOut, operation_id="admin_activate_community"
)
def activate_community(community_id: UUID, session: DB):
    record(session, Community, community_id, lock=True)
    return catalog.set_community_status(session, community_id, "active")


@communities_router.post(
    "/{community_id}/pause", response_model=CommunityOut, operation_id="admin_pause_community"
)
def pause_community(community_id: UUID, session: DB):
    record(session, Community, community_id, lock=True)
    return catalog.set_community_status(session, community_id, "paused")


def zone_page(session, query, community_id):
    statement = select(CommunityZone)
    if community_id:
        record(session, Community, community_id)
        statement = statement.where(CommunityZone.community_id == community_id)
    if query.q:
        statement = statement.where(CommunityZone.name.icontains(query.q, autoescape=True))
    page = paginate(
        session,
        statement,
        query,
        {"created_at": CommunityZone.created_at, "name": CommunityZone.name},
    )
    page["items"] = [admin_people.zone_view(zone) for zone in page["items"]]
    return page


@communities_router.get(
    "/{community_id}/zones",
    response_model=Page[CommunityZoneOut],
    operation_id="admin_list_community_zones",
)
def list_community_zones(community_id: UUID, session: DB, query: Listing):
    return zone_page(session, query, community_id)


@communities_router.post(
    "/{community_id}/zones",
    response_model=CommunityZoneOut,
    status_code=201,
    operation_id="admin_create_zone",
)
def create_zone(community_id: UUID, data: CommunityZoneCreate, session: DB):
    record(session, Community, community_id, lock=True)
    return catalog.add_zone(session, community_id, data)


@zones_router.get("", response_model=Page[CommunityZoneOut], operation_id="admin_list_zones")
def list_zones(session: DB, query: Listing, community_id: UUID | None = None):
    return zone_page(session, query, community_id)


@zones_router.get("/{zone_id}", response_model=CommunityZoneOut, operation_id="admin_get_zone")
def get_zone(zone_id: UUID, session: DB):
    return admin_people.zone_view(record(session, CommunityZone, zone_id))


@zones_router.patch("/{zone_id}", response_model=CommunityZoneOut, operation_id="admin_update_zone")
def update_zone(zone_id: UUID, data: CommunityZoneUpdate, session: DB):
    return admin_people.update_zone(session, zone_id, data)


@zones_router.delete(
    "/{zone_id}", status_code=204, response_class=Response, operation_id="admin_delete_zone"
)
def delete_zone(zone_id: UUID, session: DB):
    admin_people.delete_zone(session, zone_id)
    return Response(status_code=204)


@memberships_router.get(
    "", response_model=Page[MembershipAdminOut], operation_id="admin_list_memberships"
)
def list_memberships(
    session: DB,
    query: Listing,
    community_id: UUID | None = None,
    user_id: UUID | None = None,
    status: Literal["active", "suspended"] | None = None,
):
    statement = (
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .join(Community, Community.id == Membership.community_id)
        .outerjoin(CommunityZone, CommunityZone.id == Membership.zone_id)
    )
    if community_id:
        record(session, Community, community_id)
        statement = statement.where(Membership.community_id == community_id)
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
                Community.name.icontains(query.q, autoescape=True),
                CommunityZone.name.icontains(query.q, autoescape=True),
                Membership.address_label.icontains(query.q, autoescape=True),
            )
        )
    page = paginate(
        session,
        statement,
        query,
        {
            "created_at": Membership.created_at,
            "address_label": Membership.address_label,
            "name": User.name,
        },
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
for resource_router in (communities_router, zones_router, memberships_router):
    router.include_router(resource_router)


@router.get(
    "/communities/{community_id}/pickup-points",
    response_model=list[PickupPointOut],
    dependencies=[Depends(require_admin)],
)
def community_pickup_points(community_id: UUID, session: DB):
    record(session, Community, community_id)
    return pickup_points.list_points(session, community_id, include_inactive=True)


@router.post(
    "/communities/{community_id}/pickup-points",
    response_model=PickupPointOut,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_pickup_point(community_id: UUID, data: PickupPointCreate, session: DB):
    return pickup_points.create_point(session, community_id, data)


@router.patch(
    "/pickup-points/{point_id}",
    response_model=PickupPointOut,
    dependencies=[Depends(require_admin)],
)
def edit_pickup_point(point_id: UUID, data: PickupPointUpdate, session: DB):
    return pickup_points.update_point(session, point_id, data)
