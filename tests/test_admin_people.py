"""Admin operations exercise real relationships, address guards and history."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import UUID

import pytest
from kitchen_core.admin_people import set_user_active
from kitchen_core.models import (
    Community,
    CommunityZone,
    Device,
    Kitchen,
    KitchenMember,
    Membership,
    Order,
    User,
    utcnow,
)
from sqlalchemy import event, select, text


def success(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def people(session):
    communities = [
        Community(
            name=name, address=name + " Road", city="Pune", postal_code="411001", status="active"
        )
        for name in ("Garden", "Park")
    ]
    owner, resident, newcomer = [
        User(
            oidc_subject="people-" + name.lower(),
            oidc_issuer="https://identity.example.test",
            phone=f"+91900000000{index}",
            name=name,
        )
        for index, name in enumerate(("Owner", "Resident", "Newcomer"), start=1)
    ]
    session.add_all([*communities, owner, resident, newcomer])
    session.flush()
    garden, park = communities
    zone, extra, other = [
        CommunityZone(community_id=community.id, name=name)
        for community, name in (
            (garden, "Zone A"),
            (garden, "Zone B"),
            (park, "Zone Z"),
        )
    ]
    session.add_all([zone, extra, other])
    session.flush()
    owner_membership, resident_membership = [
        Membership(
            community_id=garden.id,
            user_id=user.id,
            zone_id=zone.id,
            address_label=address_label,
            status="active",
        )
        for user, address_label in ((owner, "101"), (resident, "102"))
    ]
    kitchen = Kitchen(
        community_id=garden.id,
        zone_id=zone.id,
        address_label="101",
        name="Home Kitchen",
        status="approved",
    )
    session.add_all([owner_membership, resident_membership, kitchen])
    session.flush()
    session.add(KitchenMember(kitchen_id=kitchen.id, user_id=owner.id, role="owner"))
    session.commit()
    return locals()


def historical_order(session, people, customer):
    ready = utcnow() - timedelta(days=1)
    order = Order(
        community_id=people["garden"].id,
        kitchen_id=people["kitchen"].id,
        customer_id=customer.id,
        status="completed",
        fulfillment_type="pickup",
        pickup_address={"zone": "Zone A", "address_label": "101"},
        delivery_address={"zone": "Zone A", "address_label": "102"},
        available_from=ready,
        available_until=ready + timedelta(hours=1),
        expires_at=ready - timedelta(hours=1),
        subtotal_paise=15000,
        total_paise=15000,
    )
    session.add(order)
    session.commit()
    return order


def test_users_are_searchable_bounded_and_provider_identity_is_immutable(
    admin_client, session, people
):
    literal = User(
        oidc_subject="literal-percent",
        oidc_issuer="https://identity.example.test",
        name="Percent %",
    )
    session.add(literal)
    session.commit()
    page = success(admin_client.get("/api/v1/users", params={"q": "%", "sort": "name"}))
    assert page["total"] == 1
    assert page["items"][0]["id"] == str(literal.id)
    assert "oidc_subject" not in page["items"][0]
    assert "oidc_issuer" not in page["items"][0]
    user_path = f"/api/v1/users/{people['resident'].id}"
    changed = success(admin_client.patch(user_path, json={"name": "Updated resident"}))
    assert changed["name"] == "Updated resident"
    assert success(admin_client.get(user_path))["phone"] == people["resident"].phone
    for field, value in (
        ("oidc_subject", "forged-subject"),
        ("oidc_issuer", "https://forged.example.test"),
    ):
        assert admin_client.patch(user_path, json={field: value}).status_code == 422
    assert admin_client.post("/api/v1/users", json={"name": "Fake identity"}).status_code == 405
    assert admin_client.delete(user_path).status_code == 409
    for params in ({"limit": 101}, {"offset": 10001}, {"sort": "oidc_subject"}):
        assert admin_client.get("/api/v1/users", params=params).status_code == 422


def test_contact_phone_updates_preserve_identity_and_other_profile_fields(admin_client, people):
    path = f"/api/v1/users/{people['newcomer'].id}"
    user = success(admin_client.patch(path, json={"phone": people["resident"].phone}))
    assert user["phone"] == people["resident"].phone
    assert user["name"] == "Newcomer"
    assert admin_client.patch(path, json={"phone": "bad phone"}).status_code == 422
    assert success(admin_client.patch(path, json={"phone": None}))["phone"] is None
    assert admin_client.patch(path, json={}).status_code == 422


def test_user_delete_removes_only_unused_profiles(admin_client, session, people):
    unused = f"/api/v1/users/{people['newcomer'].id}"
    assert admin_client.delete(unused).status_code == 204
    assert admin_client.get(unused).status_code == 404
    assert admin_client.delete(unused).status_code == 404
    assert admin_client.delete(f"/api/v1/users/{people['owner'].id}").status_code == 409
    me = User(oidc_subject="test-admin", oidc_issuer="https://identity.example.test", name="Admin")
    session.add(me)
    session.commit()
    assert admin_client.delete(f"/api/v1/users/{me.id}").status_code == 409


def test_user_delete_preserves_order_history_without_membership(admin_client, session, people):
    user = people["newcomer"]
    historical_order(session, people, user)
    assert admin_client.delete(f"/api/v1/users/{user.id}").status_code == 409
    assert success(admin_client.get(f"/api/v1/users/{user.id}"))["name"] == "Newcomer"


def test_account_deactivation_suspends_memberships_kitchen_and_devices_without_losing_history(
    admin_client, session, people
):
    owner = people["owner"]
    order = historical_order(session, people, owner)
    device = Device(
        user_id=owner.id,
        session_key="kitchen:user:session:" + "a" * 64,
        push_token="ExponentPushToken[people-device]",
        platform="ios",
    )
    session.add(device)
    session.add(
        KitchenMember(
            kitchen_id=people["kitchen"].id,
            user_id=people["resident"].id,
            role="manager",
        )
    )
    session.commit()
    response = success(admin_client.post(f"/api/v1/users/{owner.id}/deactivate"))
    assert response["is_active"] is False
    session.expire_all()
    assert session.get(Membership, people["owner_membership"].id).status == "suspended"
    assert session.get(Kitchen, people["kitchen"].id).status == "suspended"
    assert session.get(Device, device.id).is_active is False
    assert session.get(Order, order.id).status == "completed"
    assert (
        admin_client.post(
            f"/api/v1/memberships/{people['owner_membership'].id}/activate"
        ).status_code
        == 409
    )
    assert success(admin_client.post(f"/api/v1/users/{owner.id}/activate"))["is_active"] is True
    session.expire_all()
    assert session.get(Membership, people["owner_membership"].id).status == "suspended"
    assert session.get(Kitchen, people["kitchen"].id).status == "suspended"


def test_shared_kitchens_in_multiple_communities_can_deactivate_both_users_concurrently(
    session, session_factory, people
):
    owner, resident = people["owner"], people["resident"]
    # The users visit the two communities in opposite membership UUID orders.
    people["owner_membership"].id = UUID(int=101)
    people["resident_membership"].id = UUID(int=104)
    park = people["park"]
    park_kitchen = Kitchen(
        community_id=park.id,
        zone_id=people["other"].id,
        address_label="201",
        name="Shared Park Kitchen",
        status="approved",
    )
    session.add_all(
        [
            park_kitchen,
            Membership(
                id=UUID(int=103),
                user_id=owner.id,
                community_id=park.id,
                zone_id=people["other"].id,
                address_label="201",
                status="active",
            ),
            Membership(
                id=UUID(int=102),
                user_id=resident.id,
                community_id=park.id,
                zone_id=people["other"].id,
                address_label="202",
                status="active",
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            KitchenMember(kitchen_id=people["kitchen"].id, user_id=resident.id, role="manager"),
            KitchenMember(kitchen_id=park_kitchen.id, user_id=owner.id, role="manager"),
            KitchenMember(kitchen_id=park_kitchen.id, user_id=resident.id, role="owner"),
        ]
    )
    session.commit()
    user_ids = [owner.id, resident.id]
    memberships_locked = Barrier(2)
    first_kitchen_locked = [Event(), Event()]

    def deactivate(index):
        with session_factory.begin() as transaction:
            transaction.execute(text("SET LOCAL lock_timeout = '2s'"))
            transaction.execute(text("SET LOCAL statement_timeout = '5s'"))
            connection = transaction.connection()
            synchronized_memberships = False
            synchronized_kitchens = False

            def after_query(conn, cursor, statement, parameters, context, executemany):
                nonlocal synchronized_memberships, synchronized_kitchens
                if not statement.lstrip().startswith("SELECT"):
                    return
                if (
                    not synchronized_memberships
                    and "FROM community_memberships" in statement
                    and "FOR UPDATE" in statement
                ):
                    synchronized_memberships = True
                    memberships_locked.wait(timeout=5)
                if (
                    not synchronized_kitchens
                    and "FROM kitchens" in statement
                    and "FOR NO KEY UPDATE" in statement
                ):
                    synchronized_kitchens = True
                    first_kitchen_locked[index].set()
                    # Give independent first locks a chance to overlap. A correct
                    # shared lock order serializes here, so the wait is bounded.
                    first_kitchen_locked[1 - index].wait(timeout=0.25)

            event.listen(connection, "after_cursor_execute", after_query)
            try:
                result = set_user_active(transaction, user_ids[index], False)
                assert result.is_active is False
            finally:
                event.remove(connection, "after_cursor_execute", after_query)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(deactivate, index) for index in range(2)]
        for future in futures:
            future.result(timeout=10)
    session.expire_all()
    assert all(session.get(User, identifier).is_active is False for identifier in user_ids)
    assert set(
        session.scalars(select(Membership.status).where(Membership.user_id.in_(user_ids)))
    ) == {"suspended"}
    assert session.get(Kitchen, people["kitchen"].id).status == "suspended"
    assert session.get(Kitchen, park_kitchen.id).status == "suspended"


def test_membership_creation_filters_and_address_changes_preserve_order_snapshots(
    admin_client, session, people
):
    data = {
        "user_id": str(people["newcomer"].id),
        "community_id": str(people["garden"].id),
        "zone_id": str(people["zone"].id),
        "address_label": "103",
    }
    assert (
        admin_client.post(
            "/api/v1/memberships", json={**data, "zone_id": str(people["other"].id)}
        ).status_code
        == 422
    )
    membership = success(admin_client.post("/api/v1/memberships", json=data), 201)
    assert membership["status"] == "active"
    assert admin_client.post("/api/v1/memberships", json=data).status_code == 409
    path = f"/api/v1/memberships/{membership['id']}"
    assert admin_client.post(path + "/approve").status_code == 404
    assert (
        admin_client.post("/api/v1/memberships", json=data | {"status": "active"}).status_code
        == 422
    )
    assert admin_client.get("/api/v1/memberships", params={"status": "pending"}).status_code == 422
    page = success(
        admin_client.get(
            "/api/v1/memberships",
            params={
                "user_id": data["user_id"],
                "community_id": data["community_id"],
                "status": "active",
            },
        )
    )
    assert page["total"] == 1 and page["items"][0]["id"] == membership["id"]
    assert success(admin_client.get(path))["address_label"] == "103"
    assert admin_client.patch(path, json={"zone_id": str(people["other"].id)}).status_code == 422
    assert (
        success(
            admin_client.patch(
                path, json={"zone_id": str(people["extra"].id), "address_label": "204"}
            )
        )["address_label"]
        == "204"
    )
    assert success(admin_client.post(path + "/suspend"))["status"] == "suspended"
    assert success(admin_client.post(path + "/activate"))["status"] == "active"
    assert success(admin_client.post(path + "/suspend"))["status"] == "suspended"
    assert admin_client.delete(path).status_code == 204

    order = historical_order(session, people, people["resident"])
    resident_path = f"/api/v1/memberships/{people['resident_membership'].id}"
    assert (
        success(admin_client.patch(resident_path, json={"address_label": "New address_label"}))[
            "address_label"
        ]
        == "New address_label"
    )
    assert admin_client.delete(resident_path).status_code == 409
    session.expire_all()
    assert session.get(Order, order.id).delivery_address["address_label"] == "102"


def test_kitchen_owner_home_can_change_independently_but_membership_is_retained(
    admin_client, people
):
    path = f"/api/v1/memberships/{people['owner_membership'].id}"
    assert admin_client.patch(path, json={"address_label": "Moved"}).status_code == 200
    assert (
        success(admin_client.get(f"/api/v1/kitchens/{people['kitchen'].id}"))["address_label"]
        == "101"
    )
    assert admin_client.delete(path).status_code == 409
    # Idempotent edits do not move a kitchen-managed address.
    assert (
        success(admin_client.patch(path, json={"address_label": "101"}))["address_label"] == "101"
    )


def test_inactive_accounts_and_paused_communities_reject_membership_creation(admin_client, people):
    data = {
        "user_id": str(people["newcomer"].id),
        "community_id": str(people["garden"].id),
        "zone_id": str(people["zone"].id),
        "address_label": "103",
    }
    success(admin_client.post(f"/api/v1/users/{people['newcomer'].id}/deactivate"))
    assert admin_client.post("/api/v1/memberships", json=data).status_code == 409
    success(admin_client.post(f"/api/v1/users/{people['newcomer'].id}/activate"))
    success(admin_client.post(f"/api/v1/communities/{people['garden'].id}/pause"))
    assert admin_client.post("/api/v1/memberships", json=data).status_code == 409


def test_zone_update_delete_and_reference_guards(admin_client, people):
    garden = people["garden"]
    path = f"/api/v1/zones/{people['extra'].id}"
    page = success(
        admin_client.get(f"/api/v1/communities/{garden.id}/zones", params={"sort": "name"})
    )
    assert page["total"] == 2
    assert success(admin_client.get(path))["name"] == "Zone B"
    assert admin_client.patch(path, json={"name": "zone a"}).status_code == 409
    assert success(admin_client.patch(path, json={"name": "Zone C"}))["name"] == "Zone C"
    assert (
        admin_client.patch(path, json={"community_id": str(people["park"].id)}).status_code == 422
    )
    assert admin_client.delete(f"/api/v1/zones/{people['zone'].id}").status_code == 409
    assert admin_client.delete(path).status_code == 204
    assert admin_client.get(path).status_code == 404
    other_path = f"/api/v1/zones/{people['other'].id}"
    assert admin_client.delete(other_path).status_code == 204
    assert admin_client.post(f"/api/v1/communities/{people['park'].id}/activate").status_code == 200


def test_community_can_be_deleted_only_before_people_or_food_use_it(admin_client, session, people):
    data = {
        "name": "Unused community",
        "address": "Empty Road",
        "city": "Pune",
        "postal_code": "411001",
        "zones": [{"name": "Zone X"}],
    }
    community = success(admin_client.post("/api/v1/communities", json=data), 201)
    path = f"/api/v1/communities/{community['id']}"
    assert (
        success(admin_client.patch(path, json={"name": "Corrected community"}))["name"]
        == "Corrected community"
    )
    assert admin_client.delete(path).status_code == 204
    assert admin_client.get(path).status_code == 404
    assert admin_client.delete(f"/api/v1/communities/{people['garden'].id}").status_code == 409
    assert session.get(Community, people["garden"].id) is not None


def test_resident_joins_active_community_immediately_without_admin_approval(
    client, admin_client, people
):
    from kitchen_http.auth import require_user

    client.app.dependency_overrides[require_user] = lambda: people["newcomer"]
    community_id = people["garden"].id
    path = f"/api/v1/communities/{community_id}/join"
    address = {"zone_id": str(people["zone"].id), "address_label": "103"}
    joined = success(client.post(path, json=address), 201)
    assert joined["status"] == "active"
    assert success(client.get(f"/api/v1/communities/{community_id}/kitchens"))["total"] == 1
    # A suspended membership requires explicit administrative restoration.
    membership_path = f"/api/v1/memberships/{joined['id']}"
    assert success(admin_client.post(membership_path + "/suspend"))["status"] == "suspended"
    assert client.post(path, json=address).status_code == 403
    assert success(admin_client.post(membership_path + "/activate"))["status"] == "active"
    assert success(client.post(path, json=address), 201)["status"] == "active"
    assert (
        client.post(path, json=address | {"invitation_code": "no-longer-supported"}).status_code
        == 422
    )
    assert admin_client.get("/api/v1/invitations").status_code == 404
    assert (
        admin_client.post(
            f"/api/v1/communities/{community_id}/invitations", json={"phone": "+919000000004"}
        ).status_code
        == 404
    )
