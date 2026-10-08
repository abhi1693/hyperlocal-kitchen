"""Catalog invariants, follows, discovery filters and administrative route coverage."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from kitchen_core import admin_food, admin_people, catalog, pickup_points
from kitchen_core.admin_food_schemas import KitchenMemberUpdate
from kitchen_core.admin_people_schemas import MembershipUpdate
from kitchen_core.catalog_schemas import (
    CommunityCreate,
    CommunityUpdate,
    CommunityZoneCreate,
    DishCreate,
    DishUpdate,
    KitchenApprove,
    KitchenCreate,
    KitchenUpdate,
    ListingUpdate,
    MembershipJoin,
    PickupPointUpdate,
)
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Community,
    Kitchen,
    KitchenMember,
    Membership,
    MenuListing,
    PickupPoint,
)
from kitchen_core.order_schemas import OrderCreate
from sqlalchemy import select
from test_admin_food import admin_publish
from test_admin_food import food_market as food_market
from test_catalog import as_user, listing_payload, publish
from test_catalog import market as market


@pytest.mark.parametrize(
    "data",
    [
        {"date": "2026-10-09", "from": "2026-10-09"},
        {"to": "2026-10-09"},
        {"from": "2026-10-09", "to": "2026-10-08"},
        {"from": "2026-10-09", "to": "2026-12-09"},
    ],
)
def test_resident_menu_rejects_invalid_date_ranges(client, market, data):
    as_user(client, market["customer"])
    response = client.get(f"/api/v1/communities/{market['community'].id}/menu", params=data)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "invalid_date_range"


def test_resident_discovery_owner_menu_and_dish_archive(client, market):
    as_user(client, market["owner"])
    food = publish(client, market)
    community_id, kitchen_id = market["community"].id, market["kitchen"].id
    assert client.get("/api/v1/communities", params={"query": "Oak"}).status_code == 200
    assert client.get(f"/api/v1/communities/{community_id}").json()["id"] == str(community_id)
    assert client.get(f"/api/v1/communities/{community_id}/zones").json()[0]["id"] == str(
        market["zone"].id
    )
    response = client.get(f"/api/v1/kitchens/{kitchen_id}/dishes")
    assert response.status_code == 200 and response.json()[0]["id"] == str(market["dish"].id)
    response = client.get(
        f"/api/v1/kitchens/{kitchen_id}/menu-listings", params={"date": food["service_date"]}
    )
    assert response.json()["total"] == 1
    assert client.delete(f"/api/v1/dishes/{market['dish'].id}").status_code == 200
    assert client.get(f"/api/v1/kitchens/{kitchen_id}/dishes").json() == []


def test_follow_preferences_are_idempotent_private_and_filter_unavailable_kitchens(
    client, session, market
):
    as_user(client, market["customer"])
    path = f"/api/v1/kitchens/{market['kitchen'].id}/follow"
    first = client.post(path).json()
    assert first["notify_new_menu"] is False
    changed = client.post(path, json={"notify_new_menu": True}).json()
    assert changed["notify_new_menu"] is True
    assert changed["followed_at"] == first["followed_at"]
    assert client.post(path, json={}).json()["notify_new_menu"] is True
    assert client.post(path).json()["notify_new_menu"] is True
    page = client.get("/api/v1/me/followed-kitchens").json()
    assert page["total"] == 1 and page["items"][0]["kitchen"]["id"] == str(market["kitchen"].id)
    assert client.get("/api/v1/me/followed-kitchens", params={"offset": 1}).json()["items"] == []
    as_user(client, market["owner"])
    assert client.get("/api/v1/me/followed-kitchens").json()["total"] == 0
    as_user(client, market["customer"])
    market["kitchen"].status = "suspended"
    session.commit()
    assert client.get("/api/v1/me/followed-kitchens").json()["total"] == 0
    assert client.post(path).status_code == 404
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 204


@pytest.mark.parametrize("field", ["name", "city", "type"])
def test_community_required_fields_cannot_be_cleared(session, market, field):
    with pytest.raises(DomainError) as error:
        catalog.update_community(session, market["community"].id, CommunityUpdate(**{field: None}))
    assert error.value.code == "required_field"


def test_duplicate_community_zones_and_zone_names_rejected(session, market):
    with pytest.raises(DomainError) as error:
        catalog.create_community(
            session,
            CommunityCreate(
                name="New",
                city="Pune",
                zones=[CommunityZoneCreate(name="A"), CommunityZoneCreate(name="a")],
            ),
        )
    assert error.value.code == "duplicate_zone"
    with pytest.raises(DomainError) as error:
        catalog.add_zone(
            session, market["community"].id, CommunityZoneCreate(name=market["zone"].name.lower())
        )
    assert error.value.code == "duplicate_zone"


def test_conflicting_active_join_fails(session, market):
    user = market["customer"]
    member = session.scalar(select(Membership).where(Membership.user_id == user.id))
    with pytest.raises(DomainError) as error:
        catalog.join_community(
            session, user, member.community_id, MembershipJoin(address_label="Another")
        )
    assert error.value.code == "membership_exists"


def test_core_admin_filters_and_missing_records(session, market):
    community, kitchen = market["community"], market["kitchen"]
    assert catalog.list_communities(session, community.name, 10, 0, admin=True).total == 1
    assert catalog.list_memberships(session, community.id, "active", 10, 0).total == 2
    assert catalog.list_memberships(session, None, None, 10, 0).total == 3
    assert catalog.admin_kitchens(session, community.id, "approved", 10, 0).total == 1
    assert catalog.admin_kitchens(session, None, None, 10, 0).total == 1
    assert (
        catalog.list_kitchens(
            session, market["customer"].id, community.id, kitchen.name, 10, 0
        ).total
        == 1
    )
    for function, args in [
        (catalog._get, (Kitchen, uuid4())),
        (catalog._require_kitchen_mutation, (None, kitchen.id)),
        (catalog.set_membership_status, (uuid4(), "active")),
        (catalog.approve_kitchen, (uuid4(), KitchenApprove(fssai_number="12345678901234"))),
        (catalog.suspend_kitchen, (uuid4(),)),
        (
            admin_food.member_view,
            (KitchenMember(kitchen_id=kitchen.id, user_id=uuid4(), role="manager"),),
        ),
        (admin_people._locked_membership, (uuid4(),)),
    ]:
        with pytest.raises(DomainError):
            function(session, *args)


@pytest.mark.parametrize(
    "field", ["name", "pickup_enabled", "delivery_enabled", "delivery_fee_paise"]
)
def test_kitchen_required_fields_cannot_be_cleared(session, market, field):
    with pytest.raises(DomainError) as error:
        catalog.update_kitchen(
            session, market["owner"].id, market["kitchen"].id, KitchenUpdate(**{field: None})
        )
    assert error.value.code == "required_field"


def test_kitchen_fulfillment_and_reapproval_invariants(session, market):
    kitchen = market["kitchen"]
    with pytest.raises(DomainError) as error:
        catalog.update_kitchen(
            session,
            market["owner"].id,
            kitchen.id,
            KitchenUpdate(pickup_enabled=False, delivery_enabled=False),
        )
    assert error.value.code == "fulfillment_required"
    result = catalog.update_kitchen(
        session, market["owner"].id, kitchen.id, KitchenUpdate(fssai_number="98765432109876")
    )
    assert result.status == "pending"
    session.delete(session.get(KitchenMember, (kitchen.id, market["owner"].id)))
    session.flush()
    with pytest.raises(DomainError) as error:
        catalog.approve_kitchen(session, kitchen.id, KitchenApprove(fssai_number="12345678901234"))
    assert error.value.code == "active_owner_required"


def test_inactive_membership_cannot_be_activated(session, market):
    user = market["customer"]
    user.is_active = False
    session.flush()
    member = session.scalar(select(Membership).where(Membership.user_id == user.id))
    with pytest.raises(DomainError) as error:
        catalog.set_membership_status(session, member.id, "active")
    assert error.value.code == "user_inactive"


def test_manager_cannot_create_second_kitchen_in_same_community(session, market):
    session.add(
        KitchenMember(
            kitchen_id=market["kitchen"].id, user_id=market["customer"].id, role="manager"
        )
    )
    session.flush()
    with pytest.raises(DomainError) as error:
        catalog.create_kitchen(
            session,
            market["customer"],
            KitchenCreate(community_id=market["community"].id, name="Another"),
        )
    assert error.value.code == "kitchen_exists"


def test_archived_dish_update_and_required_name(session, market):
    dish = market["dish"]
    with pytest.raises(DomainError) as error:
        catalog.update_dish(session, market["owner"].id, dish.id, DishUpdate(name=None))
    assert error.value.code == "required_field"
    dish.is_active = False
    session.flush()
    with pytest.raises(DomainError) as error:
        catalog.update_dish(session, market["owner"].id, dish.id, DishUpdate(name="Rename"))
    assert error.value.code == "dish_archived"
    assert (
        catalog.update_dish(session, None, dish.id, DishUpdate(name="Renamed"), admin=True).name
        == "Renamed"
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"available_from": None}, "timezone_required"),
        ({"available_from": datetime(2026, 10, 10)}, "timezone_required"),
        ({"available_until": datetime(2026, 10, 9, tzinfo=UTC)}, "invalid_ready_window"),
        ({"available_until": datetime(2026, 10, 12, tzinfo=UTC)}, "invalid_ready_window"),
        ({"order_cutoff": datetime(2026, 10, 11, tzinfo=UTC)}, "invalid_cutoff"),
        ({"service_date": date(2026, 10, 11)}, "service_date_mismatch"),
        ({"pickup_enabled": False, "delivery_enabled": False}, "fulfillment_required"),
    ],
)
def test_listing_time_and_fulfillment_validation(changes, code):
    values = {
        "available_from": datetime(2026, 10, 10, 8, tzinfo=UTC),
        "available_until": datetime(2026, 10, 10, 10, tzinfo=UTC),
        "order_cutoff": datetime(2026, 10, 10, 7, tzinfo=UTC),
        "service_date": date(2026, 10, 10),
        "pickup_enabled": True,
        "delivery_enabled": False,
    }
    kitchen = Kitchen(pickup_enabled=True, delivery_enabled=False, status="approved")
    with pytest.raises(DomainError) as error:
        catalog._validate_listing(kitchen, values | changes, publishing=False)
    assert error.value.code == code


@pytest.mark.parametrize("change", [{"pickup_enabled": False}, {"delivery_enabled": False}])
def test_listing_rejects_disabled_kitchen_fulfillment(change):
    now = datetime.now(UTC) + timedelta(days=1)
    kitchen = Kitchen(pickup_enabled=True, delivery_enabled=True, status="approved", **{})
    for field, value in change.items():
        setattr(kitchen, field, value)
    values = {
        "available_from": now,
        "available_until": now + timedelta(hours=1),
        "order_cutoff": now,
        "service_date": (now + timedelta(hours=5, minutes=30)).date(),
        "pickup_enabled": True,
        "delivery_enabled": True,
    }
    with pytest.raises(DomainError) as error:
        catalog._validate_listing(kitchen, values, publishing=False)
    assert error.value.code == "fulfillment_unavailable"


@pytest.mark.parametrize(
    "kind", ["missing", "null_points", "null_price", "anonymous_cancel", "cancelled"]
)
def test_listing_update_rejects_invalid_mutations(client, session, market, kind):
    food = publish(client, market)
    listing_id = market["kitchen"].id if kind == "missing" else food["id"]
    from uuid import UUID

    listing_id = UUID(str(listing_id))
    changes = {
        "null_points": {"pickup_point_ids": None},
        "null_price": {"price_paise": None},
        "anonymous_cancel": {"status": "cancelled"},
        "cancelled": {"status": "published"},
    }.get(kind, {})
    if kind == "cancelled":
        catalog.cancel_listing(session, market["owner"].id, listing_id)
    with pytest.raises(DomainError):
        catalog.update_listing(
            session,
            None if kind == "anonymous_cancel" else market["owner"].id,
            listing_id,
            ListingUpdate(**changes),
        )


def test_menu_visibility_and_owned_listing_requirements(client, session, market):
    food = publish(client, market)
    service_date = date.fromisoformat(food["service_date"])
    with pytest.raises(DomainError) as error:
        catalog.list_listings(
            session,
            market["owner"].id,
            market["community"].id,
            service_date,
            service_date,
            10,
            0,
            owned=True,
        )
    assert error.value.code == "kitchen_required"
    other_kitchen = Kitchen(community_id=market["other"].id, name="Other", status="approved")
    session.add(other_kitchen)
    session.flush()
    with pytest.raises(DomainError):
        catalog.list_listings(
            session,
            market["owner"].id,
            market["community"].id,
            service_date,
            service_date,
            10,
            0,
            kitchen_id=other_kitchen.id,
        )
    from uuid import UUID

    listing = session.get(MenuListing, UUID(food["id"]))
    listing.status = "draft"
    session.flush()
    with pytest.raises(DomainError):
        catalog.get_listing(session, market["customer"].id, listing.id)


@pytest.mark.parametrize("field", ["name", "address_label", "active"])
def test_pickup_point_required_fields_cannot_be_cleared(session, market, field):
    point = session.scalar(
        select(PickupPoint).where(PickupPoint.kitchen_id == market["kitchen"].id)
    )
    with pytest.raises(DomainError) as error:
        pickup_points.update_point(session, point.id, PickupPointUpdate(**{field: None}))
    assert error.value.code == "required_field"


def test_pickup_point_cannot_be_updated_through_another_kitchen(session, market):
    point = session.scalar(
        select(PickupPoint).where(PickupPoint.kitchen_id == market["kitchen"].id)
    )
    with pytest.raises(DomainError) as error:
        pickup_points.update_point(
            session, point.id, PickupPointUpdate(name="Changed"), kitchen_id=uuid4()
        )
    assert error.value.code == "not_found"


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_admin_member_operations_require_existing_member(session, market, operation):
    with pytest.raises(DomainError) as error:
        if operation == "update":
            admin_food.update_member(
                session,
                market["kitchen"].id,
                market["customer"].id,
                KitchenMemberUpdate(role="owner"),
            )
        else:
            admin_food.delete_member(session, market["kitchen"].id, market["customer"].id)
    assert error.value.code == "not_found"


def test_empty_request_validators_and_nullable_photos():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MembershipUpdate()
    with pytest.raises(ValidationError):
        KitchenCreate(
            community_id=uuid4(), name="Kitchen", pickup_enabled=False, delivery_enabled=False
        )
    with pytest.raises(ValidationError):
        OrderCreate(
            items=[{"menu_listing_id": uuid4(), "quantity": 1}],
            delivery_address={"address_label": "Home"},
        )
    assert DishCreate(name="Food", image_url=None).image_url is None


def test_admin_filtered_resource_lists_and_food_routes(admin_client, session, food_market):
    market = food_market
    food = admin_publish(admin_client, market)
    kitchen_id, community_id = market["kitchen"].id, market["community"].id
    paths = [
        ("/communities", {"q": market["community"].name, "status": "active"}),
        ("/communities", {}),
        ("/zones", {}),
        (f"/communities/{community_id}/zones", {"q": market["zone"].name}),
        ("/memberships", {"status": "active", "q": "owner"}),
        ("/users", {"q": "owner"}),
        ("/kitchens", {"q": market["kitchen"].name, "status": "approved"}),
        ("/dishes", {"community_id": str(community_id), "q": market["dish"].name}),
        (f"/kitchens/{kitchen_id}/dishes", {"is_active": True}),
        (f"/dishes/{market['dish'].id}", {}),
        (
            "/menu-listings",
            {
                "community_id": str(community_id),
                "dish_id": str(market["dish"].id),
                "service_date": food["service_date"],
                "date_from": food["service_date"],
                "date_until": food["service_date"],
                "q": market["dish"].name,
                "status": "published",
            },
        ),
        (f"/kitchens/{kitchen_id}/menu-listings", {}),
    ]
    for path, params in paths:
        response = admin_client.get("/api/v1" + path, params=params)
        assert response.status_code == 200, response.text
    response = admin_client.get(
        "/api/v1/menu-listings", params={"date_from": "2026-10-10", "date_until": "2026-10-09"}
    )
    assert response.status_code == 422
    response = admin_client.get("/api/v1/menu-listings", params={"status": "sold_out"})
    assert response.json()["total"] == 0
    assert (
        admin_client.post(
            f"/api/v1/kitchens/{kitchen_id}/pause", json={"reason": "Today"}
        ).status_code
        == 200
    )
    assert admin_client.post(f"/api/v1/kitchens/{kitchen_id}/resume").status_code == 200
    body = listing_payload({"dish": market["dish"]}, days=2)
    response = admin_client.post(
        "/api/v1/menu-listings", json={"kitchen_id": str(kitchen_id), **body}
    )
    assert response.status_code == 201, response.text


def test_admin_filters_cover_status_and_member_lists(admin_client, food_market):
    market = food_market
    response = admin_client.get("/api/v1/users", params={"is_active": True})
    assert response.status_code == 200 and all(row["is_active"] for row in response.json()["items"])
    response = admin_client.get(
        "/api/v1/memberships", params={"user_id": str(market["owner"].id), "status": "active"}
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    response = admin_client.get(f"/api/v1/kitchens/{market['kitchen'].id}/members")
    assert response.status_code == 200 and response.json()["total"] == 1


def test_addressless_kitchen_creation_omits_default_pickup_point(session, market):
    result = catalog.create_kitchen(
        session,
        market["customer"],
        KitchenCreate(
            community_id=market["community"].id, name="No address", address_label=None, zone_id=None
        ),
    )
    assert result.address_label is None
    assert (
        list(session.scalars(select(PickupPoint).where(PickupPoint.kitchen_id == result.id))) == []
    )
    assert catalog.list_communities(session, None, 10, 0).total == 2


def test_valid_photo_urls_are_normalized():
    assert (
        DishCreate(name="Food", image_url="https://images.example.test").image_url
        == "https://images.example.test/"
    )


def test_listing_cutoff_must_be_future_when_publishing():
    now = datetime.now(UTC)
    values = {
        "available_from": now + timedelta(hours=1),
        "available_until": now + timedelta(hours=2),
        "order_cutoff": now - timedelta(seconds=1),
        "service_date": (now + timedelta(hours=6, minutes=30)).date(),
        "pickup_enabled": True,
        "delivery_enabled": False,
    }
    with pytest.raises(DomainError) as error:
        catalog._validate_listing(
            Kitchen(status="approved", pickup_enabled=True), values, publishing=True
        )
    assert error.value.code == "cutoff_passed"


@pytest.mark.parametrize(
    "duplicate,enabled,code",
    [(True, True, "duplicate_pickup_point"), (False, False, "pickup_disabled")],
)
def test_listing_pickup_choices_must_be_unique_and_enabled(
    session, market, duplicate, enabled, code
):
    identifier = uuid4()
    with pytest.raises(DomainError) as error:
        catalog.validate_listing_points(
            session,
            market["kitchen"],
            [identifier, identifier] if duplicate else [identifier],
            enabled,
        )
    assert error.value.code == code


def test_zone_and_pickup_point_validation_fail_before_writes(session, market):
    from kitchen_core.admin_people_schemas import CommunityZoneUpdate

    with pytest.raises(DomainError) as error:
        admin_people.update_zone(session, market["zone"].id, CommunityZoneUpdate(name=None))
    assert error.value.code == "required_field"
    point = session.scalar(
        select(PickupPoint).where(PickupPoint.kitchen_id == market["kitchen"].id)
    )
    assert (
        pickup_points.update_point(session, point.id, PickupPointUpdate(zone_id=None)).zone_id
        is None
    )
    with pytest.raises(DomainError):
        admin_people.locked(session, Community, uuid4())
    with pytest.raises(DomainError):
        admin_food._lock(session, Kitchen, uuid4())


@pytest.mark.parametrize("reference", ["listing", "order"])
def test_kitchen_with_referenced_pickup_point_cannot_be_deleted(client, session, market, reference):
    from uuid import UUID

    from kitchen_core import orders
    from kitchen_core.models import ListingPickupPoint
    from sqlalchemy import delete

    food = publish(client, market)
    unused = Kitchen(community_id=market["community"].id, name="Collection host", status="approved")
    session.add(unused)
    session.flush()
    point = PickupPoint(
        community_id=unused.community_id,
        kitchen_id=unused.id,
        name="Shared collection",
        address_label="Gate",
    )
    session.add(point)
    session.flush()
    link = ListingPickupPoint(
        listing_id=UUID(food["id"]),
        kitchen_id=market["kitchen"].id,
        community_id=unused.community_id,
        pickup_point_id=point.id,
    )
    session.add(link)
    session.flush()
    if reference == "order":
        orders.create_order(
            session,
            market["customer"],
            OrderCreate(
                items=[{"menu_listing_id": food["id"], "quantity": 1}], pickup_point_id=point.id
            ),
            "shared-point",
        )
        session.execute(
            delete(ListingPickupPoint).where(ListingPickupPoint.pickup_point_id == point.id)
        )
        session.flush()
    with pytest.raises(DomainError) as error:
        admin_food.delete_kitchen(session, unused.id)
    assert error.value.code == "record_in_use"
    assert session.get(Kitchen, unused.id) is not None
