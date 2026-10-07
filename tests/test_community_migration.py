"""Upgrade a populated legacy schema in isolation, including historical checkout retries."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from kitchen_core.models import Community, CommunityZone, Kitchen, Membership, MenuListing, Order
from kitchen_core.order_schemas import OrderCreate
from kitchen_core.orders import create_order, request_hash
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.orm import Session


def test_populated_society_upgrade_preserves_ids_snapshots_stock_and_retry_keys(engine):
    schema = "community_migration_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    migration_engine = create_engine(url)
    env = {
        **os.environ,
        "KITCHEN_ENVIRONMENT": "test",
        "KITCHEN_DATABASE_URL": url.render_as_string(hide_password=False),
    }

    def alembic(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    try:
        alembic("upgrade", "0004_contact_phones")
        metadata = MetaData()
        metadata.reflect(migration_engine)
        ids = {
            name: uuid4()
            for name in (
                "community",
                "zone",
                "user",
                "kitchen",
                "dish",
                "listing",
                "order",
                "membership",
            )
        }
        now = datetime.now(UTC)
        ready = now + timedelta(hours=2)
        pickup = {
            "society_name": "Legacy Society",
            "address": "Old Road",
            "city": "Pune",
            "postal_code": "411001",
            "tower_name": "Tower A",
            "flat": "101",
        }
        delivery = {**pickup, "flat": "102"}
        payload = OrderCreate(items=[{"menu_listing_id": ids["listing"], "quantity": 2}])
        with migration_engine.begin() as connection:
            records = {
                "societies": dict(
                    id=ids["community"],
                    name="Legacy Society",
                    address="Old Road",
                    city="Pune",
                    postal_code="411001",
                    status="active",
                    created_at=now,
                ),
                "towers": dict(
                    id=ids["zone"], society_id=ids["community"], name="Tower A", created_at=now
                ),
                "users": dict(
                    id=ids["user"],
                    oidc_subject="legacy-owner",
                    oidc_issuer="https://identity.example.test",
                    name="Legacy Owner",
                    is_active=True,
                    created_at=now,
                ),
                "society_memberships": dict(
                    id=ids["membership"],
                    society_id=ids["community"],
                    user_id=ids["user"],
                    tower_id=ids["zone"],
                    flat="102",
                    status="active",
                    created_at=now,
                ),
                "kitchens": dict(
                    id=ids["kitchen"],
                    society_id=ids["community"],
                    name="Legacy Kitchen",
                    tower_id=ids["zone"],
                    flat="101",
                    pickup_enabled=True,
                    delivery_enabled=False,
                    delivery_fee_paise=0,
                    status="approved",
                    created_at=now,
                ),
                "kitchen_members": dict(
                    kitchen_id=ids["kitchen"], user_id=ids["user"], role="owner"
                ),
                "dishes": dict(
                    id=ids["dish"],
                    kitchen_id=ids["kitchen"],
                    name="Rice",
                    is_active=True,
                    created_at=now,
                ),
                "menu_listings": dict(
                    id=ids["listing"],
                    kitchen_id=ids["kitchen"],
                    dish_id=ids["dish"],
                    service_date=ready.date(),
                    available_from=ready,
                    available_until=ready + timedelta(hours=1),
                    order_cutoff=ready - timedelta(hours=1),
                    price_paise=10000,
                    quantity_total=10,
                    quantity_reserved=2,
                    pickup_enabled=True,
                    delivery_enabled=False,
                    status="published",
                    created_at=now,
                ),
                "orders": dict(
                    id=ids["order"],
                    society_id=ids["community"],
                    kitchen_id=ids["kitchen"],
                    customer_id=ids["user"],
                    status="pending",
                    fulfillment_type="pickup",
                    pickup_address=pickup,
                    delivery_address=delivery,
                    available_from=ready,
                    available_until=ready + timedelta(hours=1),
                    expires_at=now + timedelta(minutes=15),
                    subtotal_paise=20000,
                    delivery_fee_paise=0,
                    total_paise=20000,
                    payment_status="unpaid",
                    created_at=now,
                ),
                "order_items": dict(
                    id=uuid4(),
                    order_id=ids["order"],
                    menu_listing_id=ids["listing"],
                    dish_name="Rice",
                    unit_price_paise=10000,
                    quantity=2,
                    total_paise=20000,
                    created_at=now,
                ),
                "order_events": dict(
                    id=uuid4(),
                    order_id=ids["order"],
                    status="pending",
                    actor_id=ids["user"],
                    created_at=now,
                ),
                "order_idempotency": dict(
                    customer_id=ids["user"],
                    key="legacy-key",
                    request_hash=request_hash(payload, version=1),
                    order_id=ids["order"],
                ),
            }
            for name, record in records.items():
                connection.execute(metadata.tables[name].insert().values(**record))
        alembic("upgrade", "head")
        alembic("check")
        with Session(migration_engine) as session:
            from kitchen_core.models import ListingPickupPoint, OrderIdempotency, PickupPoint, User

            assert session.get(Community, ids["community"]).type == "residential_society"
            assert session.get(CommunityZone, ids["zone"]).zone_type == "tower"
            assert session.get(Membership, ids["membership"]).address_label == "102"
            assert session.get(Kitchen, ids["kitchen"]).address_label == "101"
            assert session.get(MenuListing, ids["listing"]).quantity_reserved == 2
            stored = session.get(Order, ids["order"])
            assert stored.pickup_address == pickup and stored.delivery_address == delivery
            assert stored.fulfillment_snapshot is None
            assert session.get(PickupPoint, ids["kitchen"]).address_label == "101"
            assert session.get(ListingPickupPoint, (ids["listing"], ids["kitchen"])) is not None
            assert session.get(OrderIdempotency, (ids["user"], "legacy-key")).hash_version == 1
            replay = create_order(session, session.get(User, ids["user"]), payload, "legacy-key")
            assert replay.id == ids["order"] and replay.fulfillment_snapshot.version == 1
            assert replay.fulfillment_snapshot.zone_name == "Tower A"
            fresh = create_order(session, session.get(User, ids["user"]), payload, "new-key")
            assert fresh.id != ids["order"] and fresh.pickup_point_id == ids["kitchen"]
            assert fresh.fulfillment_snapshot.version == 2
            assert len(list(session.scalars(select(Order)))) == 2
            assert session.get(MenuListing, ids["listing"]).quantity_reserved == 4
    finally:
        migration_engine.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
