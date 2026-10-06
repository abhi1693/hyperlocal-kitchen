"""Resident and kitchen-owner routes; platform administration lives separately."""

from datetime import date
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from kitchen_core import catalog
from kitchen_core.catalog_schemas import (
    DishCreate,
    DishOut,
    DishUpdate,
    KitchenCreate,
    KitchenOut,
    KitchenOwnOut,
    KitchenPage,
    KitchenUpdate,
    ListingCreate,
    ListingOut,
    ListingPage,
    ListingUpdate,
    MembershipJoin,
    MembershipOut,
    MessageOut,
    SocietyOut,
    SocietyPage,
    TowerOut,
)
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import Kitchen, Society, User, utcnow
from kitchen_http.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(tags=["societies and food"])
DB = Annotated[Session, Depends(get_session, scope="function")]
Resident = Annotated[User, Depends(require_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _range(
    session: Session, society_id: UUID, on: date | None, start: date | None, end: date | None
):
    catalog._get(session, Society, society_id)
    if on is not None and (start is not None or end is not None):
        raise DomainError(422, "invalid_date_range", "Use a date or a date range, not both.")
    if end is not None and start is None:
        raise DomainError(422, "invalid_date_range", "A range end also requires a start.")
    first = on or start or utcnow().astimezone(ZoneInfo("Asia/Kolkata")).date()
    return first, end or first


@router.get("/societies", response_model=SocietyPage)
def societies(
    session: DB,
    user: Resident,
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return catalog.list_societies(session, query, limit, offset)


@router.get("/societies/{society_id}", response_model=SocietyOut)
def society(society_id: UUID, session: DB, user: Resident):
    return catalog.society_view(session, catalog.require_active_society(session, society_id))


@router.get("/societies/{society_id}/towers", response_model=list[TowerOut])
def towers(society_id: UUID, session: DB, user: Resident, limit: Limit = 100, offset: Offset = 0):
    result = catalog.society_view(session, catalog.require_active_society(session, society_id))
    return result.towers[offset : offset + limit]


@router.post("/societies/{society_id}/join", response_model=MembershipOut, status_code=201)
def join(society_id: UUID, data: MembershipJoin, session: DB, user: Resident):
    return catalog.join_society(session, user, society_id, data)


@router.get("/me/societies", response_model=list[MembershipOut])
def my_societies(session: DB, user: Resident, limit: Limit = 30, offset: Offset = 0):
    return catalog.my_memberships(session, user.id, limit, offset)


@router.post("/kitchens", response_model=KitchenOwnOut, status_code=201)
def create_kitchen(data: KitchenCreate, session: DB, user: Resident):
    return catalog.create_kitchen(session, user, data)


@router.get("/me/kitchens", response_model=list[KitchenOwnOut])
def own_kitchens(session: DB, user: Resident, limit: Limit = 30, offset: Offset = 0):
    return catalog.my_kitchens(session, user.id, limit, offset)


@router.get("/societies/{society_id}/kitchens", response_model=KitchenPage)
def kitchens(
    society_id: UUID,
    session: DB,
    user: Resident,
    query: Annotated[str | None, Query(max_length=150)] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return catalog.list_kitchens(session, user.id, society_id, query, limit, offset)


@router.get("/kitchens/{kitchen_id}", response_model=KitchenOut)
def kitchen(kitchen_id: UUID, session: DB, user: Resident):
    return catalog.get_kitchen(session, user.id, kitchen_id)


@router.patch("/kitchens/{kitchen_id}", response_model=KitchenOwnOut)
def edit_kitchen(kitchen_id: UUID, data: KitchenUpdate, session: DB, user: Resident):
    return catalog.update_kitchen(session, user.id, kitchen_id, data)


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


@router.get("/societies/{society_id}/menu", response_model=ListingPage)
def society_menu(
    society_id: UUID,
    session: DB,
    user: Resident,
    on: Annotated[date | None, Query(alias="date")] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    first, last = _range(session, society_id, on, start, end)
    return catalog.list_listings(session, user.id, society_id, first, last, limit, offset)


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
    first, last = _range(session, kitchen.society_id, on, start, end)
    return catalog.list_listings(
        session, user.id, kitchen.society_id, first, last, limit, offset, kitchen_id=kitchen_id
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
    first, last = _range(session, kitchen.society_id, on, start, end)
    return catalog.list_listings(
        session,
        user.id,
        kitchen.society_id,
        first,
        last,
        limit,
        offset,
        kitchen_id=kitchen_id,
        owned=True,
    )
