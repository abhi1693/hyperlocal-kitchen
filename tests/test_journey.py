from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, Request
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import MenuListing, User
from kitchen_http.auth import require_user
from sqlalchemy.orm import Session


def successful(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def domain_test_user(
    request: Request, session: Annotated[Session, Depends(get_session, scope="function")]
):
    # Authentication itself is exercised through signed Zitadel fixtures in test_auth.
    # This override isolates the complete domain journey from an external IdP.
    try:
        user_id = UUID(request.headers["Authorization"].removeprefix("Bearer "))
    except (KeyError, ValueError):
        raise DomainError(401, "sign_in_required", "Sign in") from None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise DomainError(401, "invalid_session", "Sign in")
    return user


@pytest.fixture
def pilot(client, admin_client, session_factory):
    client.app.dependency_overrides[require_user] = domain_test_user
    with session_factory.begin() as session:
        cook = User(
            oidc_subject="pilot-cook",
            oidc_issuer="https://identity.example.test",
            phone="+916000000001",
            name="Pilot cook",
        )
        customer = User(
            oidc_subject="pilot-resident",
            oidc_issuer="https://identity.example.test",
            phone="+916000000002",
            name="Pilot resident",
        )
        session.add_all([cook, customer])
        session.flush()
        owner = {"Authorization": f"Bearer {cook.id}"}
        resident = {"Authorization": f"Bearer {customer.id}"}
    society = successful(
        admin_client.post(
            "/api/v1/societies",
            json={
                "name": "Pilot Gardens",
                "address": "123 Pilot Road",
                "city": "Gurugram",
                "postal_code": "122001",
                "towers": [{"name": "Tower A"}, {"name": "Tower B"}],
            },
        ),
        201,
    )
    sid = society["id"]
    successful(admin_client.post(f"/api/v1/societies/{sid}/activate"))
    for headers, tower, flat in (
        (owner, 0, "101"),
        (resident, 1, "202"),
    ):
        membership = successful(
            client.post(
                f"/api/v1/societies/{sid}/join",
                headers=headers,
                json={
                    "tower_id": society["towers"][tower]["id"],
                    "flat": flat,
                },
            ),
            201,
        )
        assert membership["status"] == "active"
    kitchen = successful(
        client.post(
            "/api/v1/kitchens",
            headers=owner,
            json={
                "society_id": sid,
                "name": "Pilot Kitchen",
                "upi_id": "pilot@bank",
                "delivery_enabled": True,
                "delivery_fee_paise": 2000,
            },
        ),
        201,
    )
    kid = kitchen["id"]
    assert kitchen["status"] == "pending"
    successful(
        admin_client.post(
            f"/api/v1/kitchens/{kid}/approve", json={"fssai_number": "12345678901234"}
        )
    )
    dish = successful(
        client.post(f"/api/v1/kitchens/{kid}/dishes", headers=owner, json={"name": "Rajma Chawal"}),
        201,
    )
    ready = datetime.now(UTC) + timedelta(hours=2)
    listing = successful(
        client.post(
            f"/api/v1/kitchens/{kid}/menu-listings",
            headers=owner,
            json={
                "dish_id": dish["id"],
                "service_date": ready.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
                "available_from": ready.isoformat(),
                "available_until": (ready + timedelta(hours=1)).isoformat(),
                "order_cutoff": (ready - timedelta(hours=1)).isoformat(),
                "price_paise": 15000,
                "quantity_total": 3,
                "delivery_enabled": True,
            },
        ),
        201,
    )
    return owner, resident, society, kitchen, listing


def test_complete_http_order_loop_and_notification_privacy(client, admin_client, pilot):
    owner, resident, society, kitchen, listing = pilot
    menu = successful(
        client.get(
            f"/api/v1/societies/{society['id']}/menu",
            params={"date": listing["service_date"]},
            headers=resident,
        )
    )
    assert menu["items"][0]["quantity_remaining"] == 3
    assert "flat" not in menu["items"][0]["kitchen"]
    body = {
        "items": [{"menu_listing_id": listing["id"], "quantity": 2}],
        "fulfillment_type": "delivery",
    }
    headers = {**resident, "Idempotency-Key": "pilot-checkout"}
    order = successful(client.post("/api/v1/orders", json=body, headers=headers), 201)
    assert order["status"] == "pending"
    assert order["total_paise"] == 32000
    assert order["delivery_address"]["flat"] == "202"
    assert order["pickup_address"]["address"] == "123 Pilot Road"
    assert order["upi_id"] is None
    retry = client.post("/api/v1/orders", json=body, headers=headers)
    assert retry.status_code in (200, 201)
    assert retry.json()["id"] == order["id"]
    oid = order["id"]
    for action, state in (
        ("accept", "accepted"),
        ("prepare", "preparing"),
        ("ready", "ready"),
        ("complete", "completed"),
    ):
        changed = successful(client.post(f"/api/v1/orders/{oid}/{action}", headers=owner))
        assert changed["status"] == state
        if action == "accept":
            assert changed["upi_id"] == "pilot@bank"
            assert (
                client.post(f"/api/v1/orders/{oid}/confirm-payment", headers=resident).status_code
                == 404
            )
            successful(client.post(f"/api/v1/orders/{oid}/report-payment", headers=resident))
            paid = successful(client.post(f"/api/v1/orders/{oid}/confirm-payment", headers=owner))
            assert paid["payment_status"] == "kitchen_confirmed"
    assert client.post(f"/api/v1/orders/{oid}/cancel", headers=resident).status_code == 409
    assert (
        successful(client.get(f"/api/v1/orders/{oid}", headers=resident))["status"] == "completed"
    )
    inbox = successful(client.get("/api/v1/notifications", headers=resident))["items"]
    assert len(inbox) >= 4
    assert "flat" not in str(inbox)
    assert "phone" not in str(inbox)
    note = successful(client.post(f"/api/v1/notifications/{inbox[0]['id']}/read", headers=resident))
    assert note["read_at"] is not None
    assert (
        client.post(f"/api/v1/notifications/{inbox[0]['id']}/read", headers=owner).status_code
        == 404
    )


def test_customer_cancellation_releases_inventory_once(client, pilot, session):
    owner, resident, society, kitchen, listing = pilot
    order = successful(
        client.post(
            "/api/v1/orders",
            headers={**resident, "Idempotency-Key": "cancel"},
            json={"items": [{"menu_listing_id": listing["id"], "quantity": 2}]},
        ),
        201,
    )
    for _ in range(2):
        result = successful(client.post(f"/api/v1/orders/{order['id']}/cancel", headers=resident))
        assert result["status"] == "cancelled"
    assert session.get(MenuListing, UUID(listing["id"])).quantity_reserved == 0


def test_platform_admin_writes_do_not_exist_in_resident_api(client):
    assert client.post("/api/v1/societies", json={"name": "Unauthorised"}).status_code == 405
    assert (
        client.post(
            "/api/v1/societies/00000000-0000-0000-0000-000000000001/towers",
            json={"name": "Unauthorised"},
        ).status_code
        == 405
    )
