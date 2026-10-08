"""Checkout rejection boundaries, order authorization and preparation summaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from kitchen_core import orders
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Dish,
    Kitchen,
    Membership,
    MenuListing,
    Order,
    OrderIdempotency,
    User,
)
from kitchen_core.order_schemas import OrderCreate
from kitchen_http.auth import require_user
from test_orders import attach_pickup, payload, place
from test_orders import order_seed as order_seed


@pytest.mark.parametrize("key", ["", " " * 5, "x" * 121])
def test_checkout_rejects_invalid_idempotency_key(key):
    session = MagicMock()
    with pytest.raises(DomainError) as error:
        orders.create_order(
            session,
            SimpleNamespace(id=uuid4()),
            OrderCreate(items=[{"menu_listing_id": uuid4(), "quantity": 1}]),
            key,
        )
    assert error.value.code == "invalid_idempotency_key"
    session.scalar.assert_not_called()


@pytest.mark.parametrize(
    "case,code",
    [
        ("inactive", "account_inactive"),
        ("missing_user", "account_inactive"),
        ("quantity", "quantity_limit"),
        ("missing_listing", "listing_not_found"),
        ("missing_kitchen", "kitchen_not_found"),
        ("missing_community", "community_not_found"),
        ("missing_order", "order_unavailable"),
    ],
)
def test_checkout_rejects_missing_records_before_inventory_changes(monkeypatch, case, code):
    session = MagicMock()
    user = SimpleNamespace(id=uuid4(), is_active=case != "inactive")
    kitchen = SimpleNamespace(community_id=uuid4())
    listing_id = uuid4()
    request = OrderCreate(items=[{"menu_listing_id": listing_id, "quantity": 1}])
    session.scalar.side_effect = [
        None if case == "missing_user" else user,
        None if case == "missing_kitchen" else kitchen,
    ]
    session.get.return_value = None
    session.scalars.return_value = (
        [] if case == "missing_listing" else [SimpleNamespace(id=listing_id, kitchen_id=uuid4())]
    )
    if case == "quantity":
        request = OrderCreate(
            items=[
                {"menu_listing_id": listing_id, "quantity": 100},
                {"menu_listing_id": listing_id, "quantity": 1},
            ]
        )
    if case == "missing_order":
        previous = SimpleNamespace(
            hash_version=2, request_hash=orders.request_hash(request), order_id=uuid4()
        )
        session.get.side_effect = [previous, None]
    with pytest.raises(DomainError) as error:
        orders.create_order(session, user, request, "key")
    assert error.value.code == code
    session.add.assert_not_called()


@pytest.mark.parametrize(
    "case,code",
    [
        ("mixed_kitchens", "mixed_kitchens"),
        ("window", "mixed_service_windows"),
        ("kitchen_pickup", "fulfillment_unavailable"),
        ("listing_pickup", "fulfillment_unavailable"),
        ("dish", "dish_unavailable"),
        ("delivery_address", "delivery_address_required"),
        ("total", "order_total_limit"),
    ],
)
def test_checkout_business_limits_do_not_reserve_stock(session, order_seed, case, code):
    seed = order_seed
    kitchen = session.get(Kitchen, seed["kitchen"])
    listing = session.get(MenuListing, seed["listing"])
    request = payload(seed)
    if case in {"mixed_kitchens", "window"}:
        other_kitchen = kitchen
        if case == "mixed_kitchens":
            other_kitchen = Kitchen(
                community_id=kitchen.community_id, name="Other", status="approved"
            )
            session.add(other_kitchen)
            session.flush()
        dish = Dish(kitchen_id=other_kitchen.id, name="Other dish")
        session.add(dish)
        session.flush()
        another = MenuListing(
            kitchen_id=other_kitchen.id,
            dish_id=dish.id,
            service_date=listing.service_date,
            available_from=listing.available_from,
            available_until=listing.available_until + timedelta(minutes=1),
            order_cutoff=listing.order_cutoff,
            price_paise=100,
            quantity_total=10,
        )
        session.add(another)
        session.flush()
        request = OrderCreate(
            items=[
                {"menu_listing_id": listing.id, "quantity": 1},
                {"menu_listing_id": another.id, "quantity": 1},
            ]
        )
    elif case == "kitchen_pickup":
        kitchen.pickup_enabled = False
        kitchen.delivery_enabled = True
    elif case == "listing_pickup":
        listing.pickup_enabled = False
        listing.delivery_enabled = True
    elif case == "dish":
        session.get(Dish, seed["dish"]).is_active = False
    elif case == "delivery_address":
        kitchen.delivery_enabled = True
        listing.delivery_enabled = True
        session.get(Membership, seed["membership"]).address_label = None
        request = request.model_copy(update={"fulfillment_type": "delivery"})
    else:
        listing.price_paise = 30_000_000
        listing.quantity_total = 100
        request = payload(seed, 100)
    session.flush()
    with pytest.raises(DomainError) as error:
        orders.create_order(session, session.get(User, seed["customer"]), request, "limits")
    assert error.value.code == code
    assert listing.quantity_reserved == 0


def test_legacy_idempotency_key_cannot_be_used_with_new_destination(session_factory, order_seed):
    seed = order_seed
    place(session_factory, seed, key="legacy")
    with session_factory() as session:
        previous = session.get(OrderIdempotency, (seed["customer"], "legacy"))
        previous.hash_version = 1
        previous.request_hash = orders.request_hash(payload(seed), version=1)
        session.flush()
        request = payload(seed).model_copy(update={"pickup_point_id": seed["pickup_point"]})
        with pytest.raises(DomainError) as error:
            orders.create_order(session, session.get(User, seed["customer"]), request, "legacy")
        assert error.value.code == "idempotency_conflict"


@pytest.mark.parametrize(
    "operation,actor,action",
    [
        ("get", None, None),
        ("get", "outsider", None),
        ("transition", None, "accept"),
        ("transition", "outsider", "accept"),
        ("transition", "owner", "cancel"),
        ("payment", None, "report"),
        ("payment", "owner", "report"),
        ("payment", "outsider", "confirm"),
    ],
)
def test_order_access_does_not_reveal_another_customers_order(
    session_factory, order_seed, operation, actor, action
):
    seed = order_seed
    order = place(session_factory, seed)
    with session_factory() as session:
        user = session.get(User, seed[actor]) if actor else None
        with pytest.raises(DomainError) as error:
            if operation == "get":
                orders.get_order(session, user, order.id)
            elif operation == "transition":
                orders.transition_order(session, user, order.id, action)
            else:
                orders.record_payment(session, user, order.id, action)
        assert error.value.code == "order_not_found"


def test_expired_accept_missing_order_and_reject_without_reason(session_factory, order_seed):
    seed = order_seed
    order = place(session_factory, seed)
    with session_factory() as session:
        owner = session.get(User, seed["owner"])
        with pytest.raises(DomainError) as error:
            orders.transition_order(session, owner, order.id, "reject")
        assert error.value.code == "rejection_reason_required"
        session.get(Order, order.id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.flush()
        with pytest.raises(DomainError) as error:
            orders.transition_order(session, owner, order.id, "accept")
        assert error.value.code == "order_expired"
        with pytest.raises(DomainError) as error:
            orders.get_order(session, owner, uuid4())
        assert error.value.code == "order_not_found"
        with pytest.raises(DomainError):
            orders._locked_order(session, uuid4())


def test_preparation_summary_aggregates_reused_dish_notes_and_http_lists(
    client, admin_client, session_factory, order_seed
):
    seed = order_seed
    with session_factory() as session:
        listing = session.get(MenuListing, seed["listing"])
        another = MenuListing(
            kitchen_id=listing.kitchen_id,
            dish_id=listing.dish_id,
            service_date=listing.service_date,
            available_from=listing.available_from,
            available_until=listing.available_until,
            order_cutoff=listing.order_cutoff,
            price_paise=100,
            quantity_total=10,
        )
        session.add(another)
        session.flush()
        attach_pickup(session, session.get(Kitchen, seed["kitchen"]), another)
        user = session.get(User, seed["customer"])
        order = orders.create_order(
            session,
            user,
            OrderCreate(
                items=[
                    {"menu_listing_id": listing.id, "quantity": 1},
                    {"menu_listing_id": another.id, "quantity": 2},
                ],
                customer_note="Less salt",
            ),
            "notes",
        )
        owner = session.get(User, seed["owner"])
        orders.transition_order(session, owner, order.id, "accept")
        another_order = orders.create_order(session, user, payload(seed), "no-note")
        orders.transition_order(session, owner, another_order.id, "accept")
        session.commit()
        on = (listing.available_from + timedelta(hours=5, minutes=30)).date()
        summary = orders.prep_summary(session, owner, seed["kitchen"], on)
        assert summary.total_portions == 5 and summary.order_count == 2
        assert summary.items[0].portion_count == 5 and summary.items[0].order_count == 2
        assert len(summary.items[0].notes) == 1 and summary.items[0].notes[0].quantity == 3
        assert summary.items[0].notes[0].customer_note == "Less salt"
        client.app.dependency_overrides[require_user] = lambda: user
        assert client.get("/api/v1/orders").json()["total"] == 2
        client.app.dependency_overrides[require_user] = lambda: owner
        assert client.get(f"/api/v1/kitchens/{seed['kitchen']}/orders").json()["total"] == 2
        response = client.get(
            f"/api/v1/kitchens/{seed['kitchen']}/prep-summary", params={"date": on.isoformat()}
        )
        assert response.status_code == 200 and response.json()["total_portions"] == 5
        response = admin_client.get(
            f"/api/v1/kitchens/{seed['kitchen']}/prep-summary", params={"date": on.isoformat()}
        )
        assert response.status_code == 200 and response.json()["order_count"] == 2
        for fetch in (client, admin_client):
            response = fetch.get(
                f"/api/v1/kitchens/{seed['kitchen']}/fulfillment-groups",
                params={"service_date": on.isoformat()},
            )
            assert response.status_code == 200 and response.json()[0]["order_count"] == 2
        pending = orders.create_order(session, user, payload(seed), "reject-via-api")
        session.commit()
        response = client.post(f"/api/v1/orders/{pending.id}/reject", json={"reason": "Sold out"})
        assert response.status_code == 200 and response.json()["status"] == "rejected"
        for function in (orders.prep_summary, orders.fulfillment_groups):
            with pytest.raises(DomainError):
                function(session, None, seed["kitchen"], on)


def test_fulfillment_groups_reject_missing_legacy_address(session_factory, order_seed):
    seed = order_seed
    created = place(session_factory, seed)
    with session_factory() as session:
        owner = session.get(User, seed["owner"])
        orders.transition_order(session, owner, created.id, "accept")
        order = session.get(Order, created.id)
        order.fulfillment_snapshot = None
        order.pickup_address = None
        order.delivery_address = None
        session.flush()
        on = (order.available_from + timedelta(hours=5, minutes=30)).date()
        with pytest.raises(DomainError) as error:
            orders.fulfillment_groups(session, owner, seed["kitchen"], on)
        assert error.value.code == "invalid_address"
