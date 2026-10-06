"""Society-scoped catalog operations shared by the resident and admin APIs."""

from datetime import UTC, date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from kitchen_core.catalog_schemas import (
    DishCreate,
    DishOut,
    DishUpdate,
    KitchenAdminPage,
    KitchenApprove,
    KitchenCreate,
    KitchenOut,
    KitchenOwnOut,
    KitchenPage,
    KitchenUpdate,
    ListingCreate,
    ListingOut,
    ListingPage,
    ListingUpdate,
    MembershipAdminOut,
    MembershipJoin,
    MembershipOut,
    MembershipPage,
    SocietyCreate,
    SocietyOut,
    SocietyPage,
    SocietyUpdate,
    TowerCreate,
    TowerOut,
)
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Dish,
    Kitchen,
    KitchenMember,
    Membership,
    MenuListing,
    Order,
    OrderItem,
    Society,
    Tower,
    User,
    utcnow,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _get(session: Session, model, entity_id: UUID):
    entity = session.get(model, entity_id)
    if entity is None:
        raise DomainError(404, "not_found", "The requested record was not found.")
    return entity


def _locked(session: Session, model, entity_id: UUID):
    entity = session.scalar(
        select(model)
        .where(model.id == entity_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if entity is None:
        raise DomainError(404, "not_found", "The requested record was not found.")
    return entity


def _locked_active_user(session: Session, user_id: UUID) -> User:
    user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active:
        raise DomainError(403, "user_inactive", "An active account is required.")
    return user


def _page(session: Session, statement, limit: int, offset: int):
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    return list(session.scalars(statement.limit(limit).offset(offset))), total or 0


def require_active_society(session: Session, society_id: UUID) -> Society:
    society = _get(session, Society, society_id)
    if society.status != "active":
        raise DomainError(
            409, "society_unavailable", "This society is not accepting activity right now."
        )
    return society


def require_membership(session: Session, user_id: UUID, society_id: UUID) -> Membership:
    user = _get(session, User, user_id)
    membership = session.scalar(
        select(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.society_id == society_id,
            Membership.status == "active",
        )
        .execution_options(populate_existing=True)
    )
    if membership is None or not user.is_active:
        raise DomainError(
            403, "membership_required", "An active membership in this society is required."
        )
    return membership


def require_kitchen_member(session: Session, user_id: UUID, kitchen_id: UUID) -> Kitchen:
    kitchen = _get(session, Kitchen, kitchen_id)
    member = session.get(KitchenMember, (kitchen_id, user_id))
    if member is None:
        raise DomainError(403, "kitchen_access_denied", "You do not manage this kitchen.")
    require_membership(session, user_id, kitchen.society_id)
    return kitchen


def _require_kitchen_mutation(
    session: Session, user_id: UUID | None, kitchen_id: UUID, *, admin: bool = False
) -> Kitchen:
    if admin:
        return _get(session, Kitchen, kitchen_id)
    if user_id is None:
        raise DomainError(403, "kitchen_access_denied", "You do not manage this kitchen.")
    kitchen = require_kitchen_member(session, user_id, kitchen_id)
    require_active_society(session, kitchen.society_id)
    if kitchen.status == "suspended":
        raise DomainError(403, "kitchen_suspended", "This kitchen is suspended. Contact support.")
    return kitchen


def society_view(session: Session, society: Society) -> SocietyOut:
    towers = session.scalars(
        select(Tower).where(Tower.society_id == society.id).order_by(Tower.name)
    )
    return SocietyOut(
        id=society.id,
        name=society.name,
        address=society.address,
        city=society.city,
        postal_code=society.postal_code,
        status=society.status,
        towers=[TowerOut(id=t.id, society_id=t.society_id, name=t.name) for t in towers],
    )


def membership_view(session: Session, membership: Membership, *, admin: bool = False):
    society = _get(session, Society, membership.society_id)
    tower = _get(session, Tower, membership.tower_id)
    data = dict(
        id=membership.id,
        user_id=membership.user_id,
        society_id=membership.society_id,
        society_name=society.name,
        tower_id=tower.id,
        tower_name=tower.name,
        flat=membership.flat,
        status=membership.status,
    )
    if admin:
        user = _get(session, User, membership.user_id)
        return MembershipAdminOut(**data, user_name=user.name, phone=user.phone)
    return MembershipOut(**data)


def kitchen_view(session: Session, kitchen: Kitchen, *, private: bool = False):
    tower = _get(session, Tower, kitchen.tower_id)
    data = dict(
        id=kitchen.id,
        society_id=kitchen.society_id,
        name=kitchen.name,
        description=kitchen.description,
        tower_name=tower.name,
        pickup_enabled=kitchen.pickup_enabled,
        delivery_enabled=kitchen.delivery_enabled,
        delivery_fee_paise=kitchen.delivery_fee_paise,
        status=kitchen.status,
        fssai_number=kitchen.fssai_number,
    )
    if private:
        return KitchenOwnOut(
            **data, tower_id=kitchen.tower_id, flat=kitchen.flat, upi_id=kitchen.upi_id
        )
    return KitchenOut(**data)


def dish_view(dish: Dish) -> DishOut:
    return DishOut(
        id=dish.id,
        kitchen_id=dish.kitchen_id,
        name=dish.name,
        description=dish.description,
        image_url=dish.image_url,
        is_active=dish.is_active,
    )


def listing_view(session: Session, listing: MenuListing) -> ListingOut:
    kitchen = _get(session, Kitchen, listing.kitchen_id)
    dish = _get(session, Dish, listing.dish_id)
    society = _get(session, Society, kitchen.society_id)
    remaining = listing.quantity_total - listing.quantity_reserved
    return ListingOut(
        id=listing.id,
        kitchen=kitchen_view(session, kitchen),
        dish=dish_view(dish),
        service_date=listing.service_date,
        available_from=listing.available_from,
        available_until=listing.available_until,
        order_cutoff=listing.order_cutoff,
        price_paise=listing.price_paise,
        quantity_total=listing.quantity_total,
        quantity_remaining=remaining,
        pickup_enabled=listing.pickup_enabled,
        delivery_enabled=listing.delivery_enabled,
        delivery_fee_paise=kitchen.delivery_fee_paise if listing.delivery_enabled else 0,
        status="sold_out" if listing.status == "published" and remaining == 0 else listing.status,
        is_orderable=(
            listing.status == "published"
            and remaining > 0
            and dish.is_active
            and kitchen.status == "approved"
            and society.status == "active"
            and listing.order_cutoff > utcnow()
            and (
                (listing.pickup_enabled and kitchen.pickup_enabled)
                or (listing.delivery_enabled and kitchen.delivery_enabled)
            )
        ),
    )


def create_society(session: Session, data: SocietyCreate) -> SocietyOut:
    names = [tower.name.casefold() for tower in data.towers]
    if len(names) != len(set(names)):
        raise DomainError(422, "duplicate_tower", "Tower names must be unique within a society.")
    society = Society(**data.model_dump(exclude={"towers"}), status="draft")
    session.add(society)
    session.flush()
    for tower in data.towers:
        session.add(Tower(society_id=society.id, name=tower.name))
    session.flush()
    return society_view(session, society)


def update_society(session: Session, society_id: UUID, data: SocietyUpdate) -> SocietyOut:
    society = _get(session, Society, society_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "address", "city", "postal_code"):
        if field in values and values[field] is None:
            raise DomainError(422, "required_field", f"{field} cannot be empty.")
    for field, value in values.items():
        setattr(society, field, value)
    session.flush()
    return society_view(session, society)


def set_society_status(session: Session, society_id: UUID, status: str) -> SocietyOut:
    society = _locked(session, Society, society_id)
    if (
        status == "active"
        and session.scalar(select(Tower.id).where(Tower.society_id == society_id).limit(1)) is None
    ):
        raise DomainError(
            409, "towers_required", "Add at least one tower before activating the society."
        )
    society.status = status
    session.flush()
    return society_view(session, society)


def add_tower(session: Session, society_id: UUID, data: TowerCreate) -> TowerOut:
    _locked(session, Society, society_id)
    existing = session.scalar(
        select(Tower.id).where(
            Tower.society_id == society_id,
            func.lower(Tower.name) == data.name.lower(),
        )
    )
    if existing is not None:
        raise DomainError(409, "duplicate_tower", "A tower with this name already exists.")
    tower = Tower(society_id=society_id, name=data.name)
    session.add(tower)
    session.flush()
    return TowerOut(id=tower.id, society_id=tower.society_id, name=tower.name)


def list_societies(
    session: Session, query: str | None, limit: int, offset: int, *, admin: bool = False
) -> SocietyPage:
    statement = select(Society)
    if not admin:
        statement = statement.where(Society.status == "active")
    if query:
        statement = statement.where(Society.name.icontains(query, autoescape=True))
    societies, total = _page(session, statement.order_by(Society.name, Society.id), limit, offset)
    return SocietyPage(
        items=[society_view(session, s) for s in societies], total=total, limit=limit, offset=offset
    )


def join_society(
    session: Session, user: User, society_id: UUID, data: MembershipJoin
) -> MembershipOut:
    # Refresh after acquiring the user lock: an administrator may have deactivated
    # the account while this request waited, even if authentication loaded it earlier.
    user = _locked_active_user(session, user.id)
    _locked(session, Society, society_id)
    require_active_society(session, society_id)
    tower = _get(session, Tower, data.tower_id)
    if tower.society_id != society_id:
        raise DomainError(422, "tower_society_mismatch", "Choose a tower in the selected society.")
    membership = session.scalar(
        select(Membership)
        .where(
            Membership.society_id == society_id,
            Membership.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if membership is not None and membership.status == "suspended":
        raise DomainError(
            403, "membership_suspended", "Your society membership is suspended. Contact support."
        )
    if membership is not None and membership.status == "active":
        if membership.tower_id != data.tower_id or membership.flat != data.flat:
            raise DomainError(
                409, "membership_exists", "Your membership already uses another tower or flat."
            )
        return membership_view(session, membership)
    if membership is None:
        membership = Membership(
            society_id=society_id,
            user_id=user.id,
            tower_id=tower.id,
            flat=data.flat,
            status="active",
        )
        session.add(membership)
    else:
        membership.tower_id = tower.id
        membership.flat = data.flat
        membership.status = "active"
    session.flush()
    return membership_view(session, membership)


def my_memberships(session: Session, user_id: UUID, limit: int, offset: int) -> list[MembershipOut]:
    rows, _ = _page(
        session,
        select(Membership)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at, Membership.id),
        limit,
        offset,
    )
    return [membership_view(session, m) for m in rows]


def list_memberships(
    session: Session, society_id: UUID | None, status: str | None, limit: int, offset: int
) -> MembershipPage:
    statement = select(Membership)
    if society_id:
        _get(session, Society, society_id)
        statement = statement.where(Membership.society_id == society_id)
    if status:
        statement = statement.where(Membership.status == status)
    rows, total = _page(
        session, statement.order_by(Membership.created_at, Membership.id), limit, offset
    )
    return MembershipPage(
        items=[membership_view(session, m, admin=True) for m in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def set_membership_status(session: Session, membership_id: UUID, status: str) -> MembershipAdminOut:
    membership = session.scalar(
        select(Membership).where(Membership.id == membership_id).with_for_update()
    )
    if membership is None:
        raise DomainError(404, "not_found", "Membership was not found.")
    if status == "active":
        require_active_society(session, membership.society_id)
        if not _get(session, User, membership.user_id).is_active:
            raise DomainError(409, "user_inactive", "An inactive account cannot be activated.")
    membership.status = status
    session.flush()
    if status == "suspended":
        kitchens = list(
            session.scalars(
                select(Kitchen)
                .join(KitchenMember)
                .where(
                    KitchenMember.user_id == membership.user_id,
                    Kitchen.society_id == membership.society_id,
                )
                .order_by(Kitchen.id)
                .with_for_update(key_share=True, of=Kitchen)
                .execution_options(populate_existing=True)
            )
        )
        for kitchen in kitchens:
            remaining_member = session.scalar(
                select(KitchenMember.user_id)
                .join(User, User.id == KitchenMember.user_id)
                .join(
                    Membership,
                    (Membership.user_id == KitchenMember.user_id)
                    & (Membership.society_id == kitchen.society_id),
                )
                .where(
                    KitchenMember.kitchen_id == kitchen.id,
                    KitchenMember.role == "owner",
                    Membership.status == "active",
                    User.is_active.is_(True),
                )
                .limit(1)
            )
            if remaining_member is None and kitchen.status != "suspended":
                kitchen.status = "suspended"
        session.flush()
    return membership_view(session, membership, admin=True)


def create_kitchen(session: Session, user: User, data: KitchenCreate) -> KitchenOwnOut:
    user = _locked_active_user(session, user.id)
    require_active_society(session, data.society_id)
    membership = require_membership(session, user.id, data.society_id)
    existing = session.scalar(
        select(Kitchen.id)
        .join(KitchenMember)
        .where(
            KitchenMember.user_id == user.id,
            Kitchen.society_id == data.society_id,
        )
        .limit(1)
    )
    if existing:
        raise DomainError(409, "kitchen_exists", "You already manage a kitchen in this society.")
    kitchen = Kitchen(
        **data.model_dump(), tower_id=membership.tower_id, flat=membership.flat, status="pending"
    )
    session.add(kitchen)
    session.flush()
    session.add(KitchenMember(kitchen_id=kitchen.id, user_id=user.id, role="owner"))
    session.flush()
    return kitchen_view(session, kitchen, private=True)


def update_kitchen(
    session: Session,
    user_id: UUID | None,
    kitchen_id: UUID,
    data: KitchenUpdate,
    *,
    admin: bool = False,
) -> KitchenOwnOut:
    kitchen = _require_kitchen_mutation(session, user_id, kitchen_id, admin=admin)
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "pickup_enabled", "delivery_enabled", "delivery_fee_paise"):
        if field in values and values[field] is None:
            raise DomainError(422, "required_field", f"{field} cannot be empty.")
    if not values.get("pickup_enabled", kitchen.pickup_enabled) and not values.get(
        "delivery_enabled", kitchen.delivery_enabled
    ):
        raise DomainError(422, "fulfillment_required", "Enable pickup or delivery.")
    if "fssai_number" in values and values["fssai_number"] != kitchen.fssai_number:
        kitchen.status = "pending"
    for field, value in values.items():
        setattr(kitchen, field, value)
    session.flush()
    return kitchen_view(session, kitchen, private=True)


def my_kitchens(session: Session, user_id: UUID, limit: int, offset: int) -> list[KitchenOwnOut]:
    statement = (
        select(Kitchen)
        .join(KitchenMember)
        .where(KitchenMember.user_id == user_id)
        .order_by(Kitchen.name, Kitchen.id)
    )
    rows, _ = _page(session, statement, limit, offset)
    return [kitchen_view(session, k, private=True) for k in rows]


def list_kitchens(
    session: Session, user_id: UUID, society_id: UUID, query: str | None, limit: int, offset: int
) -> KitchenPage:
    require_membership(session, user_id, society_id)
    require_active_society(session, society_id)
    statement = select(Kitchen).where(
        Kitchen.society_id == society_id, Kitchen.status == "approved"
    )
    if query:
        statement = statement.where(Kitchen.name.icontains(query, autoescape=True))
    rows, total = _page(session, statement.order_by(Kitchen.name, Kitchen.id), limit, offset)
    return KitchenPage(
        items=[kitchen_view(session, k) for k in rows], total=total, limit=limit, offset=offset
    )


def get_kitchen(session: Session, user_id: UUID, kitchen_id: UUID) -> KitchenOut:
    kitchen = _get(session, Kitchen, kitchen_id)
    require_membership(session, user_id, kitchen.society_id)
    require_active_society(session, kitchen.society_id)
    if kitchen.status != "approved":
        raise DomainError(404, "not_found", "Kitchen was not found.")
    return kitchen_view(session, kitchen)


def admin_kitchens(
    session: Session, society_id: UUID | None, status: str | None, limit: int, offset: int
) -> KitchenAdminPage:
    statement = select(Kitchen)
    if society_id:
        statement = statement.where(Kitchen.society_id == society_id)
    if status:
        statement = statement.where(Kitchen.status == status)
    rows, total = _page(session, statement.order_by(Kitchen.created_at, Kitchen.id), limit, offset)
    return KitchenAdminPage(
        items=[kitchen_view(session, k, private=True) for k in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def approve_kitchen(session: Session, kitchen_id: UUID, data: KitchenApprove) -> KitchenOwnOut:
    kitchen = session.scalar(
        select(Kitchen)
        .where(Kitchen.id == kitchen_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if kitchen is None:
        raise DomainError(404, "not_found", "Kitchen was not found.")
    require_active_society(session, kitchen.society_id)
    active_owner = session.scalar(
        select(KitchenMember.user_id)
        .join(User, User.id == KitchenMember.user_id)
        .join(
            Membership,
            (Membership.user_id == KitchenMember.user_id)
            & (Membership.society_id == kitchen.society_id),
        )
        .where(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.role == "owner",
            Membership.status == "active",
            User.is_active.is_(True),
        )
        .limit(1)
    )
    if active_owner is None:
        raise DomainError(
            409, "active_owner_required", "The kitchen must have an active resident owner."
        )
    kitchen.fssai_number = data.fssai_number
    kitchen.status = "approved"
    session.flush()
    return kitchen_view(session, kitchen, private=True)


def suspend_kitchen(session: Session, kitchen_id: UUID) -> KitchenOwnOut:
    kitchen = session.scalar(
        select(Kitchen)
        .where(Kitchen.id == kitchen_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if kitchen is None:
        raise DomainError(404, "not_found", "Kitchen was not found.")
    kitchen.status = "suspended"
    session.flush()
    return kitchen_view(session, kitchen, private=True)


def create_dish(
    session: Session,
    user_id: UUID | None,
    kitchen_id: UUID,
    data: DishCreate,
    *,
    admin: bool = False,
) -> DishOut:
    _require_kitchen_mutation(session, user_id, kitchen_id, admin=admin)
    dish = Dish(kitchen_id=kitchen_id, **data.model_dump(), is_active=True)
    session.add(dish)
    session.flush()
    return dish_view(dish)


def list_dishes(
    session: Session, user_id: UUID, kitchen_id: UUID, limit: int, offset: int
) -> list[DishOut]:
    require_kitchen_member(session, user_id, kitchen_id)
    rows, _ = _page(
        session,
        select(Dish)
        .where(Dish.kitchen_id == kitchen_id, Dish.is_active.is_(True))
        .order_by(Dish.name, Dish.id),
        limit,
        offset,
    )
    return [dish_view(d) for d in rows]


def update_dish(
    session: Session,
    user_id: UUID | None,
    dish_id: UUID,
    data: DishUpdate,
    *,
    admin: bool = False,
) -> DishOut:
    dish = _get(session, Dish, dish_id)
    _require_kitchen_mutation(session, user_id, dish.kitchen_id, admin=admin)
    if not dish.is_active and not admin:
        raise DomainError(409, "dish_archived", "This dish has been archived.")
    values = data.model_dump(exclude_unset=True)
    for field in ("name",):
        if field in values and values[field] is None:
            raise DomainError(422, "required_field", f"{field} cannot be empty.")
    for field, value in values.items():
        setattr(dish, field, value)
    session.flush()
    return dish_view(dish)


def archive_dish(session: Session, user_id: UUID | None, dish_id: UUID, *, admin: bool = False):
    dish = _get(session, Dish, dish_id)
    _require_kitchen_mutation(session, user_id, dish.kitchen_id, admin=admin)
    dish.is_active = False
    session.flush()


def _validate_listing(
    kitchen: Kitchen, values: dict, *, publishing: bool, cancelling: bool = False
):
    for field in ("available_from", "available_until", "order_cutoff"):
        value = values[field]
        if value is None or value.utcoffset() is None:
            raise DomainError(
                422, "timezone_required", "Ready times and cutoff must include a timezone."
            )
        values[field] = value.astimezone(UTC)
    if not values["available_from"] < values["available_until"]:
        raise DomainError(422, "invalid_ready_window", "Ready until must be after ready from.")
    if values["available_until"] - values["available_from"] > timedelta(days=1):
        raise DomainError(422, "invalid_ready_window", "A food listing can cover at most one day.")
    if values["order_cutoff"] > values["available_until"]:
        raise DomainError(
            422, "invalid_cutoff", "Orders must close by the end of the ready window."
        )
    if (
        values["available_from"].astimezone(ZoneInfo("Asia/Kolkata")).date()
        != values["service_date"]
    ):
        raise DomainError(
            422,
            "service_date_mismatch",
            "The ready time must start on the service date in India time.",
        )
    if not values["pickup_enabled"] and not values["delivery_enabled"]:
        raise DomainError(422, "fulfillment_required", "Enable pickup or delivery.")
    if not cancelling and (
        (values["pickup_enabled"] and not kitchen.pickup_enabled)
        or (values["delivery_enabled"] and not kitchen.delivery_enabled)
    ):
        raise DomainError(
            422, "fulfillment_unavailable", "Enable this fulfillment option on your kitchen first."
        )
    if publishing:
        if kitchen.status != "approved":
            raise DomainError(
                409,
                "kitchen_approval_required",
                "Your kitchen must be approved before publishing food.",
            )
        if values["order_cutoff"] <= utcnow():
            raise DomainError(422, "cutoff_passed", "Choose an order cutoff in the future.")


def create_listing(
    session: Session,
    user_id: UUID | None,
    kitchen_id: UUID,
    data: ListingCreate,
    *,
    admin: bool = False,
) -> ListingOut:
    kitchen = _require_kitchen_mutation(session, user_id, kitchen_id, admin=admin)
    if data.status == "published":
        require_active_society(session, kitchen.society_id)
    dish = _get(session, Dish, data.dish_id)
    if dish.kitchen_id != kitchen_id or not dish.is_active:
        raise DomainError(422, "dish_kitchen_mismatch", "Choose an active dish from your kitchen.")
    values = data.model_dump()
    _validate_listing(
        kitchen,
        values,
        publishing=data.status == "published",
    )
    listing = MenuListing(kitchen_id=kitchen_id, **values, quantity_reserved=0)
    session.add(listing)
    session.flush()
    return listing_view(session, listing)


def update_listing(
    session: Session,
    user_id: UUID | None,
    listing_id: UUID,
    data: ListingUpdate,
    *,
    admin: bool = False,
) -> ListingOut:
    listing = session.scalar(
        select(MenuListing)
        .where(MenuListing.id == listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if listing is None:
        raise DomainError(404, "not_found", "Listing was not found.")
    changes = data.model_dump(exclude_unset=True)
    cancelling = changes.get("status") == "cancelled"
    if cancelling:
        # Closing an existing menu does not require eligibility to sell new food.
        if admin:
            kitchen = _get(session, Kitchen, listing.kitchen_id)
        elif user_id is not None:
            kitchen = require_kitchen_member(session, user_id, listing.kitchen_id)
        else:
            raise DomainError(403, "kitchen_access_denied", "You do not manage this kitchen.")
    else:
        kitchen = _require_kitchen_mutation(session, user_id, listing.kitchen_id, admin=admin)
    if any(value is None for value in changes.values()):
        raise DomainError(422, "required_field", "Listing fields cannot be empty.")
    if listing.status == "cancelled":
        raise DomainError(
            409,
            "listing_cancelled",
            "A cancelled listing cannot be republished. Cook the dish again instead.",
        )
    if "quantity_total" in changes and changes["quantity_total"] < listing.quantity_reserved:
        raise DomainError(
            409, "reserved_inventory", "Quantity cannot be lower than portions already reserved."
        )
    if cancelling:
        live_order = session.scalar(
            select(OrderItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.menu_listing_id == listing_id,
                Order.status.in_(["pending", "accepted", "preparing", "ready"]),
            )
            .limit(1)
        )
        if live_order is not None:
            raise DomainError(
                409, "live_orders", "Resolve live orders before cancelling this listing."
            )
    if listing.quantity_reserved:
        fixed_fields = {
            "service_date",
            "price_paise",
            "available_from",
            "available_until",
            "order_cutoff",
            "pickup_enabled",
            "delivery_enabled",
        }
        if changes.get("status") == "draft":
            raise DomainError(
                409, "committed_listing", "A listing with reserved portions cannot return to draft."
            )
        if any(
            field in changes and changes[field] != getattr(listing, field) for field in fixed_fields
        ):
            raise DomainError(
                409,
                "committed_listing",
                "Price, timings and fulfillment cannot change after portions are reserved.",
            )
    values = {
        field: changes.get(field, getattr(listing, field))
        for field in ListingCreate.model_fields
        if field != "dish_id"
    }
    publishing = values["status"] == "published" and listing.status != "published"
    if publishing:
        require_active_society(session, kitchen.society_id)
        if not _get(session, Dish, listing.dish_id).is_active:
            raise DomainError(
                422, "dish_kitchen_mismatch", "Choose an active dish from your kitchen."
            )
    # Existing published menus remain editable for stock corrections after cutoff.
    _validate_listing(
        kitchen,
        values,
        publishing=publishing,
        cancelling=cancelling,
    )
    for field, value in values.items():
        setattr(listing, field, value)
    session.flush()
    return listing_view(session, listing)


def cancel_listing(
    session: Session, user_id: UUID | None, listing_id: UUID, *, admin: bool = False
):
    update_listing(session, user_id, listing_id, ListingUpdate(status="cancelled"), admin=admin)


def get_listing(session: Session, user_id: UUID, listing_id: UUID) -> ListingOut:
    listing = _get(session, MenuListing, listing_id)
    kitchen = _get(session, Kitchen, listing.kitchen_id)
    require_membership(session, user_id, kitchen.society_id)
    require_active_society(session, kitchen.society_id)
    dish = _get(session, Dish, listing.dish_id)
    if listing.status != "published" or kitchen.status != "approved" or not dish.is_active:
        raise DomainError(404, "not_found", "Listing was not found.")
    return listing_view(session, listing)


def list_listings(
    session: Session,
    user_id: UUID,
    society_id: UUID,
    start: date,
    end: date,
    limit: int,
    offset: int,
    *,
    kitchen_id: UUID | None = None,
    owned: bool = False,
) -> ListingPage:
    require_membership(session, user_id, society_id)
    if end < start or (end - start).days > 31:
        raise DomainError(422, "invalid_date_range", "Choose a date range of up to 31 days.")
    statement = (
        select(MenuListing)
        .join(Kitchen)
        .join(Dish, Dish.id == MenuListing.dish_id)
        .where(
            Kitchen.society_id == society_id,
            MenuListing.service_date >= start,
            MenuListing.service_date <= end,
        )
    )
    if kitchen_id:
        kitchen = _get(session, Kitchen, kitchen_id)
        if kitchen.society_id != society_id:
            raise DomainError(404, "not_found", "Kitchen was not found in this society.")
        statement = statement.where(Kitchen.id == kitchen_id)
    if owned:
        if kitchen_id is None:
            raise DomainError(422, "kitchen_required", "Choose the kitchen you manage.")
        require_kitchen_member(session, user_id, kitchen_id)
    else:
        require_active_society(session, society_id)
        statement = statement.where(
            Kitchen.status == "approved",
            MenuListing.status == "published",
            Dish.is_active.is_(True),
        )
    rows, total = _page(
        session, statement.order_by(MenuListing.available_from, MenuListing.id), limit, offset
    )
    return ListingPage(
        items=[listing_view(session, m) for m in rows], total=total, limit=limit, offset=offset
    )
