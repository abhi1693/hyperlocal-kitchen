"""Community onboarding and independent fulfillment across the actual HTTP/database boundary."""

from datetime import timedelta
from uuid import UUID

import pytest
from kitchen_core import catalog
from kitchen_core.models import (
    CommunityZone,
    Kitchen,
    ListingPickupPoint,
    Membership,
    MenuListing,
    Order,
    PickupPoint,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_catalog import as_user, listing_payload, publish
from test_catalog import market as catalog_market


@pytest.fixture
def market(session):
    return catalog_market.__wrapped__(session)


def point(client, community_id, *, name="Community Centre", zone_id=None):
    response = client.post(
        f"/api/v1/communities/{community_id}/pickup-points",
        json={
            "name": name,
            "zone_id": str(zone_id) if zone_id else None,
            "address_label": "Main entrance",
            "instructions": "Collect at the counter",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def checkout(client, listing, *, key="pickup-checkout", **destination):
    return client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": key},
        json={
            "items": [{"menu_listing_id": listing["id"], "quantity": 2}],
            **destination,
        },
    )


def test_cantonment_join_needs_no_zone_address_or_approval(admin_client, client, market):
    created = admin_client.post(
        "/api/v1/communities",
        json={
            "name": "Example Cantonment",
            "city": "Pune",
            "type": "cantonment",
        },
    )
    assert created.status_code == 201, created.text
    community = created.json()
    assert community["type"] == "cantonment" and community["zones"] == []
    assert admin_client.post(f"/api/v1/communities/{community['id']}/activate").status_code == 200
    as_user(client, market["customer"])
    joined = client.post(f"/api/v1/communities/{community['id']}/join", json={})
    assert joined.status_code == 201, joined.text
    assert joined.json()["status"] == "active"
    assert joined.json()["zone_id"] is None and joined.json()["address_label"] is None
    assert (
        client.post(f"/api/v1/communities/{community['id']}/join", json={}).json()["id"]
        == joined.json()["id"]
    )
    listed = admin_client.get("/api/v1/memberships", params={"community_id": community["id"]})
    assert listed.json()["total"] == 1  # nullable zone must survive the admin list join


def test_zone_hierarchy_rejects_cycles_cross_community_and_referenced_deletion(
    admin_client, market
):
    community_id = market["community"].id
    root = market["zone"].id
    path = f"/api/v1/communities/{community_id}/zones"
    child = admin_client.post(
        path, json={"name": "Area A", "zone_type": "area", "parent_zone_id": str(root)}
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]
    assert (
        admin_client.patch(f"/api/v1/zones/{root}", json={"parent_zone_id": child_id}).status_code
        == 422
    )
    assert (
        admin_client.patch(
            f"/api/v1/zones/{child_id}", json={"parent_zone_id": str(market["other_zone"].id)}
        ).status_code
        == 422
    )
    assert admin_client.delete(f"/api/v1/zones/{root}").status_code == 409
    assert (
        admin_client.patch(f"/api/v1/zones/{child_id}", json={"parent_zone_id": None}).status_code
        == 200
    )


def test_pickup_works_without_home_and_snapshots_selected_point(
    admin_client, client, session, market
):
    p = point(admin_client, market["community"].id)
    food = publish(client, market, {**listing_payload(market), "pickup_point_ids": [p["id"]]})
    home = session.scalar(select(Membership).where(Membership.user_id == market["customer"].id))
    home.zone_id = None
    home.address_label = None
    session.commit()
    as_user(client, market["customer"])
    response = checkout(client, food, pickup_point_id=p["id"])
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["pickup_point_id"] == p["id"]
    assert order["delivery_address"] is None
    assert order["fulfillment_snapshot"]["name"] == "Community Centre"
    assert order["fulfillment_snapshot"]["instructions"] == "Collect at the counter"
    assert order["total_paise"] == 30000
    changed = admin_client.patch(
        f"/api/v1/pickup-points/{p['id']}",
        json={"address_label": "Another entrance", "active": False},
    )
    assert changed.status_code == 200
    replay = checkout(client, food, pickup_point_id=p["id"])
    assert replay.status_code == 201 and replay.json()["id"] == order["id"]
    assert replay.json()["fulfillment_snapshot"]["address_label"] == "Main entrance"
    assert (
        checkout(client, food, key="new-after-deactivation", pickup_point_id=p["id"]).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/communities/{market['community'].id}/menu",
            params={"date": food["service_date"]},
        ).json()["items"][0]["is_orderable"]
        is False
    )


def test_delivery_address_is_independent_and_in_idempotency_hash(
    admin_client, client, session, market
):
    kitchen = market["kitchen"]
    kitchen.delivery_enabled = True
    kitchen.delivery_fee_paise = 2500
    session.commit()
    food = publish(client, market, {**listing_payload(market), "delivery_enabled": True})
    as_user(client, market["customer"])
    destination = {"zone_id": str(market["zone"].id), "address_label": "House 42"}
    result = checkout(client, food, fulfillment_type="delivery", delivery_address=destination)
    assert result.status_code == 201, result.text
    order = result.json()
    assert order["pickup_point_id"] is None and order["pickup_address"] is None
    assert order["fulfillment_snapshot"]["address_label"] == "House 42"
    assert order["total_paise"] == 32500
    assert (
        checkout(
            client,
            food,
            fulfillment_type="delivery",
            delivery_address={**destination, "address_label": "House 43"},
        ).status_code
        == 409
    )
    assert (
        checkout(
            client,
            food,
            key="wrong-zone",
            fulfillment_type="delivery",
            delivery_address={**destination, "zone_id": str(market["other_zone"].id)},
        ).status_code
        == 422
    )
    assert (
        checkout(
            client,
            food,
            key="mixed-destination",
            fulfillment_type="delivery",
            pickup_point_id=food["pickup_points"][0]["id"],
        ).status_code
        == 422
    )


def test_home_address_can_be_saved_cleared_and_required_only_for_delivery(client, session, market):
    market["kitchen"].delivery_enabled = True
    session.commit()
    food = publish(client, market, {**listing_payload(market), "delivery_enabled": True})
    home = session.scalar(select(Membership).where(Membership.user_id == market["customer"].id))
    path = f"/api/v1/me/memberships/{home.id}"
    as_user(client, market["customer"])
    assert client.patch(path, json={"zone_id": None, "address_label": None}).status_code == 200
    missing = checkout(client, food, fulfillment_type="delivery")
    assert (
        missing.status_code == 422
        and missing.json()["detail"]["code"] == "delivery_address_required"
    )
    assert client.patch(path, json={"address_label": "House 9"}).status_code == 200
    result = checkout(client, food, fulfillment_type="delivery")
    assert result.status_code == 201, result.text
    assert result.json()["fulfillment_snapshot"]["address_label"] == "House 9"
    as_user(client, market["owner"])
    assert client.patch(path, json={"address_label": "Changed by someone else"}).status_code == 404


def test_pickup_selection_and_listing_edits_respect_basket_and_reservations(
    admin_client, client, session, market
):
    p = point(admin_client, market["community"].id)
    other = point(admin_client, market["other"].id)
    home_point = session.scalar(
        select(PickupPoint).where(PickupPoint.kitchen_id == market["kitchen"].id)
    )
    first = publish(
        client,
        market,
        {**listing_payload(market), "pickup_point_ids": [p["id"], str(home_point.id)]},
    )
    second = publish(
        client, market, {**listing_payload(market), "pickup_point_ids": [str(home_point.id)]}
    )
    as_user(client, market["customer"])
    assert checkout(client, first).status_code == 422  # more than one offered point needs a choice
    assert checkout(client, first, key="foreign", pickup_point_id=other["id"]).status_code == 422
    mixed = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "mixed"},
        json={
            "items": [
                {"menu_listing_id": first["id"], "quantity": 1},
                {"menu_listing_id": second["id"], "quantity": 1},
            ],
            "pickup_point_id": p["id"],
        },
    )
    assert mixed.status_code == 422
    result = checkout(client, first, key="chosen", pickup_point_id=p["id"])
    assert result.status_code == 201, result.text
    assert (
        checkout(client, first, key="chosen", pickup_point_id=str(home_point.id)).status_code == 409
    )
    as_user(client, market["owner"])
    assert (
        client.patch(
            f"/api/v1/menu-listings/{first['id']}", json={"pickup_point_ids": [str(home_point.id)]}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/menu-listings/{first['id']}",
            json={"pickup_point_ids": [str(home_point.id), p["id"]]},
        ).status_code
        == 200
    )
    invalid = client.post(
        f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings",
        json={**listing_payload(market), "pickup_point_ids": [other["id"]]},
    )
    assert invalid.status_code == 422


def test_kitchens_manage_only_their_own_points(admin_client, client, market):
    shared = point(admin_client, market["community"].id)
    as_user(client, market["owner"])
    path = f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points"
    created = client.post(path, json={"name": "Kitchen Pickup", "address_label": "House 3"})
    assert created.status_code == 201, created.text
    assert (
        client.patch(
            path + f"/{created.json()['id']}", json={"instructions": "Ring bell"}
        ).status_code
        == 200
    )
    assert client.patch(path + f"/{shared['id']}", json={"active": False}).status_code == 404
    as_user(client, market["customer"])
    assert (
        client.post(path, json={"name": "Unauthorized", "address_label": "House 4"}).status_code
        == 403
    )
    as_user(client, market["outsider"])
    assert (
        client.get(f"/api/v1/communities/{market['community'].id}/pickup-points").status_code == 403
    )


def test_kitchen_location_is_independent_of_owner_home(admin_client, client, session, market):
    as_user(client, market["customer"])
    created = client.post(
        "/api/v1/kitchens",
        json={
            "community_id": str(market["community"].id),
            "name": "New Kitchen",
            "zone_id": None,
            "address_label": "House 88",
        },
    )
    assert created.status_code == 201, created.text
    kitchen = created.json()
    assert kitchen["zone_id"] is None and kitchen["address_label"] == "House 88"
    home = session.scalar(select(Membership).where(Membership.user_id == market["customer"].id))
    assert (
        client.patch(
            f"/api/v1/me/memberships/{home.id}", json={"address_label": "House 89"}
        ).status_code
        == 200
    )
    session.expire_all()
    assert session.get(Kitchen, UUID(kitchen["id"])).address_label == "House 88"
    points = client.get(f"/api/v1/kitchens/{kitchen['id']}/pickup-points").json()
    assert points[0]["address_label"] == "House 88"


@pytest.mark.parametrize(
    "relation", ["parent_zone", "pickup_zone", "pickup_kitchen", "listing_point", "order_point"]
)
def test_new_location_foreign_keys_reject_other_communities(session, market, relation):
    kitchen = market["kitchen"]
    foreign_point = PickupPoint(
        community_id=market["other"].id, name="Other Point", address_label="Other place"
    )
    session.add(foreign_point)
    session.flush()
    ready = catalog.utcnow() + timedelta(days=1)
    listing = MenuListing(
        kitchen_id=kitchen.id,
        dish_id=market["dish"].id,
        service_date=ready.date(),
        available_from=ready,
        available_until=ready + timedelta(hours=1),
        order_cutoff=ready,
        price_paise=10000,
        quantity_total=5,
    )
    session.add(listing)
    session.flush()
    if relation == "parent_zone":
        row = CommunityZone(
            community_id=market["community"].id,
            name="Invalid Child",
            parent_zone_id=market["other_zone"].id,
        )
    elif relation == "pickup_zone":
        row = PickupPoint(
            community_id=market["community"].id,
            zone_id=market["other_zone"].id,
            name="Invalid Point",
            address_label="House",
        )
    elif relation == "pickup_kitchen":
        row = PickupPoint(
            community_id=market["other"].id,
            kitchen_id=kitchen.id,
            name="Invalid Point",
            address_label="House",
        )
    elif relation == "listing_point":
        row = ListingPickupPoint(
            listing_id=listing.id,
            kitchen_id=kitchen.id,
            community_id=kitchen.community_id,
            pickup_point_id=foreign_point.id,
        )
    else:
        row = Order(
            community_id=kitchen.community_id,
            kitchen_id=kitchen.id,
            customer_id=market["customer"].id,
            fulfillment_type="pickup",
            pickup_point_id=foreign_point.id,
            pickup_address={},
            available_from=ready,
            available_until=ready + timedelta(hours=1),
            expires_at=ready,
            subtotal_paise=10000,
            total_paise=10000,
        )
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.add(row)
        session.flush()
    assert error.value.orig.sqlstate == "23503"


def test_kitchen_groups_count_orders_and_portions_without_combining_payments(
    admin_client, client, market
):
    food = publish(client, market)
    as_user(client, market["customer"])
    first = checkout(client, food, key="first").json()
    second = checkout(client, food, key="second").json()
    as_user(client, market["owner"])
    assert client.post(f"/api/v1/orders/{first['id']}/accept").status_code == 200
    path = f"/api/v1/kitchens/{market['kitchen'].id}/fulfillment-groups"
    groups = client.get(path, params={"service_date": food["service_date"]})
    assert groups.status_code == 200, groups.text
    assert groups.json()[0]["order_count"] == 1  # pending orders are not packing commitments
    assert client.post(f"/api/v1/orders/{second['id']}/accept").status_code == 200
    grouped = client.get(path, params={"service_date": food["service_date"]}).json()
    assert len(grouped) == 1 and grouped[0]["order_count"] == 2 and grouped[0]["portion_count"] == 4
    assert set(grouped[0]["order_ids"]) == {first["id"], second["id"]}
    assert admin_client.get(path, params={"service_date": food["service_date"]}).json() == grouped
    as_user(client, market["customer"])
    assert client.get(path, params={"service_date": food["service_date"]}).status_code == 404


def test_switching_listing_to_delivery_clears_points_and_rejects_null_ids(client, session, market):
    market["kitchen"].delivery_enabled = True
    session.commit()
    food = publish(client, market)
    path = f"/api/v1/menu-listings/{food['id']}"
    assert client.patch(path, json={"pickup_point_ids": None}).status_code == 422
    updated = client.patch(path, json={"pickup_enabled": False, "delivery_enabled": True})
    assert updated.status_code == 200, updated.text
    assert updated.json()["pickup_points"] == []
    assert client.patch(path, json={"pickup_enabled": True}).status_code == 422


def test_unused_kitchen_and_its_unreferenced_pickup_point_can_be_removed(
    admin_client, client, market
):
    as_user(client, market["customer"])
    created = client.post(
        "/api/v1/kitchens",
        json={
            "community_id": str(market["community"].id),
            "name": "Unused Kitchen",
            "address_label": "House 88",
        },
    )
    assert created.status_code == 201
    points = client.get(f"/api/v1/kitchens/{created.json()['id']}/pickup-points").json()
    assert len(points) == 1
    assert admin_client.delete(f"/api/v1/kitchens/{created.json()['id']}").status_code == 204
    assert (
        admin_client.patch(
            f"/api/v1/pickup-points/{points[0]['id']}", json={"active": False}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("delivery_enabled", [False, True])
def test_zone_deactivation_hides_points_and_keeps_discovery_consistent(
    admin_client, client, session, market, delivery_enabled
):
    market["kitchen"].delivery_enabled = delivery_enabled
    session.commit()
    food = publish(
        client, market, {**listing_payload(market), "delivery_enabled": delivery_enabled}
    )
    point_id = food["pickup_points"][0]["id"]
    as_user(client, market["customer"])
    placed = checkout(client, food, key="before-zone-deactivation", pickup_point_id=point_id)
    assert placed.status_code == 201, placed.text
    assert (
        admin_client.patch(f"/api/v1/zones/{market['zone'].id}", json={"active": False}).status_code
        == 200
    )
    discovered = client.get(f"/api/v1/menu-listings/{food['id']}").json()
    assert discovered["pickup_points"] == []
    assert discovered["is_orderable"] is delivery_enabled
    assert client.get(f"/api/v1/communities/{market['community'].id}/pickup-points").json() == []
    assert (
        checkout(client, food, key="explicit-inactive-zone", pickup_point_id=point_id).status_code
        == 409
    )
    assert checkout(client, food, key="implicit-inactive-zone").status_code == 422
    replay = checkout(client, food, key="before-zone-deactivation", pickup_point_id=point_id)
    assert replay.status_code == 201 and replay.json()["id"] == placed.json()["id"]
    assert replay.json()["fulfillment_snapshot"] == placed.json()["fulfillment_snapshot"]
    if delivery_enabled:
        delivered = checkout(
            client,
            food,
            key="delivery-still-eligible",
            fulfillment_type="delivery",
            delivery_address={"address_label": "House 42", "zone_id": None},
        )
        assert delivered.status_code == 201, delivered.text
    as_user(client, market["owner"])
    managed = client.get(f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points").json()
    assert [p["id"] for p in managed] == [point_id]
    assert (
        admin_client.get(f"/api/v1/communities/{market['community'].id}/pickup-points").json()[0][
            "id"
        ]
        == point_id
    )
    assert (
        admin_client.patch(f"/api/v1/zones/{market['zone'].id}", json={"active": True}).status_code
        == 200
    )
    restored = client.get(f"/api/v1/menu-listings/{food['id']}").json()
    assert restored["pickup_points"][0]["id"] == point_id and restored["is_orderable"] is True


def test_inactive_zone_points_cannot_be_assigned_or_published(client, admin_client, market):
    draft = publish(client, market, {**listing_payload(market), "status": "draft"})
    point_id = draft["pickup_points"][0]["id"]
    assert (
        admin_client.patch(f"/api/v1/zones/{market['zone'].id}", json={"active": False}).status_code
        == 200
    )
    path = f"/api/v1/kitchens/{market['kitchen'].id}/menu-listings"
    assigned = client.post(path, json={**listing_payload(market), "pickup_point_ids": [point_id]})
    assert (
        assigned.status_code == 422
        and assigned.json()["detail"]["code"] == "pickup_point_unavailable"
    )
    assert client.post(path, json=listing_payload(market)).status_code == 422
    listing_path = f"/api/v1/menu-listings/{draft['id']}"
    assert client.patch(listing_path, json={"pickup_point_ids": [point_id]}).status_code == 422
    assert client.patch(listing_path, json={"status": "published"}).status_code == 422


def test_automatic_selection_skips_inactive_zone_and_keeps_unzoned_points_eligible(
    admin_client, client, market
):
    as_user(client, market["owner"])
    created = client.post(
        f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points",
        json={"name": "Unzoned collection", "address_label": "Community Centre"},
    )
    assert created.status_code == 201, created.text
    eligible_id = created.json()["id"]
    original_id = client.get(f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points").json()[0][
        "id"
    ]
    food = publish(
        client, market, {**listing_payload(market), "pickup_point_ids": [original_id, eligible_id]}
    )
    assert (
        admin_client.patch(f"/api/v1/zones/{market['zone'].id}", json={"active": False}).status_code
        == 200
    )
    default_listing = publish(client, market)
    assert [p["id"] for p in default_listing["pickup_points"]] == [eligible_id]
    as_user(client, market["customer"])
    advertised = client.get(f"/api/v1/menu-listings/{food['id']}").json()
    assert [p["id"] for p in advertised["pickup_points"]] == [eligible_id]
    assert advertised["is_orderable"] is True
    placed = checkout(client, food)
    assert placed.status_code == 201, placed.text
    assert placed.json()["pickup_point_id"] == eligible_id
    assert placed.json()["fulfillment_snapshot"]["zone_name"] is None


def test_user_can_join_home_and_office_with_independent_addresses_and_access(
    admin_client, client, market
):
    home_id = str(market["community"].id)
    office_id = str(market["other"].id)
    assert (
        admin_client.patch(
            f"/api/v1/communities/{office_id}", json={"type": "corporate_campus"}
        ).status_code
        == 200
    )
    as_user(client, market["customer"])
    office = client.post(
        f"/api/v1/communities/{office_id}/join",
        json={
            "zone_id": str(market["other_zone"].id),
            "address_label": "Office reception",
        },
    )
    assert office.status_code == 201, office.text
    memberships = {m["community_id"]: m for m in client.get("/api/v1/me/communities").json()}
    assert set(memberships) == {home_id, office_id}
    assert memberships[home_id]["address_label"] == "B-1001"
    assert memberships[office_id]["address_label"] == "Office reception"
    assert memberships[home_id]["zone_id"] == str(market["zone"].id)
    assert memberships[office_id]["zone_id"] == str(market["other_zone"].id)
    assert (
        client.patch(
            f"/api/v1/me/memberships/{office.json()['id']}", json={"address_label": "Office lobby"}
        ).status_code
        == 200
    )
    memberships = {m["community_id"]: m for m in client.get("/api/v1/me/communities").json()}
    assert memberships[home_id]["address_label"] == "B-1001"
    assert memberships[office_id]["address_label"] == "Office lobby"
    assert client.get(f"/api/v1/communities/{home_id}/menu").status_code == 200
    assert client.get(f"/api/v1/communities/{office_id}/menu").status_code == 200
    assert (
        admin_client.post(f"/api/v1/memberships/{office.json()['id']}/suspend").status_code == 200
    )
    assert client.get(f"/api/v1/communities/{office_id}/menu").status_code == 403
    assert client.get(f"/api/v1/communities/{home_id}/menu").status_code == 200
