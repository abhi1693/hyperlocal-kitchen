"""Admin catalog access retains resident boundaries and committed inventory."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID

import pytest
from kitchen_core import catalog
from kitchen_core.catalog_schemas import KitchenCreate, MembershipJoin
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Community,
    CommunityZone,
    Dish,
    Kitchen,
    KitchenMember,
    Membership,
    PickupPoint,
    User,
)
from kitchen_http.auth import require_admin, require_user
from sqlalchemy import select


@pytest.fixture
def food_market(session):
    communities = [
        Community(
            name=name, address="Pilot Road", city="Pune", postal_code="411001", status="active"
        )
        for name in ("Garden Community", "Other Community")
    ]
    users = [
        User(
            oidc_subject=f"admin-food-{name}",
            oidc_issuer="https://identity.example.test",
            name=name,
            is_active=name != "inactive",
        )
        for name in ("owner", "resident", "outsider", "inactive")
    ]
    session.add_all(communities + users)
    session.flush()
    community, other = communities
    owner, resident, outsider, inactive = users
    zones = [
        CommunityZone(community_id=community.id, name="Zone B"),
        CommunityZone(community_id=community.id, name="Zone C"),
        CommunityZone(community_id=other.id, name="Zone Z"),
    ]
    session.add_all(zones)
    session.flush()
    zone, second_zone, other_zone = zones
    for user in (owner, resident, inactive):
        session.add(
            Membership(
                community_id=community.id,
                user_id=user.id,
                zone_id=zone.id,
                address_label="B-101",
                status="active",
            )
        )
    session.add(
        Membership(
            community_id=other.id,
            user_id=outsider.id,
            zone_id=other_zone.id,
            address_label="Z-101",
            status="active",
        )
    )
    kitchen = Kitchen(
        community_id=community.id,
        name="Manisha's Kitchen",
        zone_id=zone.id,
        address_label="B-101",
        status="approved",
        fssai_number="12345678901234",
        pickup_enabled=True,
        delivery_enabled=False,
    )
    other_kitchen = Kitchen(
        community_id=other.id,
        name="Other Kitchen",
        zone_id=other_zone.id,
        address_label="Z-101",
        status="pending",
    )
    session.add_all([kitchen, other_kitchen])
    session.flush()
    session.add(
        PickupPoint(
            community_id=community.id,
            kitchen_id=kitchen.id,
            zone_id=zone.id,
            name=kitchen.name,
            address_label=kitchen.address_label,
        )
    )
    session.add_all(
        [
            KitchenMember(kitchen_id=kitchen.id, user_id=owner.id, role="owner"),
            KitchenMember(kitchen_id=other_kitchen.id, user_id=outsider.id, role="owner"),
        ]
    )
    dish = Dish(kitchen_id=kitchen.id, name="Rajma Chawal", is_active=True)
    session.add(dish)
    session.commit()
    return dict(
        community=community,
        other=other,
        zone=zone,
        second_zone=second_zone,
        other_zone=other_zone,
        owner=owner,
        resident=resident,
        outsider=outsider,
        inactive=inactive,
        kitchen=kitchen,
        other_kitchen=other_kitchen,
        dish=dish,
    )


def listing_data(market):
    ready = datetime.now(UTC).replace(hour=7, minute=30, second=0, microsecond=0) + timedelta(
        days=2
    )
    return dict(
        dish_id=str(market["dish"].id),
        service_date=ready.date().isoformat(),
        available_from=ready.isoformat(),
        available_until=(ready + timedelta(hours=2)).isoformat(),
        order_cutoff=(ready - timedelta(minutes=30)).isoformat(),
        price_paise=15000,
        quantity_total=8,
    )


def admin_publish(admin_client, market, **changes):
    data = listing_data(market) | changes
    response = admin_client.post(
        f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings", json=data
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_for_real_resident_and_corrects_same_community_address(
    admin_client, session, food_market
):
    market = food_market
    response = admin_client.post(
        "/api/v1/kitchens",
        json={
            "owner_user_id": str(market["resident"].id),
            "community_id": str(market["community"].id),
            "name": "Resident's Kitchen",
        },
    )
    assert response.status_code == 201, response.text
    kitchen = response.json()
    assert kitchen["status"] == "pending"
    assert kitchen["zone_id"] == str(market["zone"].id)
    assert kitchen["address_label"] == "B-101"
    member = session.get(KitchenMember, (UUID(kitchen["id"]), market["resident"].id))
    assert member is not None and member.role == "owner"
    path = f"/api/v1/kitchens/{kitchen['id']}"
    assert (
        admin_client.patch(path, json={"zone_id": str(market["other_zone"].id)}).status_code == 422
    )
    corrected = admin_client.patch(
        path,
        json={
            "zone_id": str(market["second_zone"].id),
            "address_label": "C-204",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["zone_name"] == "Zone C"
    assert corrected.json()["address_label"] == "C-204"
    assert admin_client.patch(path, json={"status": "approved"}).status_code == 422
    assert (
        admin_client.post(path + "/approve", json={"fssai_number": "12345678901234"}).status_code
        == 200
    )
    assert admin_client.post(path + "/suspend").status_code == 200
    # Administrators can correct suspended metadata without implicitly approving the kitchen.
    corrected = admin_client.patch(path, json={"name": "Corrected Kitchen"})
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "suspended"
    rejected = admin_client.post(
        "/api/v1/kitchens",
        json={
            "owner_user_id": str(market["inactive"].id),
            "community_id": str(market["community"].id),
            "name": "Inactive Kitchen",
        },
    )
    assert rejected.status_code == 403


def test_admin_members_cannot_cross_community_or_remove_last_active_owner(
    admin_client, food_market
):
    market = food_market
    path = f"/api/v1/kitchens/{market['kitchen'].id}/members"
    for name in ("outsider", "inactive"):
        assert admin_client.post(path, json={"user_id": str(market[name].id)}).status_code == 403
    owner_path = f"{path}/{market['owner'].id}"
    assert admin_client.patch(owner_path, json={"role": "manager"}).status_code == 409
    assert admin_client.delete(owner_path).status_code == 409
    response = admin_client.post(path, json={"user_id": str(market["resident"].id)})
    assert response.status_code == 201
    assert response.json()["role"] == "manager"
    resident_path = f"{path}/{market['resident'].id}"
    assert admin_client.post(path, json={"user_id": str(market["resident"].id)}).status_code == 409
    assert admin_client.patch(resident_path, json={"role": "owner"}).status_code == 200
    assert admin_client.delete(owner_path).status_code == 204
    assert admin_client.delete(resident_path).status_code == 409
    page = admin_client.get(path, params={"sort": "name", "q": "resident"}).json()
    assert page["total"] == 1 and page["items"][0]["user_name"] == "resident"


def test_admin_lists_across_communities_and_archives_and_restores_reusable_dishes(
    admin_client, client, food_market
):
    market = food_market
    kitchens = admin_client.get("/api/v1/kitchens", params={"sort": "name"}).json()
    assert kitchens["total"] == 2
    assert (
        admin_client.get(
            "/api/v1/kitchens", params={"community_id": str(market["other"].id)}
        ).json()["total"]
        == 1
    )
    operated = admin_client.get(
        "/api/v1/kitchens", params={"user_id": str(market["owner"].id), "limit": 1}
    ).json()
    assert operated["total"] == 1
    assert operated["items"][0]["id"] == str(market["kitchen"].id)
    assert (
        admin_client.get(
            "/api/v1/kitchens",
            params={"user_id": str(market["owner"].id), "community_id": str(market["other"].id)},
        ).json()["total"]
        == 0
    )
    assert (
        admin_client.get("/api/v1/kitchens", params={"user_id": str(market["resident"].id)}).json()[
            "total"
        ]
        == 0
    )
    response = admin_client.post(
        "/api/v1/dishes",
        json={
            "kitchen_id": str(market["other_kitchen"].id),
            "name": "Chole Rice",
        },
    )
    assert response.status_code == 201
    other_dish = response.json()
    path = f"/api/v1/dishes/{other_dish['id']}"
    assert admin_client.delete(path).status_code == 204
    archived = admin_client.get("/api/v1/dishes", params={"is_active": False}).json()
    assert archived["total"] == 1 and archived["items"][0]["id"] == other_dish["id"]
    assert admin_client.patch(path, json={"name": "Chole and Rice"}).status_code == 200
    assert admin_client.post(path + "/restore").json()["is_active"] is True
    assert (
        admin_client.get("/api/v1/dishes", params={"community_id": str(market["other"].id)}).json()[
            "total"
        ]
        == 1
    )
    assert admin_client.get("/api/v1/dishes", params={"limit": 101}).status_code == 422
    assert admin_client.get("/api/v1/dishes", params={"offset": 10001}).status_code == 422
    assert admin_client.get("/api/v1/dishes", params={"sort": "image_url"}).status_code == 422
    client.app.dependency_overrides[require_user] = lambda: market["owner"]
    assert client.patch(path, json={"name": "Foreign change"}).status_code == 403
    assert client.post(path + "/restore").status_code == 404
    assert (
        client.post(
            f"/api/v1/kitchens/{market['kitchen'].id}/members",
            json={"user_id": str(market["resident"].id)},
        ).status_code
        == 404
    )


def test_admin_listing_mutations_preserve_reserved_price_window_and_live_orders(
    admin_client, client, session, food_market
):
    market = food_market
    listing = admin_publish(admin_client, market)
    # A second reusable dish must not duplicate listing rows through an ambiguous join.
    admin_client.post(f"/api/v1/kitchens/{market['kitchen'].id}/dishes", json={"name": "Paratha"})
    listing_page = admin_client.get(
        "/api/v1/menu-listings",
        params={
            "community_id": str(market["community"].id),
            "q": "Rajma",
        },
    ).json()
    assert listing_page["total"] == 1 and len(listing_page["items"]) == 1
    client.app.dependency_overrides[require_user] = lambda: market["resident"]
    placed = client.post(
        "/api/v1/orders",
        json={
            "items": [{"menu_listing_id": listing["id"], "quantity": 2}],
            "fulfillment_type": "pickup",
        },
        headers={"Idempotency-Key": "admin-food-inventory"},
    )
    assert placed.status_code == 201, placed.text
    path = f"/api/v1/menu-listings/{listing['id']}"
    for changes in (
        {"quantity_total": 1},
        {"price_paise": 20000},
        {"status": "draft"},
        {"available_until": listing_data(market)["available_from"]},
    ):
        assert admin_client.patch(path, json=changes).status_code == 409
    assert admin_client.patch(path, json={"quantity_reserved": 0}).status_code == 422
    assert admin_client.delete(path).status_code == 409
    changed = admin_client.patch(path, json={"quantity_total": 10})
    assert changed.status_code == 200
    assert changed.json()["quantity_remaining"] == 8
    corrected = admin_client.patch(
        f"/api/v1/kitchens/{market['kitchen'].id}", json={"address_label": "B-999"}
    )
    assert corrected.status_code == 200
    order = client.get(f"/api/v1/orders/{placed.json()['id']}").json()
    assert order["pickup_address"]["address_label"] == "B-101"
    assert order["total_paise"] == 30000
    cancelled = client.post(f"/api/v1/orders/{placed.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert admin_client.delete(path).status_code == 204
    assert admin_client.get(path).json()["status"] == "cancelled"
    # Cancelled listings and reusable dishes remain linked to order history.
    assert admin_client.delete(f"/api/v1/kitchens/{market['kitchen'].id}").status_code == 409
    assert session.scalar(select(Dish.id).where(Dish.id == market["dish"].id)) is not None


def test_admin_still_requires_approved_kitchen_active_community_and_own_dish(
    admin_client, client, session, food_market
):
    market = food_market
    path = f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings"
    other_dish = admin_client.post(
        "/api/v1/dishes",
        json={
            "kitchen_id": str(market["other_kitchen"].id),
            "name": "Other dish",
        },
    ).json()
    data = listing_data(market)
    assert admin_client.post(path, json=data | {"dish_id": other_dish["id"]}).status_code == 422
    assert (
        admin_client.post(path, json=data | {"available_from": "2026-10-09T13:00:00"}).status_code
        == 422
    )
    assert admin_client.post(path, json=data | {"delivery_enabled": True}).status_code == 422
    archived_draft = admin_publish(admin_client, market, status="draft")
    dish_path = f"/api/v1/dishes/{market['dish'].id}"
    assert admin_client.delete(dish_path).status_code == 204
    publish_path = f"/api/v1/menu-listings/{archived_draft['id']}"
    assert admin_client.patch(publish_path, json={"status": "published"}).status_code == 422
    assert admin_client.post(dish_path + "/restore").status_code == 200
    assert admin_client.patch(publish_path, json={"status": "published"}).status_code == 200
    market["community"].status = "paused"
    session.commit()
    assert admin_client.post(path, json=data).status_code == 409
    draft = admin_publish(admin_client, market, status="draft")
    assert (
        admin_client.patch(
            f"/api/v1/menu-listings/{draft['id']}", json={"status": "published"}
        ).status_code
        == 409
    )
    market["community"].status = "active"
    session.commit()
    assert admin_client.post(f"/api/v1/kitchens/{market['kitchen'].id}/suspend").status_code == 200
    assert admin_client.post(path, json=data).status_code == 409
    client.app.dependency_overrides[require_user] = lambda: market["owner"]
    assert client.post(path, json=data | {"admin": True}).status_code == 422


def test_admin_deletes_only_unused_kitchens_and_requires_admin_identity(admin_client, food_market):
    market = food_market
    assert admin_client.delete(f"/api/v1/kitchens/{market['other_kitchen'].id}").status_code == 204
    assert admin_client.get(f"/api/v1/kitchens/{market['other_kitchen'].id}").status_code == 404
    assert admin_client.delete(f"/api/v1/kitchens/{market['kitchen'].id}").status_code == 409
    admin_client.app.dependency_overrides.pop(require_admin)
    admin_client.app.dependency_overrides[require_user] = lambda: market["owner"]
    assert admin_client.get("/api/v1/kitchens").status_code == 401


@pytest.mark.parametrize("operation", ["join", "create_kitchen"])
def test_waiting_resident_mutation_rechecks_deactivated_user(
    session_factory, food_market, operation
):
    market = food_market
    started = Event()

    def waiting_request():
        with session_factory() as request_session:
            # Simulate dependencies that loaded the account before waiting for its lock.
            user = request_session.get(User, market["resident"].id)
            request_session.scalar(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.community_id == market["community"].id,
                )
            )
            started.set()
            try:
                if operation == "join":
                    catalog.join_community(
                        request_session,
                        user,
                        market["community"].id,
                        MembershipJoin(zone_id=market["zone"].id, address_label="B-101"),
                    )
                else:
                    catalog.create_kitchen(
                        request_session,
                        user,
                        KitchenCreate(community_id=market["community"].id, name="Waiting Kitchen"),
                    )
                request_session.commit()
                return None
            except DomainError as exc:
                request_session.rollback()
                return exc.code

    with session_factory() as administrator, ThreadPoolExecutor(max_workers=1) as pool:
        user = administrator.scalar(
            select(User).where(User.id == market["resident"].id).with_for_update(key_share=True)
        )
        future = pool.submit(waiting_request)
        try:
            assert started.wait(timeout=5)
            assert not future.done()
            user.is_active = False
            membership = administrator.scalar(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.community_id == market["community"].id,
                )
            )
            membership.status = "suspended"
            administrator.commit()
            assert future.result(timeout=5) == "user_inactive"
        finally:
            # Release the lock even when an assertion fails, before the pool joins its worker.
            administrator.rollback()
    with session_factory() as verification:
        assert (
            verification.scalar(
                select(Kitchen.id)
                .join(KitchenMember)
                .where(
                    KitchenMember.user_id == market["resident"].id,
                )
            )
            is None
        )


def test_listing_cancellation_available_after_pause_suspend_or_fulfillment_change(
    admin_client, client, session, food_market
):
    market = food_market
    owner_listing = admin_publish(admin_client, market)
    admin_listing = admin_publish(admin_client, market)
    committed_listing = admin_publish(admin_client, market)
    client.app.dependency_overrides[require_user] = lambda: market["resident"]
    placed = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "unavailable-cancel"},
        json={
            "items": [{"menu_listing_id": committed_listing["id"], "quantity": 2}],
            "fulfillment_type": "pickup",
        },
    )
    assert placed.status_code == 201, placed.text
    path = f"/api/v1/kitchens/{market['kitchen'].id}"
    assert (
        admin_client.patch(
            path, json={"pickup_enabled": False, "delivery_enabled": True}
        ).status_code
        == 200
    )
    listing_path = f"/api/v1/menu-listings/{owner_listing['id']}"
    assert admin_client.get(listing_path).json()["is_orderable"] is False
    assert client.get(listing_path).json()["is_orderable"] is False
    assert admin_client.post(path + "/suspend").status_code == 200
    market["community"].status = "paused"
    session.commit()
    client.app.dependency_overrides[require_user] = lambda: market["owner"]
    committed_path = f"/api/v1/menu-listings/{committed_listing['id']}"
    assert client.delete(committed_path).status_code == 409
    assert admin_client.delete(committed_path).status_code == 409
    assert client.delete(f"/api/v1/menu-listings/{owner_listing['id']}").status_code == 200
    assert admin_client.delete(f"/api/v1/menu-listings/{admin_listing['id']}").status_code == 204
    # Unavailability still prevents publishing; cancellation is the only relaxed action.
    assert admin_client.post(path + "/menu-listings", json=listing_data(market)).status_code == 409
