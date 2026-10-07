"""Transactional inventory reservation and the order state machine.

The caller owns the database transaction. Inventory changes, order events and
notifications commit together; this module never sends external notifications.
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from kitchen_core import catalog
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Community,
    CommunityZone,
    Dish,
    Kitchen,
    KitchenMember,
    ListingPickupPoint,
    Membership,
    MenuListing,
    Notification,
    Order,
    OrderEvent,
    OrderIdempotency,
    OrderItem,
    PickupPoint,
    User,
    eligible_pickup_point,
)
from kitchen_core.order_schemas import (
    AddressSnapshot,
    FulfillmentGroup,
    FulfillmentType,
    OrderCreate,
    OrderEventOut,
    OrderItemOut,
    OrderOut,
    OrderPage,
    PaymentStatus,
)
from kitchen_core.settings import get_settings
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

TRANSITIONS = {
    "accept": ({"pending"}, "accepted"),
    "reject": ({"pending"}, "rejected"),
    "prepare": ({"accepted"}, "preparing"),
    "ready": ({"preparing"}, "ready"),
    "complete": ({"ready"}, "completed"),
    "cancel": ({"pending", "accepted"}, "cancelled"),
}
PAYABLE_STATUSES = {"accepted", "preparing", "ready", "completed"}
RELEASE_STATUSES = {"rejected", "cancelled", "expired"}


def utcnow() -> datetime:
    return datetime.now(UTC)


def combined_items(payload: OrderCreate) -> dict[UUID, int]:
    quantities: dict[UUID, int] = defaultdict(int)
    for item in payload.items:
        quantities[item.menu_listing_id] += item.quantity
    return dict(sorted(quantities.items(), key=lambda item: str(item[0])))


def request_hash(payload: OrderCreate, *, version: int = 2) -> str:
    canonical: dict[str, Any] = {
        "items": [
            {"menu_listing_id": str(listing_id), "quantity": quantity}
            for listing_id, quantity in combined_items(payload).items()
        ],
        "fulfillment_type": payload.fulfillment_type,
        "customer_note": payload.customer_note or None,
    }
    if version >= 2:
        canonical["pickup_point_id"] = (
            str(payload.pickup_point_id) if payload.pickup_point_id else None
        )
        canonical["delivery_address"] = (
            payload.delivery_address.model_dump(mode="json") if payload.delivery_address else None
        )
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _active_membership(session: Session, user_id: UUID, community_id: UUID) -> Membership:
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.community_id == community_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise DomainError(
            403, "community_access_denied", "Active community membership is required."
        )
    return membership


def _kitchen_access(session: Session, user_id: UUID, kitchen_id: UUID) -> Kitchen:
    kitchen = session.get(Kitchen, kitchen_id)
    if kitchen is None or session.get(KitchenMember, (kitchen_id, user_id)) is None:
        raise DomainError(404, "kitchen_not_found", "Kitchen not found.")
    _active_membership(session, user_id, kitchen.community_id)
    return kitchen


def _locked_order(session: Session, order_id: UUID) -> Order:
    order = session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise DomainError(404, "order_not_found", "Order not found.")
    return order


def _order_items(session: Session, order_id: UUID) -> list[OrderItem]:
    return list(
        session.scalars(
            select(OrderItem)
            .where(OrderItem.order_id == order_id)
            .order_by(OrderItem.created_at, OrderItem.id)
        )
    )


def _notify(session: Session, order: Order, user_ids: list[UUID], kind: str) -> None:
    for user_id in set(user_ids):
        session.add(
            Notification(
                user_id=user_id,
                order_id=order.id,
                kind=kind,
                payload={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "status": order.status,
                    "kitchen_name": order.kitchen.name,
                    "payment_status": order.payment_status,
                },
            )
        )


def _kitchen_user_ids(session: Session, kitchen_id: UUID) -> list[UUID]:
    return list(
        session.scalars(
            select(KitchenMember.user_id)
            .join(Kitchen, Kitchen.id == KitchenMember.kitchen_id)
            .join(
                Membership,
                and_(
                    Membership.user_id == KitchenMember.user_id,
                    Membership.community_id == Kitchen.community_id,
                ),
            )
            .join(User, User.id == KitchenMember.user_id)
            .where(
                KitchenMember.kitchen_id == kitchen_id,
                Membership.status == "active",
                User.is_active.is_(True),
            )
        )
    )


def _status_event(
    session: Session,
    order: Order,
    actor_id: UUID | None,
    reason: str | None = None,
    now: datetime | None = None,
) -> None:
    session.add(
        OrderEvent(
            order_id=order.id,
            status=order.status,
            actor_id=actor_id,
            reason=reason,
            created_at=now or utcnow(),
        )
    )
    _notify(session, order, [order.customer_id], "order_status")
    if order.status in {"cancelled", "expired"}:
        _notify(session, order, _kitchen_user_ids(session, order.kitchen_id), "order_status")


def _snapshot_address(
    session: Session, community: Community, zone_id: UUID | None, address_label: str | None
) -> dict:
    catalog.validate_zone(session, community.id, zone_id)
    zone = session.get(CommunityZone, zone_id) if zone_id else None
    return {
        "version": 2,
        "community_name": community.name,
        "address": community.address,
        "city": community.city,
        "postal_code": community.postal_code,
        "zone_name": zone.name if zone else None,
        "address_label": address_label,
    }


def _read_snapshot(value: dict | None) -> AddressSnapshot | None:
    if value is None:
        return None
    if "society_name" in value:
        value = {
            **value,
            "version": 1,
            "community_name": value["society_name"],
            "zone_name": value.get("tower_name"),
            "address_label": value.get("flat"),
        }
    return AddressSnapshot.model_validate(value)


def serialize_order(session: Session, order: Order) -> OrderOut:
    session.flush()
    events = list(
        session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.created_at, OrderEvent.id)
        )
    )
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        community_id=order.community_id,
        kitchen_id=order.kitchen_id,
        customer_id=order.customer_id,
        kitchen_name=order.kitchen.name,
        customer_name=order.customer.name or "Member",
        status=order.status,
        payment_status=cast(PaymentStatus, order.payment_status),
        upi_id=order.upi_id if order.status in PAYABLE_STATUSES else None,
        fulfillment_type=cast(FulfillmentType, order.fulfillment_type),
        customer_note=order.customer_note,
        rejection_reason=next(
            (event.reason for event in reversed(events) if event.status == "rejected"), None
        ),
        items=[
            OrderItemOut(
                menu_listing_id=item.menu_listing_id,
                dish_name=item.dish_name,
                unit_price_paise=item.unit_price_paise,
                quantity=item.quantity,
                total_paise=item.total_paise,
            )
            for item in _order_items(session, order.id)
        ],
        subtotal_paise=order.subtotal_paise,
        delivery_fee_paise=order.delivery_fee_paise,
        total_paise=order.total_paise,
        available_from=order.available_from,
        available_until=order.available_until,
        pickup_point_id=order.pickup_point_id,
        fulfillment_snapshot=cast(
            AddressSnapshot,
            _read_snapshot(
                order.fulfillment_snapshot
                or (
                    order.pickup_address
                    if order.fulfillment_type == "pickup"
                    else order.delivery_address
                )
            ),
        ),
        pickup_address=_read_snapshot(order.pickup_address),
        delivery_address=_read_snapshot(order.delivery_address),
        expires_at=order.expires_at,
        created_at=order.created_at,
        updated_at=events[-1].created_at if events else order.created_at,
        events=[
            OrderEventOut(status=event.status, reason=event.reason, created_at=event.created_at)
            for event in events
        ],
    )


def create_order(
    session: Session,
    user: User,
    payload: OrderCreate,
    idempotency_key: str,
    *,
    admin: bool = False,
) -> OrderOut:
    idempotency_key = idempotency_key.strip()
    if not idempotency_key or len(idempotency_key) > 120:
        raise DomainError(422, "invalid_idempotency_key", "Provide a non-empty Idempotency-Key.")
    # NO KEY UPDATE serializes this customer's requests while allowing the
    # KEY SHARE locks taken by order/notification foreign-key inserts. FOR
    # UPDATE would deadlock with expiry or owners ordering from each other.
    locked_user = session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if locked_user is None or not locked_user.is_active:
        raise DomainError(403, "account_inactive", "This account cannot place orders.")
    digest = request_hash(payload)
    previous = session.get(OrderIdempotency, (user.id, idempotency_key))
    if previous is not None:
        # Legacy keys were created before fulfillment destinations were request fields.
        if previous.hash_version == 1 and (payload.pickup_point_id or payload.delivery_address):
            raise DomainError(
                409, "idempotency_conflict", "This key was used for a different order."
            )
        if previous.request_hash != request_hash(payload, version=previous.hash_version):
            raise DomainError(
                409, "idempotency_conflict", "This key was used for a different order."
            )
        previous_order = session.get(Order, previous.order_id)
        if previous_order is None:
            raise DomainError(409, "order_unavailable", "The previous order is unavailable.")
        return serialize_order(session, previous_order)

    quantities = combined_items(payload)
    if any(quantity > 100 for quantity in quantities.values()):
        raise DomainError(422, "quantity_limit", "Choose at most 100 portions of each dish.")
    listings = list(
        session.scalars(
            select(MenuListing)
            .where(MenuListing.id.in_(quantities))
            .order_by(MenuListing.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(listings) != len(quantities):
        raise DomainError(404, "listing_not_found", "One of these dishes is unavailable.")
    if len({listing.kitchen_id for listing in listings}) != 1:
        raise DomainError(422, "mixed_kitchens", "Place a separate order for each kitchen.")
    kitchen = session.get(Kitchen, listings[0].kitchen_id)
    if kitchen is None:
        raise DomainError(404, "kitchen_not_found", "Kitchen not found.")
    community = session.get(Community, kitchen.community_id)
    if community is None:
        raise DomainError(404, "community_not_found", "Community not found.")
    membership = _active_membership(session, user.id, kitchen.community_id)
    if kitchen.status != "approved" or community.status != "active":
        raise DomainError(409, "kitchen_unavailable", "This kitchen is not accepting orders.")
    if (
        len({(item.service_date, item.available_from, item.available_until) for item in listings})
        != 1
    ):
        raise DomainError(
            422, "mixed_service_windows", "Order dishes from the same ready window together."
        )
    fulfillment = payload.fulfillment_type
    if not getattr(kitchen, f"{fulfillment}_enabled"):
        raise DomainError(409, "fulfillment_unavailable", "This fulfillment option is unavailable.")

    point = None
    if fulfillment == "pickup":
        offered = None
        for listing in listings:
            ids = set(
                session.scalars(
                    select(ListingPickupPoint.pickup_point_id).where(
                        ListingPickupPoint.listing_id == listing.id
                    )
                )
            )
            offered = ids if offered is None else offered & ids
        offered = offered or set()
        selected = payload.pickup_point_id
        # A sole offered active point is the implicit selection for a simple checkout.
        if selected is None:
            active_ids = list(
                session.scalars(
                    select(PickupPoint.id).where(
                        PickupPoint.id.in_(offered), eligible_pickup_point()
                    )
                )
            )
            if len(active_ids) != 1:
                raise DomainError(422, "pickup_point_required", "Choose a pickup point.")
            selected = active_ids[0]
        if selected not in offered:
            raise DomainError(
                422, "pickup_point_unavailable", "This point is not offered by every listing."
            )
        point = session.scalar(
            select(PickupPoint)
            .where(PickupPoint.id == selected, eligible_pickup_point())
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if point is None or not point.active or point.community_id != community.id:
            raise DomainError(409, "pickup_point_unavailable", "This pickup point is unavailable.")
        snapshot = _snapshot_address(session, community, point.zone_id, point.address_label)
        snapshot.update(name=point.name, instructions=point.instructions)
    else:
        destination = payload.delivery_address
        zone_id = destination.zone_id if destination else membership.zone_id
        address_label = destination.address_label if destination else membership.address_label
        if not address_label:
            raise DomainError(422, "delivery_address_required", "Provide a home delivery address.")
        snapshot = _snapshot_address(session, community, zone_id, address_label)

    now = utcnow()
    subtotal = 0
    dishes = {}
    for listing in listings:
        if listing.status != "published" or listing.order_cutoff <= now:
            raise DomainError(409, "orders_closed", "Orders have closed for one of these dishes.")
        if not getattr(listing, f"{fulfillment}_enabled"):
            raise DomainError(
                409, "fulfillment_unavailable", "This fulfillment option is unavailable."
            )
        if listing.quantity_total - listing.quantity_reserved < quantities[listing.id]:
            raise DomainError(
                409, "insufficient_quantity", "There are not enough portions remaining."
            )
        dish = session.get(Dish, listing.dish_id)
        if dish is None or not dish.is_active or dish.kitchen_id != kitchen.id:
            raise DomainError(409, "dish_unavailable", "One of these dishes is unavailable.")
        dishes[listing.id] = dish
        subtotal += listing.price_paise * quantities[listing.id]
    delivery_fee = kitchen.delivery_fee_paise if fulfillment == "delivery" else 0
    if subtotal + delivery_fee > 2_147_483_647:
        raise DomainError(422, "order_total_limit", "The order total exceeds the supported limit.")
    order = Order(
        community_id=community.id,
        kitchen_id=kitchen.id,
        customer_id=user.id,
        status="pending",
        fulfillment_type=fulfillment,
        customer_note=payload.customer_note or None,
        pickup_point_id=point.id if point else None,
        fulfillment_snapshot=snapshot,
        pickup_address=snapshot if fulfillment == "pickup" else None,
        delivery_address=snapshot if fulfillment == "delivery" else None,
        available_from=listings[0].available_from,
        available_until=listings[0].available_until,
        expires_at=min(
            now + timedelta(minutes=get_settings().pending_order_minutes),
            *(item.order_cutoff for item in listings),
        ),
        subtotal_paise=subtotal,
        delivery_fee_paise=delivery_fee,
        total_paise=subtotal + delivery_fee,
        payment_status="unpaid",
        upi_id=kitchen.upi_id,
        created_at=now,
    )
    session.add(order)
    session.flush()
    for listing in listings:
        quantity = quantities[listing.id]
        listing.quantity_reserved += quantity
        session.add(
            OrderItem(
                order_id=order.id,
                menu_listing_id=listing.id,
                dish_name=dishes[listing.id].name,
                unit_price_paise=listing.price_paise,
                quantity=quantity,
                total_paise=listing.price_paise * quantity,
            )
        )
    session.add(
        OrderIdempotency(
            customer_id=user.id, key=idempotency_key, request_hash=digest, order_id=order.id
        )
    )
    session.add(
        OrderEvent(
            order_id=order.id,
            status="pending",
            actor_id=None if admin else user.id,
            created_at=now,
        )
    )
    _notify(session, order, _kitchen_user_ids(session, kitchen.id), "new_order")
    return serialize_order(session, order)


def _release_inventory(session: Session, order: Order) -> None:
    items = _order_items(session, order.id)
    quantities = {item.menu_listing_id: item.quantity for item in items}
    listings = list(
        session.scalars(
            select(MenuListing)
            .where(MenuListing.id.in_(quantities))
            .order_by(MenuListing.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for listing in listings:
        listing.quantity_reserved -= quantities[listing.id]


def get_order(
    session: Session, user: User | None, order_id: UUID, *, admin: bool = False
) -> OrderOut:
    order = session.get(Order, order_id)
    if order is None:
        raise DomainError(404, "order_not_found", "Order not found.")
    if not admin and user is None:
        raise DomainError(404, "order_not_found", "Order not found.")
    if not admin and user is not None and order.customer_id != user.id:
        try:
            _kitchen_access(session, user.id, order.kitchen_id)
        except DomainError:
            raise DomainError(404, "order_not_found", "Order not found.") from None
    return serialize_order(session, order)


def _page(session: Session, condition, limit: int, offset: int) -> OrderPage:
    total = session.scalar(select(func.count()).select_from(Order).where(condition)) or 0
    rows = session.scalars(
        select(Order)
        .where(condition)
        .order_by(Order.created_at.desc(), Order.id)
        .limit(limit)
        .offset(offset)
    )
    return OrderPage(
        items=[serialize_order(session, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def list_customer_orders(
    session: Session, user: User, limit: int = 20, offset: int = 0
) -> OrderPage:
    return _page(session, Order.customer_id == user.id, limit, offset)


def list_kitchen_orders(
    session: Session, user: User, kitchen_id: UUID, limit: int = 20, offset: int = 0
) -> OrderPage:
    _kitchen_access(session, user.id, kitchen_id)
    return _page(session, Order.kitchen_id == kitchen_id, limit, offset)


def transition_order(
    session: Session,
    user: User | None,
    order_id: UUID,
    action: str,
    reason: str | None = None,
    *,
    admin: bool = False,
) -> OrderOut:
    order = _locked_order(session, order_id)
    if not admin:
        if user is None:
            raise DomainError(404, "order_not_found", "Order not found.")
        if action == "cancel":
            if order.customer_id != user.id:
                raise DomainError(404, "order_not_found", "Order not found.")
        else:
            try:
                _kitchen_access(session, user.id, order.kitchen_id)
            except DomainError:
                raise DomainError(404, "order_not_found", "Order not found.") from None
    sources, destination = TRANSITIONS[action]
    if order.status == destination:
        return serialize_order(session, order)
    if order.status not in sources:
        raise DomainError(409, "invalid_order_transition", "This action is no longer available.")
    now = utcnow()
    if action == "accept" and order.expires_at <= now:
        raise DomainError(409, "order_expired", "The acceptance window has ended.")
    if action == "reject" and not reason:
        raise DomainError(422, "rejection_reason_required", "Give the customer a short reason.")
    if destination in RELEASE_STATUSES:
        _release_inventory(session, order)
    order.status = destination
    _status_event(session, order, None if admin or user is None else user.id, reason, now)
    return serialize_order(session, order)


def expire_order(session: Session, order: Order | UUID, now: datetime | None = None) -> bool:
    """Expire a due pending order, atomically releasing its portions once."""
    order = _locked_order(session, order.id if isinstance(order, Order) else order)
    now = now or utcnow()
    if order.status != "pending" or order.expires_at > now:
        return False
    _release_inventory(session, order)
    order.status = "expired"
    _status_event(session, order, None, "The kitchen did not accept before the deadline.", now)
    session.flush()
    return True


def record_payment(
    session: Session,
    user: User | None,
    order_id: UUID,
    action: str,
    *,
    admin: bool = False,
) -> OrderOut:
    order = _locked_order(session, order_id)
    if not admin:
        if user is None:
            raise DomainError(404, "order_not_found", "Order not found.")
        if action == "report":
            if order.customer_id != user.id:
                raise DomainError(404, "order_not_found", "Order not found.")
        else:
            try:
                _kitchen_access(session, user.id, order.kitchen_id)
            except DomainError:
                raise DomainError(404, "order_not_found", "Order not found.") from None
    if order.status not in PAYABLE_STATUSES:
        raise DomainError(
            409, "payment_unavailable", "Record payment after the kitchen accepts your order."
        )
    if order.payment_status == "kitchen_confirmed":
        return serialize_order(session, order)
    if action == "report" and order.payment_status == "customer_reported":
        return serialize_order(session, order)
    order.payment_status = "customer_reported" if action == "report" else "kitchen_confirmed"
    session.add(
        OrderEvent(
            order_id=order.id,
            status=order.status,
            actor_id=None if admin or user is None else user.id,
            reason=order.payment_status,
        )
    )
    recipients = (
        _kitchen_user_ids(session, order.kitchen_id) if action == "report" else [order.customer_id]
    )
    _notify(session, order, recipients, "payment_status")
    return serialize_order(session, order)


def fulfillment_groups(
    session: Session,
    user: User | None,
    kitchen_id: UUID,
    service_date: date,
    *,
    admin: bool = False,
) -> list[FulfillmentGroup]:
    """Accepted, uncompleted orders grouped by agreed collection/delivery destination."""
    if admin:
        catalog._get(session, Kitchen, kitchen_id)
    else:
        if user is None:
            raise DomainError(403, "kitchen_access_denied", "Sign in to manage this kitchen.")
        _kitchen_access(session, user.id, kitchen_id)
    start = datetime.combine(service_date, time.min, tzinfo=ZoneInfo("Asia/Kolkata"))
    portions = (
        select(func.sum(OrderItem.quantity)).where(OrderItem.order_id == Order.id).scalar_subquery()
    )
    rows = session.execute(
        select(Order, portions)
        .where(
            Order.kitchen_id == kitchen_id,
            Order.status.in_(["accepted", "preparing", "ready"]),
            Order.available_from >= start,
            Order.available_from < start + timedelta(days=1),
        )
        .order_by(Order.available_from, Order.created_at, Order.id)
    )
    groups: dict[tuple, FulfillmentGroup] = {}
    for order, quantity in rows:
        snapshot = _read_snapshot(
            order.fulfillment_snapshot
            or (
                order.pickup_address
                if order.fulfillment_type == "pickup"
                else order.delivery_address
            )
        )
        if snapshot is None:
            raise DomainError(409, "invalid_address", "This order has no fulfillment address.")
        key = (
            order.available_from,
            order.available_until,
            order.fulfillment_type,
            order.pickup_point_id,
            snapshot.model_dump_json(),
        )
        if key not in groups:
            groups[key] = FulfillmentGroup(
                fulfillment_type=order.fulfillment_type,
                pickup_point_id=order.pickup_point_id,
                fulfillment_snapshot=snapshot,
                available_from=order.available_from,
                available_until=order.available_until,
                order_count=0,
                portion_count=0,
                order_ids=[],
            )
        group = groups[key]
        group.order_count += 1
        group.portion_count += quantity or 0
        group.order_ids.append(order.id)
    return list(groups.values())
