"""Persisted association traversal and database-enforced tenant ownership."""

import subprocess
import sys
from datetime import timedelta

import pytest
from kitchen_core.models import (
    Community,
    CommunityZone,
    Device,
    Dish,
    Kitchen,
    KitchenMember,
    Membership,
    MenuListing,
    Notification,
    Order,
    OrderEvent,
    OrderIdempotency,
    OrderItem,
    User,
    utcnow,
)
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError


def make_listing(kitchen, dish, *, days=0):
    ready = utcnow() + timedelta(days=days, hours=2)
    return MenuListing(
        kitchen_id=kitchen.id,
        dish_id=dish.id,
        service_date=ready.date(),
        available_from=ready,
        available_until=ready + timedelta(hours=1),
        order_cutoff=ready - timedelta(minutes=30),
        price_paise=15000,
        quantity_total=10,
    )


def make_order(community, kitchen, customer):
    ready = utcnow() + timedelta(hours=2)
    return Order(
        community_id=community.id,
        kitchen_id=kitchen.id,
        customer_id=customer.id,
        fulfillment_type="pickup",
        pickup_address={"zone": "Zone A", "address_label": "A-101"},
        delivery_address={"zone": "Zone A", "address_label": "A-102"},
        available_from=ready,
        available_until=ready + timedelta(hours=1),
        expires_at=utcnow() + timedelta(minutes=15),
        subtotal_paise=30000,
        delivery_fee_paise=0,
        total_paise=30000,
    )


@pytest.fixture
def model_graph(session):
    communities = [
        Community(
            name=name,
            address=name + " Road",
            city="Pune",
            postal_code="411001",
            status="active",
        )
        for name in ("Garden", "Park")
    ]
    owner, manager, customer, unjoined = [
        User(oidc_subject=name.lower(), oidc_issuer="https://identity.example.test", name=name)
        for name in ("Owner", "Manager", "Customer", "Unjoined")
    ]
    session.add_all([*communities, owner, manager, customer, unjoined])
    session.flush()
    garden, park = communities
    zones = [CommunityZone(community_id=community.id, name="Zone A") for community in communities]
    session.add_all(zones)
    session.flush()
    garden_zone, park_zone = zones
    memberships = [
        Membership(
            community_id=community.id,
            user_id=user.id,
            zone_id=zone.id,
            address_label=f"A-{index + 101}",
            status="active",
        )
        for index, (community, zone, user) in enumerate(
            [
                (garden, garden_zone, owner),
                (garden, garden_zone, manager),
                (garden, garden_zone, customer),
                (park, park_zone, owner),
            ]
        )
    ]
    kitchens = [
        Kitchen(
            community_id=community.id,
            zone_id=zone.id,
            address_label="A-101",
            name=community.name + " Kitchen",
            status="approved",
        )
        for community, zone in zip(communities, zones, strict=True)
    ]
    session.add_all([*memberships, *kitchens])
    session.flush()
    kitchen, other_kitchen = kitchens
    kitchen_memberships = [
        KitchenMember(kitchen_id=kitchen.id, user_id=owner.id, role="owner"),
        KitchenMember(kitchen_id=kitchen.id, user_id=manager.id, role="manager"),
        KitchenMember(kitchen_id=other_kitchen.id, user_id=owner.id, role="owner"),
    ]
    dish = Dish(kitchen_id=kitchen.id, name="Rajma Chawal")
    session.add_all([*kitchen_memberships, dish])
    session.flush()
    listing = make_listing(kitchen, dish)
    tomorrow = make_listing(kitchen, dish, days=1)
    order = make_order(garden, kitchen, customer)
    device = Device(
        user_id=customer.id,
        session_key="kitchen:user:session:" + "b" * 64,
        push_token="ExpoPushToken[model-test]",
        platform="android",
    )
    session.add_all([listing, tomorrow, order, device])
    session.flush()
    item = OrderItem(
        order_id=order.id,
        menu_listing_id=listing.id,
        dish_name=dish.name,
        unit_price_paise=15000,
        quantity=2,
        total_paise=30000,
    )
    event = OrderEvent(order_id=order.id, actor_id=customer.id, status="pending")
    notification = Notification(
        order_id=order.id, user_id=customer.id, kind="order_pending", payload={"status": "pending"}
    )
    idempotency = OrderIdempotency(
        customer_id=customer.id, key="original-order", request_hash="c" * 64, order_id=order.id
    )
    session.add_all([item, event, notification, idempotency])
    session.commit()
    return dict(
        garden=garden,
        park=park,
        owner=owner,
        manager=manager,
        customer=customer,
        unjoined=unjoined,
        garden_zone=garden_zone,
        park_zone=park_zone,
        kitchen=kitchen,
        other_kitchen=other_kitchen,
        dish=dish,
        listing=listing,
        tomorrow=tomorrow,
        order=order,
        item=item,
        event=event,
        notification=notification,
        idempotency=idempotency,
        device=device,
    )


def test_mapper_configuration_is_warning_free_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings; from sqlalchemy.exc import SAWarning; "
                "warnings.simplefilter('error', SAWarning); "
                "import kitchen_core.models; from sqlalchemy.orm import configure_mappers; "
                "configure_mappers()"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_many_to_many_associations_preserve_role_and_resident_address(session, model_graph):
    graph = model_graph
    session.expire_all()
    owner, kitchen = graph["owner"], graph["kitchen"]
    assert {membership.community.name for membership in owner.memberships} == {"Garden", "Park"}
    assert {membership.zone.name for membership in owner.memberships} == {"Zone A"}
    assert {membership.address_label for membership in owner.memberships} == {"A-101", "A-104"}
    assert {membership.kitchen.name for membership in owner.kitchen_memberships} == {
        "Garden Kitchen",
        "Park Kitchen",
    }
    assert {(membership.user.name, membership.role) for membership in kitchen.memberships} == {
        ("Owner", "owner"),
        ("Manager", "manager"),
    }
    assert {membership.user.name for membership in graph["garden"].memberships} == {
        "Owner",
        "Manager",
        "Customer",
    }
    assert graph["garden_zone"].community is graph["garden"]
    assert kitchen.community is graph["garden"]
    assert kitchen.zone is graph["garden_zone"]
    assert graph["device"].user is graph["customer"]
    assert {community.name for community in owner.communities} == {"Garden", "Park"}
    assert {row.name for row in owner.kitchens} == {"Garden Kitchen", "Park Kitchen"}
    assert {user.name for user in graph["garden"].users} == {"Owner", "Manager", "Customer"}
    assert {user.name for user in kitchen.members} == {"Owner", "Manager"}


def test_view_only_shortcuts_cannot_grant_kitchen_membership(session, model_graph):
    manager = model_graph["manager"]
    manager.kitchens.append(model_graph["other_kitchen"])
    session.commit()
    session.expire_all()
    assert {kitchen.name for kitchen in manager.kitchens} == {"Garden Kitchen"}
    assert {(link.kitchen.name, link.role) for link in manager.kitchen_memberships} == {
        ("Garden Kitchen", "manager")
    }


def test_reusable_dish_listings_and_order_history_traverse_both_directions(session, model_graph):
    graph = model_graph
    session.expire_all()
    order, dish, listing = graph["order"], graph["dish"], graph["listing"]
    assert dish.kitchen is graph["kitchen"]
    assert {row.id for row in dish.listings} == {listing.id, graph["tomorrow"].id}
    assert listing.dish is dish and listing.kitchen is graph["kitchen"]
    assert order.customer is graph["customer"]
    assert order.community is graph["garden"] and order.kitchen is graph["kitchen"]
    assert order.items[0].listing is listing
    assert listing.order_items[0].order is order
    assert order.events[0].order is order and order.events[0].actor is graph["customer"]
    assert order.notifications[0].order is order
    assert order.notifications[0].user is graph["customer"]
    assert order.idempotency.order is order
    assert {row.id for row in graph["customer"].orders} == {order.id}
    assert {row.id for row in graph["kitchen"].orders} == {order.id}
    # Reusing a dish never mutates the historical item snapshot.
    dish.name = "Renamed dish"
    session.flush()
    assert order.items[0].dish_name == "Rajma Chawal"


@pytest.mark.parametrize(
    "invalid_link",
    ["membership_zone", "kitchen_zone", "listing_dish", "order_community", "idempotency_customer"],
)
def test_database_rejects_cross_boundary_foreign_keys(session, model_graph, invalid_link):
    graph = model_graph
    if invalid_link == "membership_zone":
        row = Membership(
            community_id=graph["garden"].id,
            zone_id=graph["park_zone"].id,
            user_id=graph["unjoined"].id,
            address_label="A-201",
            status="active",
        )
    elif invalid_link == "kitchen_zone":
        row = Kitchen(
            community_id=graph["garden"].id,
            zone_id=graph["park_zone"].id,
            name="Cross-boundary kitchen",
            address_label="A-201",
        )
    elif invalid_link == "listing_dish":
        row = make_listing(graph["other_kitchen"], graph["dish"])
    elif invalid_link == "order_community":
        row = make_order(graph["garden"], graph["other_kitchen"], graph["customer"])
    else:
        extra_order = make_order(graph["garden"], graph["kitchen"], graph["customer"])
        session.add(extra_order)
        session.flush()
        row = OrderIdempotency(
            customer_id=graph["manager"].id,
            order_id=extra_order.id,
            key="wrong-customer",
            request_hash="d" * 64,
        )
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.add(row)
        session.flush()
    assert (
        error.value.orig.sqlstate == "23503"
    )  # foreign_key_violation, not a duplicate or null error


@pytest.mark.parametrize("association", ["community_membership", "kitchen_membership"])
def test_association_membership_is_unique(session, model_graph, association):
    graph = model_graph
    if association == "community_membership":
        row = Membership(
            community_id=graph["garden"].id,
            zone_id=graph["garden_zone"].id,
            user_id=graph["owner"].id,
            address_label="A-999",
            status="active",
        )
    else:
        row = KitchenMember(
            kitchen_id=graph["kitchen"].id, user_id=graph["owner"].id, role="manager"
        )
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.add(row)
        session.flush()
    assert error.value.orig.sqlstate == "23505"


@pytest.mark.parametrize("reparent", ["zone_community", "dish_kitchen", "order_customer"])
def test_reparenting_cannot_invalidate_existing_foreign_keys(session, model_graph, reparent):
    graph = model_graph
    if reparent == "zone_community":
        statement = (
            update(CommunityZone)
            .where(CommunityZone.id == graph["garden_zone"].id)
            .values(community_id=graph["park"].id, name="Moved CommunityZone")
        )
    elif reparent == "dish_kitchen":
        statement = (
            update(Dish)
            .where(Dish.id == graph["dish"].id)
            .values(kitchen_id=graph["other_kitchen"].id)
        )
    else:
        statement = (
            update(Order)
            .where(Order.id == graph["order"].id)
            .values(customer_id=graph["manager"].id)
        )
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.execute(statement)
    assert error.value.orig.sqlstate == "23503"


def test_relationship_assignment_persists_association_details(session, model_graph):
    graph = model_graph
    membership = Membership(
        user=graph["unjoined"],
        community=graph["garden"],
        zone=graph["garden_zone"],
        address_label="A-501",
    )
    session.add(membership)
    session.flush()
    assert membership.user_id == graph["unjoined"].id
    assert membership.community_id == graph["garden"].id
    assert membership.zone_id == graph["garden_zone"].id
    session.expire_all()
    assert graph["unjoined"].memberships[0].address_label == "A-501"
    assert graph["unjoined"].memberships[0].status == "active"


def test_hard_delete_cannot_remove_customer_of_historical_order(session, model_graph):
    with pytest.raises(IntegrityError) as error, session.begin_nested():
        session.delete(model_graph["customer"])
        session.flush()
    assert error.value.orig.sqlstate == "23503"
