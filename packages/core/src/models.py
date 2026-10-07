"""MVP entities with explicit association objects and community-scoped references.

Memberships and kitchen memberships own writes to their many-to-many links.
Convenience user/community/kitchen collections are read-only. Historical orders
and their child records restrict parent deletion; lifecycle uses soft states.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from kitchen_core.community_types import CommunityType
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
    or_,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, foreign, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Entity, Base):
    __tablename__ = "users"
    oidc_subject: Mapped[str] = mapped_column(String(250), unique=True)
    oidc_issuer: Mapped[str] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", passive_deletes="all"
    )
    kitchen_memberships: Mapped[list[KitchenMember]] = relationship(
        back_populates="user", passive_deletes="all"
    )
    orders: Mapped[list[Order]] = relationship(back_populates="customer", passive_deletes="all")
    order_keys: Mapped[list[OrderIdempotency]] = relationship(
        back_populates="customer", passive_deletes="all"
    )
    order_events: Mapped[list[OrderEvent]] = relationship(
        back_populates="actor", passive_deletes="all"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", passive_deletes="all"
    )
    devices: Mapped[list[Device]] = relationship(back_populates="user", passive_deletes="all")
    communities: Mapped[list[Community]] = relationship(
        secondary="community_memberships", back_populates="users", viewonly=True
    )
    kitchens: Mapped[list[Kitchen]] = relationship(
        secondary="kitchen_members", back_populates="members", viewonly=True
    )


COMMUNITY_TYPES = tuple(item.slug for item in CommunityType)
ZONE_TYPES = ("tower", "area", "hostel", "block", "other")


class Community(Entity, Base):
    __tablename__ = "communities"
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    type: Mapped[str] = mapped_column(
        String(30), default="residential_society", server_default="residential_society"
    )
    __table_args__ = (
        CheckConstraint("status IN ('draft','active','paused')"),
        CheckConstraint("type IN " + str(COMMUNITY_TYPES), name="communities_type_check"),
    )

    zones: Mapped[list[CommunityZone]] = relationship(
        back_populates="community", passive_deletes="all"
    )
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="community", passive_deletes="all"
    )
    kitchens: Mapped[list[Kitchen]] = relationship(
        back_populates="community", passive_deletes="all"
    )
    orders: Mapped[list[Order]] = relationship(back_populates="community", passive_deletes="all")
    users: Mapped[list[User]] = relationship(
        secondary="community_memberships", back_populates="communities", viewonly=True
    )


class CommunityZone(Entity, Base):
    __tablename__ = "community_zones"
    parent_zone_id: Mapped[UUID | None] = mapped_column(Uuid)
    zone_type: Mapped[str] = mapped_column(String(20), default="other", server_default="other")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("community_id", "name"),
        CheckConstraint("zone_type IN " + str(ZONE_TYPES), name="community_zones_type_check"),
        CheckConstraint(
            "parent_zone_id IS NULL OR parent_zone_id != id", name="zone_not_self_parent"
        ),
        ForeignKeyConstraint(
            ["parent_zone_id", "community_id"],
            ["community_zones.id", "community_zones.community_id"],
            name="fk_zone_parent_community",
        ),
        UniqueConstraint("id", "community_id", name="uq_zones_id_community"),
    )

    community: Mapped[Community] = relationship(back_populates="zones")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="zone",
        primaryjoin=lambda: and_(
            CommunityZone.id == foreign(Membership.zone_id),
            CommunityZone.community_id == Membership.community_id,
        ),
        passive_deletes="all",
    )
    kitchens: Mapped[list[Kitchen]] = relationship(
        back_populates="zone",
        primaryjoin=lambda: and_(
            CommunityZone.id == foreign(Kitchen.zone_id),
            CommunityZone.community_id == Kitchen.community_id,
        ),
        passive_deletes="all",
    )


class Membership(Entity, Base):
    __tablename__ = "community_memberships"
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    zone_id: Mapped[UUID | None] = mapped_column(Uuid)
    address_label: Mapped[str | None] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    __table_args__ = (
        UniqueConstraint("community_id", "user_id"),
        CheckConstraint(
            "status IN ('active','suspended')", name="community_memberships_status_check"
        ),
        ForeignKeyConstraint(
            ["zone_id", "community_id"],
            ["community_zones.id", "community_zones.community_id"],
            name="fk_membership_zone_community",
        ),
    )

    community: Mapped[Community] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    zone: Mapped[CommunityZone | None] = relationship(
        back_populates="memberships",
        primaryjoin=lambda: and_(
            foreign(Membership.zone_id) == CommunityZone.id,
            Membership.community_id == CommunityZone.community_id,
        ),
    )


class Kitchen(Entity, Base):
    __tablename__ = "kitchens"
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    zone_id: Mapped[UUID | None] = mapped_column(Uuid)
    address_label: Mapped[str | None] = mapped_column(String(250))
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    upi_id: Mapped[str | None] = mapped_column(String(150))
    fssai_number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    is_accepting_orders: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pause_reason: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','suspended')"),
        CheckConstraint("pickup_enabled OR delivery_enabled"),
        CheckConstraint("delivery_fee_paise >= 0"),
        UniqueConstraint("id", "community_id", name="uq_kitchens_id_community"),
        ForeignKeyConstraint(
            ["zone_id", "community_id"],
            ["community_zones.id", "community_zones.community_id"],
            name="fk_kitchen_zone_community",
        ),
    )

    community: Mapped[Community] = relationship(back_populates="kitchens")
    zone: Mapped[CommunityZone | None] = relationship(
        back_populates="kitchens",
        primaryjoin=lambda: and_(
            foreign(Kitchen.zone_id) == CommunityZone.id,
            Kitchen.community_id == CommunityZone.community_id,
        ),
    )
    memberships: Mapped[list[KitchenMember]] = relationship(
        back_populates="kitchen", passive_deletes="all"
    )
    members: Mapped[list[User]] = relationship(
        secondary="kitchen_members", back_populates="kitchens", viewonly=True
    )
    dishes: Mapped[list[Dish]] = relationship(back_populates="kitchen", passive_deletes="all")
    listings: Mapped[list[MenuListing]] = relationship(
        back_populates="kitchen", passive_deletes="all"
    )
    orders: Mapped[list[Order]] = relationship(
        back_populates="kitchen",
        primaryjoin=lambda: and_(
            Kitchen.id == foreign(Order.kitchen_id), Kitchen.community_id == Order.community_id
        ),
        passive_deletes="all",
    )


class KitchenFollow(Base):
    __tablename__ = "kitchen_follows"
    kitchen_id: Mapped[UUID] = mapped_column(ForeignKey("kitchens.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    notify_new_menu: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KitchenMember(Base):
    __tablename__ = "kitchen_members"
    kitchen_id: Mapped[UUID] = mapped_column(ForeignKey("kitchens.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")
    __table_args__ = (CheckConstraint("role IN ('owner','manager')"),)

    user: Mapped[User] = relationship(back_populates="kitchen_memberships")
    kitchen: Mapped[Kitchen] = relationship(back_populates="memberships")


class Dish(Entity, Base):
    __tablename__ = "dishes"
    kitchen_id: Mapped[UUID] = mapped_column(ForeignKey("kitchens.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("id", "kitchen_id", name="uq_dishes_id_kitchen"),)

    kitchen: Mapped[Kitchen] = relationship(back_populates="dishes")
    listings: Mapped[list[MenuListing]] = relationship(
        back_populates="dish",
        primaryjoin=lambda: and_(
            Dish.id == foreign(MenuListing.dish_id), Dish.kitchen_id == MenuListing.kitchen_id
        ),
        passive_deletes="all",
    )


class MenuListing(Entity, Base):
    __tablename__ = "menu_listings"
    kitchen_id: Mapped[UUID] = mapped_column(ForeignKey("kitchens.id"), index=True)
    dish_id: Mapped[UUID] = mapped_column(Uuid)
    service_date: Mapped[date] = mapped_column(Date)
    available_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_paise: Mapped[int] = mapped_column(Integer)
    quantity_total: Mapped[int] = mapped_column(Integer)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="published")
    __table_args__ = (
        UniqueConstraint("id", "kitchen_id", name="uq_listings_id_kitchen"),
        Index("ix_listings_feed", "service_date", "status", "kitchen_id"),
        CheckConstraint("status IN ('draft','published','cancelled')"),
        CheckConstraint("price_paise >= 0"),
        CheckConstraint("quantity_total > 0"),
        CheckConstraint("quantity_reserved >= 0 AND quantity_reserved <= quantity_total"),
        CheckConstraint("available_from < available_until"),
        CheckConstraint("order_cutoff <= available_until"),
        CheckConstraint("pickup_enabled OR delivery_enabled"),
        ForeignKeyConstraint(
            ["dish_id", "kitchen_id"],
            ["dishes.id", "dishes.kitchen_id"],
            name="fk_listing_dish_kitchen",
        ),
    )

    kitchen: Mapped[Kitchen] = relationship(back_populates="listings")
    dish: Mapped[Dish] = relationship(
        back_populates="listings",
        primaryjoin=lambda: and_(
            foreign(MenuListing.dish_id) == Dish.id, MenuListing.kitchen_id == Dish.kitchen_id
        ),
    )
    order_items: Mapped[list[OrderItem]] = relationship(
        back_populates="listing", passive_deletes="all"
    )


class Order(Entity, Base):
    __tablename__ = "orders"
    order_number: Mapped[int] = mapped_column(BigInteger, Identity(start=1001), unique=True)
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"))
    kitchen_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    fulfillment_type: Mapped[str] = mapped_column(String(20))
    customer_note: Mapped[str | None] = mapped_column(String(1000))
    pickup_point_id: Mapped[UUID | None] = mapped_column(Uuid)
    fulfillment_snapshot: Mapped[dict | None] = mapped_column(JSON)
    pickup_address: Mapped[dict | None] = mapped_column(JSON)
    delivery_address: Mapped[dict | None] = mapped_column(JSON)
    available_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid")
    upi_id: Mapped[str | None] = mapped_column(String(150))
    __table_args__ = (
        ForeignKeyConstraint(
            ["pickup_point_id", "community_id"],
            ["pickup_points.id", "pickup_points.community_id"],
            name="fk_order_pickup_community",
        ),
        CheckConstraint(
            "fulfillment_type = 'pickup' OR pickup_point_id IS NULL",
            name="order_delivery_no_pickup",
        ),
        Index("ix_orders_kitchen_status", "kitchen_id", "status", "created_at"),
        CheckConstraint(
            "status IN ('pending','accepted','preparing','ready','completed',"
            "'rejected','cancelled','expired')"
        ),
        CheckConstraint("fulfillment_type IN ('pickup','delivery')"),
        CheckConstraint("payment_status IN ('unpaid','customer_reported','kitchen_confirmed')"),
        CheckConstraint("subtotal_paise >= 0 AND delivery_fee_paise >= 0"),
        CheckConstraint("total_paise = subtotal_paise + delivery_fee_paise"),
        UniqueConstraint("id", "customer_id", name="uq_orders_id_customer"),
        ForeignKeyConstraint(
            ["kitchen_id", "community_id"],
            ["kitchens.id", "kitchens.community_id"],
            name="fk_order_kitchen_community",
        ),
    )

    community: Mapped[Community] = relationship(back_populates="orders")
    kitchen: Mapped[Kitchen] = relationship(
        back_populates="orders",
        primaryjoin=lambda: and_(
            foreign(Order.kitchen_id) == Kitchen.id, Order.community_id == Kitchen.community_id
        ),
    )
    customer: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", passive_deletes="all")
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order",
        order_by="(OrderEvent.created_at, OrderEvent.id)",
        passive_deletes="all",
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="order", passive_deletes="all"
    )
    idempotency: Mapped[OrderIdempotency | None] = relationship(
        back_populates="order",
        primaryjoin=lambda: and_(
            Order.id == foreign(OrderIdempotency.order_id),
            Order.customer_id == OrderIdempotency.customer_id,
        ),
        passive_deletes="all",
    )


class OrderItem(Entity, Base):
    __tablename__ = "order_items"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_listing_id: Mapped[UUID] = mapped_column(ForeignKey("menu_listings.id"))
    dish_name: Mapped[str] = mapped_column(String(150))
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    total_paise: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("order_id", "menu_listing_id"),
        CheckConstraint("quantity > 0 AND unit_price_paise >= 0"),
        CheckConstraint("total_paise = quantity * unit_price_paise"),
    )

    order: Mapped[Order] = relationship(back_populates="items")
    listing: Mapped[MenuListing] = relationship(back_populates="order_items")


class OrderIdempotency(Base):
    __tablename__ = "order_idempotency"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    hash_version: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    order_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "customer_id"],
            ["orders.id", "orders.customer_id"],
            name="fk_idempotency_order_customer",
        ),
    )

    customer: Mapped[User] = relationship(back_populates="order_keys")
    order: Mapped[Order] = relationship(
        back_populates="idempotency",
        primaryjoin=lambda: and_(
            foreign(OrderIdempotency.order_id) == Order.id,
            OrderIdempotency.customer_id == Order.customer_id,
        ),
    )


class OrderEvent(Entity, Base):
    __tablename__ = "order_events"
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(500))

    order: Mapped[Order] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship(back_populates="order_events")


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="notifications")
    order: Mapped[Order] = relationship(back_populates="notifications")


class Device(Entity, Base):
    __tablename__ = "devices"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    session_key: Mapped[str] = mapped_column(String(200))
    push_token: Mapped[str] = mapped_column(String(250), unique=True)
    platform: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="devices")


class PickupPoint(Entity, Base):
    __tablename__ = "pickup_points"
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id"), index=True)
    kitchen_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    zone_id: Mapped[UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(150))
    address_label: Mapped[str] = mapped_column(String(250))
    instructions: Mapped[str | None] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    __table_args__ = (
        UniqueConstraint("id", "community_id", name="uq_pickup_points_id_community"),
        ForeignKeyConstraint(
            ["zone_id", "community_id"],
            ["community_zones.id", "community_zones.community_id"],
            name="fk_pickup_zone_community",
        ),
        ForeignKeyConstraint(
            ["kitchen_id", "community_id"],
            ["kitchens.id", "kitchens.community_id"],
            name="fk_pickup_kitchen_community",
        ),
    )


class ListingPickupPoint(Base):
    __tablename__ = "listing_pickup_points"
    listing_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    pickup_point_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kitchen_id: Mapped[UUID] = mapped_column(Uuid)
    community_id: Mapped[UUID] = mapped_column(Uuid)
    __table_args__ = (
        ForeignKeyConstraint(
            ["listing_id", "kitchen_id"],
            ["menu_listings.id", "menu_listings.kitchen_id"],
            name="fk_listing_pickup_listing",
        ),
        ForeignKeyConstraint(
            ["kitchen_id", "community_id"],
            ["kitchens.id", "kitchens.community_id"],
            name="fk_listing_pickup_kitchen",
        ),
        ForeignKeyConstraint(
            ["pickup_point_id", "community_id"],
            ["pickup_points.id", "pickup_points.community_id"],
            name="fk_listing_pickup_point",
        ),
    )


def eligible_pickup_point():
    """A point is usable when active and either unzoned or in its active community zone."""
    active_zone = (
        select(CommunityZone.id)
        .where(
            CommunityZone.id == PickupPoint.zone_id,
            CommunityZone.community_id == PickupPoint.community_id,
            CommunityZone.active.is_(True),
        )
        .exists()
    )
    return and_(PickupPoint.active.is_(True), or_(PickupPoint.zone_id.is_(None), active_zone))
