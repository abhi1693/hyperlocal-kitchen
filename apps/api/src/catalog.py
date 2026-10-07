"""Resident and kitchen-owner routes; platform administration lives separately."""

from datetime import date
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from kitchen_core import admin_people, catalog, pickup_points
from kitchen_core.admin_people_schemas import MembershipUpdate
from kitchen_core.catalog_schemas import (
    CommunityOut,
    CommunityPage,
    CommunityZoneOut,
    DishCreate,
    DishOut,
    DishUpdate,
    KitchenCreate,
    KitchenOut,
    KitchenOwnOut,
    KitchenPage,
    KitchenPause,
    KitchenUpdate,
    ListingCreate,
    ListingOut,
    ListingPage,
    ListingUpdate,
    MembershipJoin,
    MembershipOut,
    MessageOut,
    PickupPointCreate,
    PickupPointOut,
    PickupPointUpdate,
)
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import Community, Kitchen, Membership, User, utcnow
from kitchen_http.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(tags=["communities and food"])
DB = Annotated[Session, Depends(get_session, scope="function")]
Resident = Annotated[User, Depends(require_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _range(
    session: Session, community_id: UUID, on: date | None, start: date | None, end: date | None
):
    catalog._get(session, Community, community_id)
    if on is not None and (start is not None or end is not None):
        raise DomainError(422, "invalid_date_range", "Use a date or a date range, not both.")
    if end is not None and start is None:
        raise DomainError(422, "invalid_date_range", "A range end also requires a start.")
    first = on or start or utcnow().astimezone(ZoneInfo("Asia/Kolkata")).date()
    return first, end or first


@router.get("/communities", response_model=CommunityPage)
def communities(
    session: DB,
    user: Resident,
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return catalog.list_communities(session, query, limit, offset)


@router.get("/communities/{community_id}", response_model=CommunityOut)
def community(community_id: UUID, session: DB, user: Resident):
    return catalog.community_view(session, catalog.require_active_community(session, community_id))


@router.get("/communities/{community_id}/zones", response_model=list[CommunityZoneOut])
def zones(community_id: UUID, session: DB, user: Resident, limit: Limit = 100, offset: Offset = 0):
    result = catalog.community_view(
        session, catalog.require_active_community(session, community_id)
    )
    return result.zones[offset : offset + limit]


@router.post("/communities/{community_id}/join", response_model=MembershipOut, status_code=201)
def join(community_id: UUID, data: MembershipJoin, session: DB, user: Resident):
    return catalog.join_community(session, user, community_id, data)


@router.get("/me/communities", response_model=list[MembershipOut])
def my_communities(session: DB, user: Resident, limit: Limit = 30, offset: Offset = 0):
    return catalog.my_memberships(session, user.id, limit, offset)


@router.post("/kitchens", response_model=KitchenOwnOut, status_code=201)
def create_kitchen(data: KitchenCreate, session: DB, user: Resident):
    return catalog.create_kitchen(session, user, data)


@router.get("/me/kitchens", response_model=list[KitchenOwnOut])
def own_kitchens(session: DB, user: Resident, limit: Limit = 30, offset: Offset = 0):
    return catalog.my_kitchens(session, user.id, limit, offset)


@router.get("/communities/{community_id}/kitchens", response_model=KitchenPage)
def kitchens(
    community_id: UUID,
    session: DB,
    user: Resident,
    query: Annotated[str | None, Query(max_length=150)] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return catalog.list_kitchens(session, user.id, community_id, query, limit, offset)


@router.get("/kitchens/{kitchen_id}", response_model=KitchenOut)
def kitchen(kitchen_id: UUID, session: DB, user: Resident):
    return catalog.get_kitchen(session, user.id, kitchen_id)


@router.patch("/kitchens/{kitchen_id}", response_model=KitchenOwnOut)
def edit_kitchen(kitchen_id: UUID, data: KitchenUpdate, session: DB, user: Resident):
    return catalog.update_kitchen(session, user.id, kitchen_id, data)


@router.post("/kitchens/{kitchen_id}/pause", response_model=KitchenOwnOut)
def pause_kitchen(
    kitchen_id: UUID, session: DB, user: Resident, data: KitchenPause = KitchenPause()
):
    return catalog.set_kitchen_accepting_orders(
        session, user.id, kitchen_id, accepting=False, reason=data.reason
    )


@router.post("/kitchens/{kitchen_id}/resume", response_model=KitchenOwnOut)
def resume_kitchen(kitchen_id: UUID, session: DB, user: Resident):
    return catalog.set_kitchen_accepting_orders(session, user.id, kitchen_id, accepting=True)


@router.get("/kitchens/{kitchen_id}/dishes", response_model=list[DishOut])
def dishes(kitchen_id: UUID, session: DB, user: Resident, limit: Limit = 30, offset: Offset = 0):
    return catalog.list_dishes(session, user.id, kitchen_id, limit, offset)


@router.post("/kitchens/{kitchen_id}/dishes", response_model=DishOut, status_code=201)
def add_dish(kitchen_id: UUID, data: DishCreate, session: DB, user: Resident):
    return catalog.create_dish(session, user.id, kitchen_id, data)


@router.patch("/dishes/{dish_id}", response_model=DishOut)
def edit_dish(dish_id: UUID, data: DishUpdate, session: DB, user: Resident):
    return catalog.update_dish(session, user.id, dish_id, data)


@router.delete("/dishes/{dish_id}", response_model=MessageOut)
def remove_dish(dish_id: UUID, session: DB, user: Resident):
    catalog.archive_dish(session, user.id, dish_id)
    return MessageOut(message="Dish archived.")


@router.post("/kitchens/{kitchen_id}/menu-listings", response_model=ListingOut, status_code=201)
def publish(kitchen_id: UUID, data: ListingCreate, session: DB, user: Resident):
    return catalog.create_listing(session, user.id, kitchen_id, data)


@router.patch("/menu-listings/{listing_id}", response_model=ListingOut)
def edit_listing(listing_id: UUID, data: ListingUpdate, session: DB, user: Resident):
    return catalog.update_listing(session, user.id, listing_id, data)


@router.delete("/menu-listings/{listing_id}", response_model=MessageOut)
def remove_listing(listing_id: UUID, session: DB, user: Resident):
    catalog.cancel_listing(session, user.id, listing_id)
    return MessageOut(message="Listing cancelled.")


@router.get("/menu-listings/{listing_id}", response_model=ListingOut)
def listing(listing_id: UUID, session: DB, user: Resident):
    return catalog.get_listing(session, user.id, listing_id)


@router.get("/communities/{community_id}/menu", response_model=ListingPage)
def community_menu(
    community_id: UUID,
    session: DB,
    user: Resident,
    on: Annotated[date | None, Query(alias="date")] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    first, last = _range(session, community_id, on, start, end)
    return catalog.list_listings(session, user.id, community_id, first, last, limit, offset)


@router.get("/kitchens/{kitchen_id}/menu", response_model=ListingPage)
def kitchen_menu(
    kitchen_id: UUID,
    session: DB,
    user: Resident,
    on: Annotated[date | None, Query(alias="date")] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    kitchen = catalog._get(session, Kitchen, kitchen_id)
    first, last = _range(session, kitchen.community_id, on, start, end)
    return catalog.list_listings(
        session, user.id, kitchen.community_id, first, last, limit, offset, kitchen_id=kitchen_id
    )


@router.get("/kitchens/{kitchen_id}/menu-listings", response_model=ListingPage)
def own_menu(
    kitchen_id: UUID,
    session: DB,
    user: Resident,
    on: Annotated[date | None, Query(alias="date")] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    kitchen = catalog.require_kitchen_member(session, user.id, kitchen_id)
    first, last = _range(session, kitchen.community_id, on, start, end)
    return catalog.list_listings(
        session,
        user.id,
        kitchen.community_id,
        first,
        last,
        limit,
        offset,
        kitchen_id=kitchen_id,
        owned=True,
    )


@router.get("/communities/{community_id}/pickup-points", response_model=list[PickupPointOut])
def community_pickup_points(community_id: UUID, session: DB, user: Resident):
    catalog.require_membership(session, user.id, community_id)
    return pickup_points.list_points(session, community_id)


@router.get("/kitchens/{kitchen_id}/pickup-points", response_model=list[PickupPointOut])
def kitchen_pickup_points(kitchen_id: UUID, session: DB, user: Resident):
    kitchen = catalog.require_kitchen_member(session, user.id, kitchen_id)
    return pickup_points.list_points(
        session, kitchen.community_id, kitchen_id=kitchen_id, include_inactive=True
    )


@router.post("/kitchens/{kitchen_id}/pickup-points", response_model=PickupPointOut, status_code=201)
def create_pickup_point(kitchen_id: UUID, data: PickupPointCreate, session: DB, user: Resident):
    kitchen = catalog._require_kitchen_mutation(session, user.id, kitchen_id)
    return pickup_points.create_point(session, kitchen.community_id, data, kitchen_id=kitchen_id)


@router.patch("/kitchens/{kitchen_id}/pickup-points/{point_id}", response_model=PickupPointOut)
def edit_pickup_point(
    kitchen_id: UUID, point_id: UUID, data: PickupPointUpdate, session: DB, user: Resident
):
    catalog.require_kitchen_member(session, user.id, kitchen_id)
    return pickup_points.update_point(session, point_id, data, kitchen_id=kitchen_id)


@router.patch("/me/memberships/{membership_id}", response_model=MembershipOut)
def edit_home(membership_id: UUID, data: MembershipUpdate, session: DB, user: Resident):
    membership = catalog._get(session, Membership, membership_id)
    if membership.user_id != user.id:
        raise DomainError(404, "not_found", "Membership was not found.")
    catalog.require_membership(session, user.id, membership.community_id)
    result = admin_people.update_membership(session, membership_id, data)
    return MembershipOut.model_validate(result.model_dump())
