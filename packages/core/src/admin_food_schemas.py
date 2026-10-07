"""Typed platform-admin operations for existing kitchens, dishes and listings."""

from typing import Literal
from uuid import UUID

from kitchen_core.catalog_schemas import (
    DishCreate,
    KitchenCreate,
    KitchenUpdate,
    ListingCreate,
    StrictRequest,
)


class AdminKitchenCreate(KitchenCreate):
    owner_user_id: UUID


class AdminKitchenUpdate(KitchenUpdate):
    pass


class KitchenMemberCreate(StrictRequest):
    user_id: UUID
    role: Literal["owner", "manager"] = "manager"


class KitchenMemberUpdate(StrictRequest):
    role: Literal["owner", "manager"]


class KitchenMemberOut(StrictRequest):
    kitchen_id: UUID
    user_id: UUID
    user_name: str | None
    role: Literal["owner", "manager"]


class AdminDishCreate(DishCreate):
    kitchen_id: UUID


class AdminListingCreate(ListingCreate):
    kitchen_id: UUID
