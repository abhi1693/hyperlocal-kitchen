"""Typed food administration on the separate platform-admin application."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from kitchen_admin_api.dependencies import DB
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import admin_food, catalog
from kitchen_core.admin_food_schemas import (
    AdminDishCreate,
    AdminKitchenCreate,
    AdminKitchenUpdate,
    AdminListingCreate,
    KitchenMemberCreate,
    KitchenMemberOut,
    KitchenMemberUpdate,
)
from kitchen_core.catalog_schemas import (
    DishCreate,
    DishOut,
    DishUpdate,
    KitchenApprove,
    KitchenOwnOut,
    ListingCreate,
    ListingOut,
    ListingUpdate,
)
from kitchen_core.errors import DomainError
from kitchen_core.models import Dish, Kitchen, KitchenMember, MenuListing, User
from kitchen_http.auth import require_admin
from sqlalchemy import select

router = APIRouter(tags=["food administration"], dependencies=[Depends(require_admin)])


@router.get("/kitchens", response_model=Page[KitchenOwnOut], operation_id="admin_food_kitchens")
def kitchens(
    session: DB,
    listing: Listing,
    community_id: UUID | None = None,
    status: Literal["pending", "approved", "suspended"] | None = None,
):
    statement = select(Kitchen)
    if community_id is not None:
        statement = statement.where(Kitchen.community_id == community_id)
    if status is not None:
        statement = statement.where(Kitchen.status == status)
    if listing.q:
        statement = statement.where(Kitchen.name.icontains(listing.q, autoescape=True))
    page = paginate(
        session,
        statement,
        listing,
        {
            "created_at": Kitchen.created_at,
            "name": Kitchen.name,
            "status": Kitchen.status,
        },
    )
    page["items"] = [catalog.kitchen_view(session, row, private=True) for row in page["items"]]
    return page


@router.post(
    "/kitchens",
    response_model=KitchenOwnOut,
    status_code=201,
    operation_id="admin_food_create_kitchen",
)
def create_kitchen(data: AdminKitchenCreate, session: DB):
    return admin_food.create_kitchen(session, data)


@router.get(
    "/kitchens/{kitchen_id}", response_model=KitchenOwnOut, operation_id="admin_food_kitchen"
)
def kitchen(kitchen_id: UUID, session: DB):
    return catalog.kitchen_view(session, record(session, Kitchen, kitchen_id), private=True)


@router.patch(
    "/kitchens/{kitchen_id}", response_model=KitchenOwnOut, operation_id="admin_food_update_kitchen"
)
def update_kitchen(kitchen_id: UUID, data: AdminKitchenUpdate, session: DB):
    return admin_food.update_kitchen(session, kitchen_id, data)


@router.delete("/kitchens/{kitchen_id}", status_code=204, operation_id="admin_food_delete_kitchen")
def delete_kitchen(kitchen_id: UUID, session: DB):
    admin_food.delete_kitchen(session, kitchen_id)
    return Response(status_code=204)


@router.post(
    "/kitchens/{kitchen_id}/approve",
    response_model=KitchenOwnOut,
    operation_id="admin_food_approve_kitchen",
)
def approve_kitchen(kitchen_id: UUID, data: KitchenApprove, session: DB):
    return catalog.approve_kitchen(session, kitchen_id, data)


@router.post(
    "/kitchens/{kitchen_id}/suspend",
    response_model=KitchenOwnOut,
    operation_id="admin_food_suspend_kitchen",
)
def suspend_kitchen(kitchen_id: UUID, session: DB):
    return catalog.suspend_kitchen(session, kitchen_id)


@router.get(
    "/kitchens/{kitchen_id}/members",
    response_model=Page[KitchenMemberOut],
    operation_id="admin_food_kitchen_members",
)
def members(kitchen_id: UUID, session: DB, listing: Listing):
    record(session, Kitchen, kitchen_id)
    statement = select(KitchenMember).join(User).where(KitchenMember.kitchen_id == kitchen_id)
    if listing.q:
        statement = statement.where(User.name.icontains(listing.q, autoescape=True))
    page = paginate(
        session,
        statement,
        listing,
        {
            "user_id": KitchenMember.user_id,
            "role": KitchenMember.role,
            "name": User.name,
        },
        default="user_id",
    )
    page["items"] = [admin_food.member_view(session, row) for row in page["items"]]
    return page


@router.post(
    "/kitchens/{kitchen_id}/members",
    response_model=KitchenMemberOut,
    status_code=201,
    operation_id="admin_food_create_kitchen_member",
)
def create_member(kitchen_id: UUID, data: KitchenMemberCreate, session: DB):
    return admin_food.create_member(session, kitchen_id, data)


@router.patch(
    "/kitchens/{kitchen_id}/members/{user_id}",
    response_model=KitchenMemberOut,
    operation_id="admin_food_update_kitchen_member",
)
def update_member(kitchen_id: UUID, user_id: UUID, data: KitchenMemberUpdate, session: DB):
    return admin_food.update_member(session, kitchen_id, user_id, data)


@router.delete(
    "/kitchens/{kitchen_id}/members/{user_id}",
    status_code=204,
    operation_id="admin_food_delete_kitchen_member",
)
def delete_member(kitchen_id: UUID, user_id: UUID, session: DB):
    admin_food.delete_member(session, kitchen_id, user_id)
    return Response(status_code=204)


def _dishes(session, listing, *, kitchen_id=None, community_id=None, is_active=None):
    statement = select(Dish).join(Kitchen)
    if kitchen_id is not None:
        statement = statement.where(Dish.kitchen_id == kitchen_id)
    if community_id is not None:
        statement = statement.where(Kitchen.community_id == community_id)
    if is_active is not None:
        statement = statement.where(Dish.is_active.is_(is_active))
    if listing.q:
        statement = statement.where(Dish.name.icontains(listing.q, autoescape=True))
    page = paginate(
        session,
        statement,
        listing,
        {
            "created_at": Dish.created_at,
            "name": Dish.name,
            "is_active": Dish.is_active,
        },
    )
    page["items"] = [catalog.dish_view(row) for row in page["items"]]
    return page


@router.get("/dishes", response_model=Page[DishOut], operation_id="admin_food_dishes")
def dishes(
    session: DB,
    listing: Listing,
    kitchen_id: UUID | None = None,
    community_id: UUID | None = None,
    is_active: bool | None = None,
):
    return _dishes(
        session, listing, kitchen_id=kitchen_id, community_id=community_id, is_active=is_active
    )


@router.get(
    "/kitchens/{kitchen_id}/dishes",
    response_model=Page[DishOut],
    operation_id="admin_food_kitchen_dishes",
)
def kitchen_dishes(kitchen_id: UUID, session: DB, listing: Listing, is_active: bool | None = None):
    record(session, Kitchen, kitchen_id)
    return _dishes(session, listing, kitchen_id=kitchen_id, is_active=is_active)


@router.post(
    "/dishes", response_model=DishOut, status_code=201, operation_id="admin_food_create_dish"
)
def create_dish(data: AdminDishCreate, session: DB):
    details = DishCreate.model_validate(data.model_dump(exclude={"kitchen_id"}))
    return catalog.create_dish(session, None, data.kitchen_id, details, admin=True)


@router.post(
    "/kitchens/{kitchen_id}/dishes",
    response_model=DishOut,
    status_code=201,
    operation_id="admin_food_create_kitchen_dish",
)
def create_kitchen_dish(kitchen_id: UUID, data: DishCreate, session: DB):
    return catalog.create_dish(session, None, kitchen_id, data, admin=True)


@router.get("/dishes/{dish_id}", response_model=DishOut, operation_id="admin_food_dish")
def dish(dish_id: UUID, session: DB):
    return catalog.dish_view(record(session, Dish, dish_id))


@router.patch("/dishes/{dish_id}", response_model=DishOut, operation_id="admin_food_update_dish")
def update_dish(dish_id: UUID, data: DishUpdate, session: DB):
    return catalog.update_dish(session, None, dish_id, data, admin=True)


@router.delete("/dishes/{dish_id}", status_code=204, operation_id="admin_food_archive_dish")
def archive_dish(dish_id: UUID, session: DB):
    catalog.archive_dish(session, None, dish_id, admin=True)
    return Response(status_code=204)


@router.post(
    "/dishes/{dish_id}/restore", response_model=DishOut, operation_id="admin_food_restore_dish"
)
def restore_dish(dish_id: UUID, session: DB):
    return admin_food.restore_dish(session, dish_id)


def _listings(
    session,
    listing,
    *,
    kitchen_id=None,
    community_id=None,
    dish_id=None,
    service_date=None,
    date_from=None,
    date_until=None,
    status=None,
):
    if date_from is not None and date_until is not None and date_until < date_from:
        raise DomainError(422, "invalid_date_range", "The end date must follow the start date.")
    statement = (
        select(MenuListing)
        .join(Kitchen, Kitchen.id == MenuListing.kitchen_id)
        .join(Dish, Dish.id == MenuListing.dish_id)
    )
    for column, value in (
        (MenuListing.kitchen_id, kitchen_id),
        (Kitchen.community_id, community_id),
        (MenuListing.dish_id, dish_id),
        (MenuListing.service_date, service_date),
    ):
        if value is not None:
            statement = statement.where(column == value)
    if date_from is not None:
        statement = statement.where(MenuListing.service_date >= date_from)
    if date_until is not None:
        statement = statement.where(MenuListing.service_date <= date_until)
    if status == "sold_out":
        statement = statement.where(
            MenuListing.status == "published",
            MenuListing.quantity_reserved == MenuListing.quantity_total,
        )
    elif status is not None:
        statement = statement.where(MenuListing.status == status)
    if listing.q:
        statement = statement.where(Dish.name.icontains(listing.q, autoescape=True))
    page = paginate(
        session,
        statement,
        listing,
        {
            "created_at": MenuListing.created_at,
            "service_date": MenuListing.service_date,
            "price_paise": MenuListing.price_paise,
            "status": MenuListing.status,
        },
    )
    page["items"] = [catalog.listing_view(session, row) for row in page["items"]]
    return page


@router.get("/menu-listings", response_model=Page[ListingOut], operation_id="admin_food_listings")
def listings(
    session: DB,
    listing: Listing,
    kitchen_id: UUID | None = None,
    community_id: UUID | None = None,
    dish_id: UUID | None = None,
    service_date: date | None = None,
    date_from: date | None = None,
    date_until: date | None = None,
    status: Literal["draft", "published", "sold_out", "cancelled"] | None = None,
):
    return _listings(
        session,
        listing,
        kitchen_id=kitchen_id,
        community_id=community_id,
        dish_id=dish_id,
        service_date=service_date,
        date_from=date_from,
        date_until=date_until,
        status=status,
    )


@router.get(
    "/kitchens/{kitchen_id}/menu-listings",
    response_model=Page[ListingOut],
    operation_id="admin_food_kitchen_listings",
)
def kitchen_listings(
    kitchen_id: UUID,
    session: DB,
    listing: Listing,
    service_date: date | None = None,
    date_from: date | None = None,
    date_until: date | None = None,
    status: Literal["draft", "published", "sold_out", "cancelled"] | None = None,
):
    record(session, Kitchen, kitchen_id)
    return _listings(
        session,
        listing,
        kitchen_id=kitchen_id,
        service_date=service_date,
        date_from=date_from,
        date_until=date_until,
        status=status,
    )


@router.post(
    "/menu-listings",
    response_model=ListingOut,
    status_code=201,
    operation_id="admin_food_create_listing",
)
def create_listing(data: AdminListingCreate, session: DB):
    details = ListingCreate.model_validate(data.model_dump(exclude={"kitchen_id"}))
    return catalog.create_listing(session, None, data.kitchen_id, details, admin=True)


@router.post(
    "/kitchens/{kitchen_id}/menu-listings",
    response_model=ListingOut,
    status_code=201,
    operation_id="admin_food_create_kitchen_listing",
)
def create_kitchen_listing(kitchen_id: UUID, data: ListingCreate, session: DB):
    return catalog.create_listing(session, None, kitchen_id, data, admin=True)


@router.get(
    "/menu-listings/{listing_id}", response_model=ListingOut, operation_id="admin_food_listing"
)
def listing_detail(listing_id: UUID, session: DB):
    return catalog.listing_view(session, record(session, MenuListing, listing_id))


@router.patch(
    "/menu-listings/{listing_id}",
    response_model=ListingOut,
    operation_id="admin_food_update_listing",
)
def update_listing(listing_id: UUID, data: ListingUpdate, session: DB):
    return catalog.update_listing(session, None, listing_id, data, admin=True)


@router.delete(
    "/menu-listings/{listing_id}", status_code=204, operation_id="admin_food_cancel_listing"
)
def cancel_listing(listing_id: UUID, session: DB):
    catalog.cancel_listing(session, None, listing_id, admin=True)
    return Response(status_code=204)
