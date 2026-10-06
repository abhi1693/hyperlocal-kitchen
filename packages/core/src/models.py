"""MVP entities with explicit association objects and society-scoped references.

Memberships and kitchen memberships own writes to their many-to-many links.
Convenience user/society/kitchen collections are read-only. Historical orders
and their child records restrict parent deletion; lifecycle uses soft states.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

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
    societies: Mapped[list[Society]] = relationship(
        secondary="society_memberships", back_populates="users", viewonly=True
    )
    kitchens: Mapped[list[Kitchen]] = relationship(
        secondary="kitchen_members", back_populates="members", viewonly=True
    )


class Society(Entity, Base):
    __tablename__ = "societies"
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    __table_args__ = (CheckConstraint("status IN ('draft','active','paused')"),)

    towers: Mapped[list[Tower]] = relationship(back_populates="society", passive_deletes="all")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="society", passive_deletes="all"
    )
    kitchens: Mapped[list[Kitchen]] = relationship(back_populates="society", passive_deletes="all")
    orders: Mapped[list[Order]] = relationship(back_populates="society", passive_deletes="all")
    users: Mapped[list[User]] = relationship(
        secondary="society_memberships", back_populates="societies", viewonly=True
    )


class Tower(Entity, Base):
    __tablename__ = "towers"
    society_id: Mapped[UUID] = mapped_column(ForeignKey("societies.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("society_id", "name"),
        UniqueConstraint("id", "society_id", name="uq_towers_id_society"),
    )

    society: Mapped[Society] = relationship(back_populates="towers")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="tower",
        primaryjoin=lambda: and_(
            Tower.id == foreign(Membership.tower_id), Tower.society_id == Membership.society_id
        ),
        passive_deletes="all",
    )
    kitchens: Mapped[list[Kitchen]] = relationship(
        back_populates="tower",
        primaryjoin=lambda: and_(
            Tower.id == foreign(Kitchen.tower_id), Tower.society_id == Kitchen.society_id
        ),
        passive_deletes="all",
    )


class Membership(Entity, Base):
    __tablename__ = "society_memberships"
    society_id: Mapped[UUID] = mapped_column(ForeignKey("societies.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tower_id: Mapped[UUID] = mapped_column(Uuid)
    flat: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    __table_args__ = (
        UniqueConstraint("society_id", "user_id"),
        CheckConstraint(
            "status IN ('active','suspended')", name="society_memberships_status_check"
        ),
        ForeignKeyConstraint(
            ["tower_id", "society_id"],
            ["towers.id", "towers.society_id"],
            name="fk_membership_tower_society",
        ),
    )

    society: Mapped[Society] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    tower: Mapped[Tower] = relationship(
        back_populates="memberships",
        primaryjoin=lambda: and_(
            foreign(Membership.tower_id) == Tower.id, Membership.society_id == Tower.society_id
        ),
    )


class Kitchen(Entity, Base):
    __tablename__ = "kitchens"
    society_id: Mapped[UUID] = mapped_column(ForeignKey("societies.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    tower_id: Mapped[UUID] = mapped_column(Uuid)
    flat: Mapped[str] = mapped_column(String(50))
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    upi_id: Mapped[str | None] = mapped_column(String(150))
    fssai_number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','suspended')"),
        CheckConstraint("pickup_enabled OR delivery_enabled"),
        CheckConstraint("delivery_fee_paise >= 0"),
        UniqueConstraint("id", "society_id", name="uq_kitchens_id_society"),
        ForeignKeyConstraint(
            ["tower_id", "society_id"],
            ["towers.id", "towers.society_id"],
            name="fk_kitchen_tower_society",
        ),
    )

    society: Mapped[Society] = relationship(back_populates="kitchens")
    tower: Mapped[Tower] = relationship(
        back_populates="kitchens",
        primaryjoin=lambda: and_(
            foreign(Kitchen.tower_id) == Tower.id, Kitchen.society_id == Tower.society_id
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
            Kitchen.id == foreign(Order.kitchen_id), Kitchen.society_id == Order.society_id
        ),
        passive_deletes="all",
    )


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
    society_id: Mapped[UUID] = mapped_column(ForeignKey("societies.id"))
    kitchen_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    fulfillment_type: Mapped[str] = mapped_column(String(20))
    customer_note: Mapped[str | None] = mapped_column(String(1000))
    pickup_address: Mapped[dict] = mapped_column(JSON)
    delivery_address: Mapped[dict] = mapped_column(JSON)
    available_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid")
    upi_id: Mapped[str | None] = mapped_column(String(150))
    __table_args__ = (
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
            ["kitchen_id", "society_id"],
            ["kitchens.id", "kitchens.society_id"],
            name="fk_order_kitchen_society",
        ),
    )

    society: Mapped[Society] = relationship(back_populates="orders")
    kitchen: Mapped[Kitchen] = relationship(
        back_populates="orders",
        primaryjoin=lambda: and_(
            foreign(Order.kitchen_id) == Kitchen.id, Order.society_id == Kitchen.society_id
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
