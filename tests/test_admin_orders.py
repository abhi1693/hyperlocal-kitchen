from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from kitchen_admin_api.orders import router
from kitchen_core import auth
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Dish,
    Kitchen,
    KitchenMember,
    Membership,
    MenuListing,
    Notification,
    Order,
    OrderEvent,
    User,
)
from kitchen_core.order_schemas import OrderCreate
from kitchen_core.orders import create_order, get_order
from kitchen_http import auth as http_auth
from kitchen_http.application import configure_app
from sqlalchemy import func, select
from test_orders import attach_pickup, payload, place
from test_orders import order_seed as order_seed


def create_as_admin(client, seed, *, quantity=2, key="admin-order-key", customer=None):
    body = payload(seed, quantity).model_dump(mode="json")
    body["customer_id"] = str(customer or seed["customer"])
    return client.post("/api/v1/orders", json=body, headers={"Idempotency-Key": key})


def test_admin_create_uses_customer_inventory_and_canonical_idempotency(
    admin_client, session_factory, order_seed
):
    seed = order_seed
    created = create_as_admin(admin_client, seed)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["customer_id"] == str(seed["customer"])
    assert order["kitchen_id"] == str(seed["kitchen"])
    assert order["total_paise"] == 30000
    assert order["status"] == "pending"
    replay = create_as_admin(admin_client, seed)
    assert replay.json()["id"] == order["id"]
    assert create_as_admin(admin_client, seed, quantity=3).status_code == 409
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert session.scalar(select(func.count()).select_from(Notification)) == 1
        event = session.scalar(select(OrderEvent))
        assert event.actor_id is None
        # Both API surfaces share the customer's idempotency namespace.
        customer = session.get(User, seed["customer"])
        resident_replay = create_order(session, customer, payload(seed), "admin-order-key")
        assert str(resident_replay.id) == order["id"]


def test_admin_order_input_cannot_override_server_fields(admin_client, order_seed):
    body = payload(order_seed).model_dump(mode="json")
    body["customer_id"] = str(order_seed["customer"])
    assert admin_client.post("/api/v1/orders", json=body).status_code == 422
    for field, value in [("total_paise", 1), ("status", "completed"), ("admin", True)]:
        response = admin_client.post(
            "/api/v1/orders", json={**body, field: value}, headers={"Idempotency-Key": "forged"}
        )
        assert response.status_code == 422
    body["customer_id"] = str(uuid4())
    response = admin_client.post(
        "/api/v1/orders", json=body, headers={"Idempotency-Key": "missing-customer"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("restriction", "expected_status"),
    [("inactive", 403), ("membership", 403), ("community", 403), ("stock", 409), ("cutoff", 409)],
)
def test_admin_creation_preserves_customer_and_listing_rules(
    admin_client, session_factory, order_seed, restriction, expected_status
):
    seed = order_seed
    customer = seed["customer"]
    with session_factory() as session:
        if restriction == "inactive":
            session.get(User, customer).is_active = False
        elif restriction == "membership":
            session.get(Membership, seed["membership"]).status = "suspended"
        elif restriction == "community":
            customer = seed["outsider"]
        elif restriction == "stock":
            session.get(MenuListing, seed["listing"]).quantity_total = 1
        else:
            session.get(MenuListing, seed["listing"]).order_cutoff = datetime.now(UTC) - timedelta(
                minutes=1
            )
        session.commit()
    response = create_as_admin(admin_client, seed, customer=customer)
    assert response.status_code == expected_status, response.text
    with session_factory() as session:
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(Notification)) == 0


def other_community_order(session_factory, seed):
    now = datetime.now(UTC)
    with session_factory() as session:
        customer = session.get(User, seed["outsider"])
        membership = session.scalar(select(Membership).where(Membership.user_id == customer.id))
        kitchen = Kitchen(
            community_id=membership.community_id,
            zone_id=membership.zone_id,
            address_label=membership.address_label,
            name="Other Community Kitchen",
            status="approved",
        )
        session.add(kitchen)
        session.flush()
        session.add(KitchenMember(kitchen_id=kitchen.id, user_id=customer.id))
        dish = Dish(kitchen_id=kitchen.id, name="Dal Rice")
        session.add(dish)
        session.flush()
        listing = MenuListing(
            kitchen_id=kitchen.id,
            dish_id=dish.id,
            service_date=now.date(),
            available_from=now + timedelta(hours=2),
            available_until=now + timedelta(hours=3),
            order_cutoff=now + timedelta(hours=1),
            price_paise=12000,
            quantity_total=10,
        )
        session.add(listing)
        session.flush()
        attach_pickup(session, kitchen, listing)
        order = create_order(
            session,
            customer,
            OrderCreate(items=[{"menu_listing_id": listing.id, "quantity": 3}]),
            "other-community-order",
        )
        session.commit()
        return order


def test_admin_global_detail_and_sql_filters_do_not_expand_resident_access(
    admin_client, session_factory, order_seed
):
    first = place(session_factory, order_seed, quantity=1)
    other = other_community_order(session_factory, order_seed)
    assert admin_client.get(f"/api/v1/orders/{other.id}").status_code == 200
    with session_factory() as session:
        resident = session.get(User, order_seed["customer"])
        with pytest.raises(DomainError) as error:
            get_order(session, resident, other.id)
        assert error.value.status == 404
    assert admin_client.post(f"/api/v1/orders/{first.id}/accept").status_code == 200
    assert admin_client.post(f"/api/v1/orders/{first.id}/report-payment").status_code == 200
    for filters, expected in [
        ({"customer_id": str(other.customer_id)}, other.id),
        ({"community_id": str(other.community_id)}, other.id),
        ({"kitchen_id": str(first.kitchen_id)}, first.id),
        ({"status": "accepted", "payment_status": "customer_reported"}, first.id),
        ({"q": "Other Community Kitchen"}, other.id),
        ({"q": "Outsider"}, other.id),
        ({"q": f"#{first.order_number}"}, first.id),
    ]:
        response = admin_client.get("/api/v1/orders", params=filters)
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        assert [item["id"] for item in page["items"]] == [str(expected)]
    page = admin_client.get(
        "/api/v1/orders", params={"sort": "order_number", "limit": 1, "offset": 1}
    ).json()
    assert page["total"] == 2
    assert page["limit"] == page["offset"] == 1
    assert page["items"][0]["id"] == str(other.id)
    assert admin_client.get("/api/v1/orders", params={"q": "%"}).json()["total"] == 0
    assert admin_client.get("/api/v1/orders", params={"q": "#"}).json()["total"] == 0
    for invalid in [{"sort": "customer_id"}, {"limit": 101}, {"status": "invented"}]:
        assert admin_client.get("/api/v1/orders", params=invalid).status_code == 422


def test_admin_transitions_and_payments_share_guards_and_idempotent_notifications(
    admin_client, session_factory, order_seed
):
    created = create_as_admin(admin_client, order_seed).json()
    path = f"/api/v1/orders/{created['id']}"
    assert admin_client.post(path + "/ready").status_code == 409
    assert admin_client.post(path + "/confirm-payment").status_code == 409
    for action in ["accept", "report-payment", "confirm-payment", "prepare", "ready", "complete"]:
        first = admin_client.post(path + "/" + action)
        assert first.status_code == 200, first.text
        with session_factory() as session:
            before = session.scalar(select(func.count()).select_from(Notification))
        repeated = admin_client.post(path + "/" + action)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["events"] == first.json()["events"]
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(Notification)) == before
    detail = admin_client.get(path).json()
    assert detail["status"] == "completed"
    assert detail["payment_status"] == "kitchen_confirmed"
    assert len(detail["events"]) == 7
    assert admin_client.post(path + "/cancel").status_code == 409
    assert admin_client.patch(path, json={"status": "pending"}).status_code == 405
    assert admin_client.delete(path).status_code == 405
    with session_factory() as session:
        assert session.get(MenuListing, order_seed["listing"]).quantity_reserved == 2
        assert all(event.actor_id is None for event in session.scalars(select(OrderEvent)))


@pytest.mark.parametrize("action", ["cancel", "reject", "accepted_cancel"])
def test_admin_releases_inventory_and_preserves_rejection_reason_once(
    admin_client, session_factory, order_seed, action
):
    order = create_as_admin(admin_client, order_seed).json()
    path = f"/api/v1/orders/{order['id']}"
    if action == "accepted_cancel":
        assert admin_client.post(path + "/accept").status_code == 200
        action = "cancel"
    body = {"reason": "Kitchen cannot prepare this dish."} if action == "reject" else None
    if action == "reject":
        assert admin_client.post(path + "/reject", json={"reason": " "}).status_code == 422
    first = admin_client.post(path + "/" + action, json=body)
    repeated = admin_client.post(path + "/" + action, json=body)
    assert first.status_code == repeated.status_code == 200
    assert first.json()["events"] == repeated.json()["events"]
    if action == "reject":
        assert first.json()["rejection_reason"] == body["reason"]
    with session_factory() as session:
        assert session.get(MenuListing, order_seed["listing"]).quantity_reserved == 0


def test_admin_cannot_accept_an_expired_window(admin_client, session_factory, order_seed):
    order = place(session_factory, order_seed)
    with session_factory() as session:
        session.get(Order, order.id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    response = admin_client.post(f"/api/v1/orders/{order.id}/accept")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_expired"
    with session_factory() as session:
        assert session.get(Order, order.id).status == "pending"
        assert session.scalar(select(func.count()).select_from(OrderEvent)) == 1


@pytest.mark.parametrize("guard", ["signed_out", "role", "csrf"])
def test_every_admin_order_route_retains_admin_auth_before_database(monkeypatch, guard):
    record = {
        "subject": "admin-subject",
        "issuer": "https://identity.example.test",
        "organization_id": "pilot-org",
        "roles": ["kitchen_owner"] if guard == "role" else ["platform_admin"],
        "expires_at": 4_000_000_000,
        "csrf_token": "c" * 43,
    }

    def session_record(kind, token):
        assert kind == "admin"
        if guard == "signed_out":
            raise DomainError(401, "invalid_session", "Administrator sign-in required")
        return record

    monkeypatch.setattr(auth, "load_session", session_record)
    monkeypatch.setattr(
        http_auth,
        "get_settings",
        lambda: SimpleNamespace(
            admin_required_role="platform_admin", admin_base_url="http://testserver"
        ),
    )
    app = configure_app("Admin orders permission contract")
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: pytest.fail("Unauthorized database access")
    path = f"/api/v1/orders/{uuid4()}"
    with TestClient(app) as client:
        if guard != "csrf":
            assert client.get("/api/v1/orders").status_code == (
                401 if guard == "signed_out" else 403
            )
            assert client.get(path).status_code == (401 if guard == "signed_out" else 403)
        for suffix in [
            "accept",
            "reject",
            "prepare",
            "ready",
            "complete",
            "cancel",
            "report-payment",
            "confirm-payment",
        ]:
            response = client.post(path + "/" + suffix, json={"reason": "Unavailable"})
            assert response.status_code == (401 if guard == "signed_out" else 403)
        assert client.post("/api/v1/orders", json={}).status_code == (
            401 if guard == "signed_out" else 403
        )
