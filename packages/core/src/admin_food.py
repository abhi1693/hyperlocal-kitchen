"""Privileged catalog operations that retain the marketplace's business rules."""

from uuid import UUID

from kitchen_core import catalog
from kitchen_core.admin_food_schemas import (
    AdminKitchenCreate,
    AdminKitchenUpdate,
    KitchenMemberCreate,
    KitchenMemberOut,
    KitchenMemberUpdate,
)
from kitchen_core.catalog_schemas import DishOut, KitchenCreate, KitchenOwnOut
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Dish,
    Kitchen,
    KitchenMember,
    ListingPickupPoint,
    Membership,
    MenuListing,
    Order,
    PickupPoint,
    User,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def _lock(session: Session, model, identifier: UUID):
    value = session.scalar(
        select(model)
        .where(model.id == identifier)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if value is None:
        raise DomainError(404, "not_found", "The requested record was not found.")
    return value


def create_kitchen(session: Session, data: AdminKitchenCreate) -> KitchenOwnOut:
    owner = _lock(session, User, data.owner_user_id)
    details = KitchenCreate.model_validate(
        data.model_dump(exclude={"owner_user_id"}, exclude_unset=True)
    )
    return catalog.create_kitchen(session, owner, details)


def update_kitchen(session: Session, kitchen_id: UUID, data: AdminKitchenUpdate) -> KitchenOwnOut:
    _lock(session, Kitchen, kitchen_id)
    return catalog.update_kitchen(session, None, kitchen_id, data, admin=True)


def delete_kitchen(session: Session, kitchen_id: UUID):
    kitchen = catalog._locked(session, Kitchen, kitchen_id)
    for model in (Dish, MenuListing, Order):
        if session.scalar(select(model.id).where(model.kitchen_id == kitchen_id).limit(1)):
            raise DomainError(
                409, "record_in_use", "A kitchen with food or order history cannot be deleted."
            )
    owned_points = list(
        session.scalars(
            select(PickupPoint)
            .where(PickupPoint.kitchen_id == kitchen_id)
            .order_by(PickupPoint.id)
            .with_for_update()
        )
    )
    for point in owned_points:
        if session.scalar(
            select(ListingPickupPoint.listing_id)
            .where(ListingPickupPoint.pickup_point_id == point.id)
            .limit(1)
        ) or session.scalar(select(Order.id).where(Order.pickup_point_id == point.id).limit(1)):
            raise DomainError(
                409, "record_in_use", "A referenced pickup point prevents deleting this kitchen."
            )
        session.delete(point)
    session.flush()
    session.execute(delete(KitchenMember).where(KitchenMember.kitchen_id == kitchen_id))
    session.delete(kitchen)
    session.flush()


def member_view(session: Session, member: KitchenMember) -> KitchenMemberOut:
    user = catalog._get(session, User, member.user_id)
    return KitchenMemberOut.model_validate(
        dict(kitchen_id=member.kitchen_id, user_id=user.id, user_name=user.name, role=member.role)
    )


def _require_remaining_owner(session: Session, kitchen: Kitchen, excluding: UUID):
    owner = session.scalar(
        select(KitchenMember.user_id)
        .join(User, User.id == KitchenMember.user_id)
        .join(
            Membership,
            (Membership.user_id == KitchenMember.user_id)
            & (Membership.community_id == kitchen.community_id),
        )
        .where(
            KitchenMember.kitchen_id == kitchen.id,
            KitchenMember.user_id != excluding,
            KitchenMember.role == "owner",
            User.is_active.is_(True),
            Membership.status == "active",
        )
        .limit(1)
    )
    if owner is None:
        raise DomainError(
            409,
            "active_owner_required",
            "The kitchen must retain an active community member as owner.",
        )


def create_member(
    session: Session, kitchen_id: UUID, data: KitchenMemberCreate
) -> KitchenMemberOut:
    # Use the same user-before-kitchen order as account deactivation and kitchen creation.
    _lock(session, User, data.user_id)
    kitchen = _lock(session, Kitchen, kitchen_id)
    catalog.require_membership(session, data.user_id, kitchen.community_id)
    if session.get(KitchenMember, (kitchen_id, data.user_id)) is not None:
        raise DomainError(409, "member_exists", "This user already manages the kitchen.")
    if data.role != "owner":
        _require_remaining_owner(session, kitchen, data.user_id)
    member = KitchenMember(kitchen_id=kitchen_id, user_id=data.user_id, role=data.role)
    session.add(member)
    session.flush()
    return member_view(session, member)


def update_member(
    session: Session, kitchen_id: UUID, user_id: UUID, data: KitchenMemberUpdate
) -> KitchenMemberOut:
    _lock(session, User, user_id)
    kitchen = _lock(session, Kitchen, kitchen_id)
    catalog.require_membership(session, user_id, kitchen.community_id)
    member = session.get(KitchenMember, (kitchen_id, user_id))
    if member is None:
        raise DomainError(404, "not_found", "Kitchen member was not found.")
    if data.role != "owner":
        _require_remaining_owner(session, kitchen, user_id)
    member.role = data.role
    session.flush()
    return member_view(session, member)


def delete_member(session: Session, kitchen_id: UUID, user_id: UUID):
    _lock(session, User, user_id)
    kitchen = _lock(session, Kitchen, kitchen_id)
    member = session.get(KitchenMember, (kitchen_id, user_id))
    if member is None:
        raise DomainError(404, "not_found", "Kitchen member was not found.")
    _require_remaining_owner(session, kitchen, user_id)
    session.delete(member)
    session.flush()


def restore_dish(session: Session, dish_id: UUID) -> DishOut:
    dish = _lock(session, Dish, dish_id)
    dish.is_active = True
    session.flush()
    return catalog.dish_view(dish)
