"""Integration checks for society onboarding and committed food listings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic

import pytest
from kitchen_core import catalog
from kitchen_core.catalog_schemas import MembershipJoin
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Dish,
    Kitchen,
    KitchenMember,
    Membership,
    MenuListing,
    Society,
    Tower,
    User,
)
from kitchen_http.auth import require_user
from sqlalchemy import func, select, text


def as_user(client, user):
    client.app.dependency_overrides[require_user] = lambda: user


@pytest.fixture
def market(session):
    society = Society(
        name="Garden Society",
        address="Garden Road",
        city="Pune",
        postal_code="411001",
        status="active",
    )
    other = Society(
        name="Other Society",
        address="Other Road",
        city="Pune",
        postal_code="411002",
        status="active",
    )
    owner = User(
        oidc_subject="catalog-owner",
        oidc_issuer="https://identity.example.test",
        phone="+919000000001",
        name="Manisha",
        is_active=True,
    )
    customer = User(
        oidc_subject="catalog-customer",
        oidc_issuer="https://identity.example.test",
        phone="+919000000002",
        name="Resident",
        is_active=True,
    )
    outsider = User(
        oidc_subject="catalog-outsider",
        oidc_issuer="https://identity.example.test",
        phone="+919000000003",
        name="Other resident",
        is_active=True,
    )
    session.add_all([society, other, owner, customer, outsider])
    session.flush()
    tower = Tower(society_id=society.id, name="Tower B")
    other_tower = Tower(society_id=other.id, name="Tower Z")
    session.add_all([tower, other_tower])
    session.flush()
    session.add_all(
        [
            Membership(
                society_id=society.id,
                user_id=owner.id,
                tower_id=tower.id,
                flat="B-1204",
                status="active",
            ),
            Membership(
                society_id=society.id,
                user_id=customer.id,
                tower_id=tower.id,
                flat="B-1001",
                status="active",
            ),
            Membership(
                society_id=other.id,
                user_id=outsider.id,
                tower_id=other_tower.id,
                flat="Z-101",
                status="active",
            ),
        ]
    )
    kitchen = Kitchen(
        society_id=society.id,
        name="Manisha's Kitchen",
        tower_id=tower.id,
        flat="B-1204",
        status="approved",
        pickup_enabled=True,
        delivery_enabled=False,
        fssai_number="12345678901234",
    )
    session.add(kitchen)
    session.flush()
    session.add(KitchenMember(kitchen_id=kitchen.id, user_id=owner.id, role="owner"))
    dish = Dish(
        kitchen_id=kitchen.id,
        name="Rajma Chawal",
        is_active=True,
    )
    session.add(dish)
    session.commit()
    return dict(
        society=society,
        other=other,
        tower=tower,
        other_tower=other_tower,
        owner=owner,
        customer=customer,
        outsider=outsider,
        kitchen=kitchen,
        dish=dish,
    )


def listing_payload(market, *, days=1):
    # UTC 07:30 is 13:00 in the society timezone; use tomorrow to avoid clock-sensitive tests.
    ready = datetime.now(UTC).replace(hour=7, minute=30, second=0, microsecond=0) + timedelta(
        days=days
    )
    return dict(
        dish_id=str(market["dish"].id),
        service_date=ready.date().isoformat(),
        available_from=ready.isoformat(),
        available_until=(ready + timedelta(hours=2)).isoformat(),
        order_cutoff=(ready - timedelta(minutes=30)).isoformat(),
        price_paise=15000,
        quantity_total=8,
        pickup_enabled=True,
        delivery_enabled=False,
    )


def publish(client, market, payload=None):
    as_user(client, market["owner"])
    response = client.post(
        f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings",
        json=payload or listing_payload(market),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_platform_only_society_creation_requires_towers_before_activation(
    admin_client, client, session
):
    response = admin_client.post(
        "/api/v1/societies",
        json=dict(
            name="Pilot Society",
            address="Pilot Road",
            city="Pune",
            postal_code="411001",
        ),
    )
    assert response.status_code == 201, response.text
    society_id = response.json()["id"]
    assert response.json()["status"] == "draft"
    assert admin_client.post(f"/api/v1/societies/{society_id}/activate").status_code == 409
    assert (
        admin_client.post(
            f"/api/v1/societies/{society_id}/towers", json={"name": "Tower A"}
        ).status_code
        == 201
    )
    assert (
        admin_client.post(
            f"/api/v1/societies/{society_id}/towers", json={"name": "tower a"}
        ).status_code
        == 409
    )
    assert admin_client.post(f"/api/v1/societies/{society_id}/activate").status_code == 200
    # The resident API contains no society or tower write route.
    assert client.post("/api/v1/societies", json={"name": "Unapproved"}).status_code == 405
    assert (
        client.post(f"/api/v1/societies/{society_id}/towers", json={"name": "Bad"}).status_code
        == 405
    )


@pytest.mark.parametrize("phone", [None, "+919000000004"])
def test_society_join_immediately_enables_food_and_orders(client, session, market, phone):
    food = publish(client, market)
    newcomer = User(
        oidc_subject="catalog-newcomer",
        oidc_issuer="https://identity.example.test",
        phone=phone,
        name="New resident",
        is_active=True,
    )
    session.add(newcomer)
    session.commit()
    society_id = market["society"].id
    data = dict(tower_id=str(market["tower"].id), flat="B-502")
    as_user(client, newcomer)
    joined = client.post(f"/api/v1/societies/{society_id}/join", json=data)
    assert joined.status_code == 201, joined.text
    assert joined.json()["status"] == "active"
    repeated = client.post(f"/api/v1/societies/{society_id}/join", json=data)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == joined.json()["id"]
    assert (
        session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.user_id == newcomer.id, Membership.society_id == society_id)
        )
        == 1
    )
    menu = client.get(f"/api/v1/societies/{society_id}/menu", params={"date": food["service_date"]})
    assert menu.status_code == 200, menu.text
    assert [item["id"] for item in menu.json()["items"]] == [food["id"]]
    assert menu.json()["items"][0]["is_orderable"] is True
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == 200
    assert client.get(f"/api/v1/kitchens/{market['kitchen'].id}").status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "instant-society-join"},
        json={"items": [{"menu_listing_id": food["id"], "quantity": 1}]},
    )
    assert order.status_code == 201, order.text
    assert order.json()["customer_id"] == str(newcomer.id)
    assert order.json()["status"] == "pending"
    assert order.json()["delivery_address"]["flat"] == "B-502"
    # Repeating onboarding does not silently move an existing resident's address.
    data["flat"] = "B-999"
    assert client.post(f"/api/v1/societies/{society_id}/join", json=data).status_code == 409


def test_cross_society_tower_and_listing_ids_are_rejected(client, session, market):
    as_user(client, market["outsider"])
    response = client.post(
        f"/api/v1/societies/{market['society'].id}/join",
        json={"tower_id": str(market["other_tower"].id), "flat": "Z-101"},
    )
    assert response.status_code == 422
    assert (
        session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.user_id == market["outsider"].id,
                Membership.society_id == market["society"].id,
            )
        )
        == 0
    )
    food = publish(client, market)
    as_user(client, market["outsider"])
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == 403
    assert client.get(f"/api/v1/kitchens/{market['kitchen'].id}").status_code == 403
    assert (
        client.patch(
            f"/api/v1/menu-listings/{food['id']}", json={"quantity_total": 100}
        ).status_code
        == 403
    )


def test_join_waits_for_society_pause_and_does_not_create_membership(session_factory, market):
    society_id = market["society"].id
    newcomer_id = market["outsider"].id
    tower_id = market["tower"].id
    request_started = Event()
    request_finished = Event()
    request_pid = {}

    def joining_resident():
        with session_factory() as request_session:
            request_session.execute(text("SET LOCAL lock_timeout = '5s'"))
            request_session.execute(text("SET LOCAL statement_timeout = '8s'"))
            user = request_session.get(User, newcomer_id)
            # A request may already hold the society's previously active state.
            previous_society = request_session.get(Society, society_id)
            assert previous_society.status == "active"
            request_pid["value"] = request_session.scalar(select(func.pg_backend_pid()))
            request_started.set()
            try:
                catalog.join_society(
                    request_session,
                    user,
                    society_id,
                    MembershipJoin(tower_id=tower_id, flat="B-502"),
                )
                request_session.commit()
                return None
            except DomainError as exc:
                request_session.rollback()
                return exc.code
            finally:
                request_finished.set()

    with session_factory() as administrator, ThreadPoolExecutor(max_workers=1) as pool:
        society = administrator.scalar(
            select(Society).where(Society.id == society_id).with_for_update()
        )
        society.status = "paused"
        administrator.flush()
        administrator_pid = administrator.scalar(select(func.pg_backend_pid()))
        future = pool.submit(joining_resident)
        try:
            assert request_started.wait(timeout=3)
            deadline = monotonic() + 3
            while True:
                blockers = administrator.scalar(select(func.pg_blocking_pids(request_pid["value"])))
                if administrator_pid in blockers:
                    break
                assert not request_finished.is_set(), "Join finished before the pause committed"
                assert monotonic() < deadline, "Join did not wait on the society transaction"
                request_finished.wait(timeout=0.01)
            # PostgreSQL confirms this transaction blocks the resident; no sleep
            # or thread-scheduling assumption determines when to commit the pause.
            assert not future.done()
            administrator.commit()
            assert future.result(timeout=5) == "society_unavailable"
        finally:
            administrator.rollback()
    with session_factory() as verification:
        assert verification.get(Society, society_id).status == "paused"
        assert (
            verification.scalar(
                select(Membership.id).where(
                    Membership.user_id == newcomer_id,
                    Membership.society_id == society_id,
                )
            )
            is None
        )


def test_kitchen_approval_and_discovery_privacy(admin_client, client, session, market):
    kitchen = market["kitchen"]
    kitchen.status = "pending"
    session.commit()
    as_user(client, market["owner"])
    assert (
        client.post(
            f"/api/v1/kitchens/{kitchen.id}/menu-listings", json=listing_payload(market)
        ).status_code
        == 409
    )
    assert (
        admin_client.post(
            f"/api/v1/kitchens/{kitchen.id}/approve", json={"fssai_number": "12345678901234"}
        ).status_code
        == 200
    )
    food = publish(client, market)
    public = food["kitchen"]
    assert public["tower_name"] == "Tower B"
    assert public["fssai_number"] == "12345678901234"
    assert "flat" not in public and "phone" not in public and "upi_id" not in public
    as_user(client, market["owner"])
    own = client.get("/api/v1/me/kitchens").json()[0]
    assert own["flat"] == "B-1204"
    changed = client.patch(
        f"/api/v1/kitchens/{kitchen.id}", json={"fssai_number": "98765432109876"}
    )
    assert changed.json()["status"] == "pending"
    as_user(client, market["customer"])
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == 404


def test_cook_again_reuses_dish_and_validates_service_timezone(client, session, market):
    as_user(client, market["owner"])
    payload = listing_payload(market)
    payload["available_from"] = payload["available_from"].replace("+00:00", "")
    assert (
        client.post(
            f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings", json=payload
        ).status_code
        == 422
    )
    payload = listing_payload(market)
    payload["service_date"] = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    assert (
        client.post(
            f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings", json=payload
        ).status_code
        == 422
    )
    first = publish(client, market)
    second = publish(client, market, listing_payload(market, days=2))
    assert first["dish"]["id"] == second["dish"]["id"]
    assert first["id"] != second["id"]
    assert session.scalar(select(func.count()).select_from(Dish)) == 1
    assert session.scalar(select(func.count()).select_from(MenuListing)) == 2


def test_reserved_listing_cannot_change_price_window_or_drop_stock(client, market):
    food = publish(client, market)
    as_user(client, market["customer"])
    order = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "catalog-stock-protection"},
        json={
            "items": [{"menu_listing_id": food["id"], "quantity": 2}],
            "fulfillment_type": "pickup",
        },
    )
    assert order.status_code == 201, order.text
    as_user(client, market["owner"])
    for changes in ({"quantity_total": 1}, {"price_paise": 16000}, {"status": "draft"}):
        assert client.patch(f"/api/v1/menu-listings/{food['id']}", json=changes).status_code == 409
    assert client.delete(f"/api/v1/menu-listings/{food['id']}").status_code == 409
    increased = client.patch(f"/api/v1/menu-listings/{food['id']}", json={"quantity_total": 10})
    assert increased.status_code == 200, increased.text
    assert increased.json()["quantity_remaining"] == 8


def test_kitchen_delivery_fee_is_used_for_listings_and_pickup_stays_free(client, market):
    as_user(client, market["owner"])
    kitchen_path = f"/api/v1/kitchens/{market['kitchen'].id}"
    configured = client.patch(
        kitchen_path, json={"delivery_enabled": True, "delivery_fee_paise": 2000}
    )
    assert configured.status_code == 200, configured.text
    delivery_payload = listing_payload(market)
    delivery_payload["delivery_enabled"] = True
    delivery_food = publish(client, market, delivery_payload)
    assert delivery_food["delivery_fee_paise"] == 2000
    pickup_food = publish(client, market, listing_payload(market, days=2))
    assert pickup_food["delivery_fee_paise"] == 0

    as_user(client, market["customer"])
    pickup = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "kitchen-fee-pickup"},
        json={
            "items": [{"menu_listing_id": delivery_food["id"], "quantity": 1}],
            "fulfillment_type": "pickup",
        },
    )
    assert pickup.status_code == 201, pickup.text
    assert pickup.json()["delivery_fee_paise"] == 0
    delivery = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "kitchen-fee-delivery"},
        json={
            "items": [{"menu_listing_id": delivery_food["id"], "quantity": 1}],
            "fulfillment_type": "delivery",
        },
    )
    assert delivery.status_code == 201, delivery.text
    assert delivery.json()["delivery_fee_paise"] == 2000

    as_user(client, market["owner"])
    assert client.patch(kitchen_path, json={"delivery_fee_paise": 3000}).status_code == 200
    as_user(client, market["customer"])
    assert (
        client.get(f"/api/v1/menu-listings/{delivery_food['id']}").json()["delivery_fee_paise"]
        == 3000
    )
    assert (
        client.get(f"/api/v1/orders/{delivery.json()['id']}").json()["delivery_fee_paise"] == 2000
    )


def test_membership_suspension_and_bounded_feed(admin_client, client, session, market):
    food = publish(client, market)
    as_user(client, market["customer"])
    assert client.get(f"/api/v1/societies/{market['society'].id}/menu?limit=101").status_code == 422
    membership = session.scalar(
        select(Membership).where(Membership.user_id == market["customer"].id)
    )
    assert admin_client.post(f"/api/v1/memberships/{membership.id}/suspend").status_code == 200
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == 403
    for flat in (membership.flat, "B-999"):
        rejoin = client.post(
            f"/api/v1/societies/{market['society'].id}/join",
            json={"tower_id": str(market["tower"].id), "flat": flat},
        )
        assert rejoin.status_code == 403, rejoin.text
    session.expire_all()
    assert session.get(Membership, membership.id).status == "suspended"
    assert session.get(Membership, membership.id).flat == "B-1001"
    restored = admin_client.post(f"/api/v1/memberships/{membership.id}/activate")
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "active"
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == 200


@pytest.mark.parametrize("remaining_role", [None, "manager", "owner"])
def test_suspending_last_active_kitchen_owner_stops_orders(
    admin_client, client, session, market, remaining_role
):
    food = publish(client, market)
    if remaining_role:
        session.add(
            KitchenMember(
                kitchen_id=market["kitchen"].id,
                user_id=market["customer"].id,
                role=remaining_role,
            )
        )
        session.commit()
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == market["owner"].id,
            Membership.society_id == market["society"].id,
        )
    )
    response = admin_client.post(f"/api/v1/memberships/{membership.id}/suspend")
    assert response.status_code == 200, response.text
    session.expire_all()
    assert session.get(Kitchen, market["kitchen"].id).status == (
        "approved" if remaining_role == "owner" else "suspended"
    )
    as_user(client, market["customer"])
    assert client.get(f"/api/v1/menu-listings/{food['id']}").status_code == (
        200 if remaining_role == "owner" else 404
    )
    order = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "last-member-suspension"},
        json={
            "items": [{"menu_listing_id": food["id"], "quantity": 1}],
            "fulfillment_type": "pickup",
        },
    )
    assert order.status_code == (201 if remaining_role == "owner" else 409), order.text


@pytest.mark.parametrize(
    "image_url",
    ["http://example.com/food.jpg", "file:///tmp/food.jpg", "javascript:alert(1)", "https://"],
)
def test_dish_photos_require_valid_https_urls(client, market, image_url):
    as_user(client, market["owner"])
    response = client.post(
        f"/api/v1/kitchens/{market['kitchen'].id}/dishes",
        json={"name": "Lunch", "image_url": image_url},
    )
    assert response.status_code == 422
    response = client.patch(f"/api/v1/dishes/{market['dish'].id}", json={"image_url": image_url})
    assert response.status_code == 422
