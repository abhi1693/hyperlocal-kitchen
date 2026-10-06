"""Admin operations exercise real relationships, address guards and history."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import UUID

import pytest
from kitchen_core.admin_people import set_user_active
from kitchen_core.models import (
    Device,
    Kitchen,
    KitchenMember,
    Membership,
    Order,
    Society,
    Tower,
    User,
    utcnow,
)
from sqlalchemy import event, select, text


def success(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def people(session):
    societies = [
        Society(
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
    session.add_all([*societies, owner, resident, newcomer])
    session.flush()
    garden, park = societies
    tower, extra, other = [
        Tower(society_id=society.id, name=name)
        for society, name in ((garden, "Tower A"), (garden, "Tower B"), (park, "Tower Z"))
    ]
    session.add_all([tower, extra, other])
    session.flush()
    owner_membership, resident_membership = [
        Membership(
            society_id=garden.id,
            user_id=user.id,
            tower_id=tower.id,
            flat=flat,
            status="active",
        )
        for user, flat in ((owner, "101"), (resident, "102"))
    ]
    kitchen = Kitchen(
        society_id=garden.id, tower_id=tower.id, flat="101", name="Home Kitchen", status="approved"
    )
    session.add_all([owner_membership, resident_membership, kitchen])
    session.flush()
    session.add(KitchenMember(kitchen_id=kitchen.id, user_id=owner.id, role="owner"))
    session.commit()
    return locals()


def historical_order(session, people, customer):
    ready = utcnow() - timedelta(days=1)
    order = Order(
        society_id=people["garden"].id,
        kitchen_id=people["kitchen"].id,
        customer_id=customer.id,
        status="completed",
        fulfillment_type="pickup",
        pickup_address={"tower": "Tower A", "flat": "101"},
        delivery_address={"tower": "Tower A", "flat": "102"},
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
        ("phone", "+919999999999"),
        ("oidc_subject", "forged-subject"),
        ("oidc_issuer", "https://forged.example.test"),
    ):
        assert admin_client.patch(user_path, json={field: value}).status_code == 422
    assert admin_client.post("/api/v1/users", json={"name": "Fake identity"}).status_code == 405
    assert admin_client.delete(user_path).status_code == 405
    for params in ({"limit": 101}, {"offset": 10001}, {"sort": "oidc_subject"}):
        assert admin_client.get("/api/v1/users", params=params).status_code == 422


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


def test_shared_kitchens_in_multiple_societies_can_deactivate_both_users_concurrently(
    session, session_factory, people
):
    owner, resident = people["owner"], people["resident"]
    # The users visit the two societies in opposite membership UUID orders.
    people["owner_membership"].id = UUID(int=101)
    people["resident_membership"].id = UUID(int=104)
    park = people["park"]
    park_kitchen = Kitchen(
        society_id=park.id,
        tower_id=people["other"].id,
        flat="201",
        name="Shared Park Kitchen",
        status="approved",
    )
    session.add_all(
        [
            park_kitchen,
            Membership(
                id=UUID(int=103),
                user_id=owner.id,
                society_id=park.id,
                tower_id=people["other"].id,
                flat="201",
                status="active",
            ),
            Membership(
                id=UUID(int=102),
                user_id=resident.id,
                society_id=park.id,
                tower_id=people["other"].id,
                flat="202",
                status="active",
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            KitchenMember(kitchen_id=people["kitchen"].id, user_id=resident.id, role="owner"),
            KitchenMember(kitchen_id=park_kitchen.id, user_id=owner.id, role="owner"),
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
                    and "FROM society_memberships" in statement
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
        "society_id": str(people["garden"].id),
        "tower_id": str(people["tower"].id),
        "flat": "103",
    }
    assert (
        admin_client.post(
            "/api/v1/memberships", json={**data, "tower_id": str(people["other"].id)}
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
                "society_id": data["society_id"],
                "status": "active",
            },
        )
    )
    assert page["total"] == 1 and page["items"][0]["id"] == membership["id"]
    assert success(admin_client.get(path))["flat"] == "103"
    assert admin_client.patch(path, json={"tower_id": str(people["other"].id)}).status_code == 422
    assert (
        success(
            admin_client.patch(path, json={"tower_id": str(people["extra"].id), "flat": "204"})
        )["flat"]
        == "204"
    )
    assert success(admin_client.post(path + "/suspend"))["status"] == "suspended"
    assert success(admin_client.post(path + "/activate"))["status"] == "active"
    assert success(admin_client.post(path + "/suspend"))["status"] == "suspended"
    assert admin_client.delete(path).status_code == 204

    order = historical_order(session, people, people["resident"])
    resident_path = f"/api/v1/memberships/{people['resident_membership'].id}"
    assert (
        success(admin_client.patch(resident_path, json={"flat": "New flat"}))["flat"] == "New flat"
    )
    assert admin_client.delete(resident_path).status_code == 409
    session.expire_all()
    assert session.get(Order, order.id).delivery_address["flat"] == "102"


def test_kitchen_member_address_and_membership_cannot_be_removed(admin_client, people):
    path = f"/api/v1/memberships/{people['owner_membership'].id}"
    assert admin_client.patch(path, json={"flat": "Moved"}).status_code == 409
    assert admin_client.delete(path).status_code == 409
    # Idempotent edits do not move a kitchen-managed address.
    assert success(admin_client.patch(path, json={"flat": "101"}))["flat"] == "101"


def test_inactive_accounts_and_paused_societies_reject_membership_creation(admin_client, people):
    data = {
        "user_id": str(people["newcomer"].id),
        "society_id": str(people["garden"].id),
        "tower_id": str(people["tower"].id),
        "flat": "103",
    }
    success(admin_client.post(f"/api/v1/users/{people['newcomer'].id}/deactivate"))
    assert admin_client.post("/api/v1/memberships", json=data).status_code == 409
    success(admin_client.post(f"/api/v1/users/{people['newcomer'].id}/activate"))
    success(admin_client.post(f"/api/v1/societies/{people['garden'].id}/pause"))
    assert admin_client.post("/api/v1/memberships", json=data).status_code == 409


def test_tower_update_delete_and_last_active_tower_guards(admin_client, people):
    garden = people["garden"]
    path = f"/api/v1/towers/{people['extra'].id}"
    page = success(
        admin_client.get(f"/api/v1/societies/{garden.id}/towers", params={"sort": "name"})
    )
    assert page["total"] == 2
    assert success(admin_client.get(path))["name"] == "Tower B"
    assert admin_client.patch(path, json={"name": "tower a"}).status_code == 409
    assert success(admin_client.patch(path, json={"name": "Tower C"}))["name"] == "Tower C"
    assert admin_client.patch(path, json={"society_id": str(people["park"].id)}).status_code == 422
    assert admin_client.delete(f"/api/v1/towers/{people['tower'].id}").status_code == 409
    assert admin_client.delete(path).status_code == 204
    assert admin_client.get(path).status_code == 404
    other_path = f"/api/v1/towers/{people['other'].id}"
    assert admin_client.delete(other_path).status_code == 409
    success(admin_client.post(f"/api/v1/societies/{people['park'].id}/pause"))
    assert admin_client.delete(other_path).status_code == 204
    assert admin_client.post(f"/api/v1/societies/{people['park'].id}/activate").status_code == 409


def test_society_can_be_deleted_only_before_people_or_food_use_it(admin_client, session, people):
    data = {
        "name": "Unused society",
        "address": "Empty Road",
        "city": "Pune",
        "postal_code": "411001",
        "towers": [{"name": "Tower X"}],
    }
    society = success(admin_client.post("/api/v1/societies", json=data), 201)
    path = f"/api/v1/societies/{society['id']}"
    assert (
        success(admin_client.patch(path, json={"name": "Corrected society"}))["name"]
        == "Corrected society"
    )
    assert admin_client.delete(path).status_code == 204
    assert admin_client.get(path).status_code == 404
    assert admin_client.delete(f"/api/v1/societies/{people['garden'].id}").status_code == 409
    assert session.get(Society, people["garden"].id) is not None


def test_resident_joins_active_society_immediately_without_admin_approval(
    client, admin_client, people
):
    from kitchen_http.auth import require_user

    client.app.dependency_overrides[require_user] = lambda: people["newcomer"]
    society_id = people["garden"].id
    path = f"/api/v1/societies/{society_id}/join"
    address = {"tower_id": str(people["tower"].id), "flat": "103"}
    joined = success(client.post(path, json=address), 201)
    assert joined["status"] == "active"
    assert success(client.get(f"/api/v1/societies/{society_id}/kitchens"))["total"] == 1
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
            f"/api/v1/societies/{society_id}/invitations", json={"phone": "+919000000004"}
        ).status_code
        == 404
    )
