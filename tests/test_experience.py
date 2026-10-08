"""Account experience preferences persist without granting or removing permissions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID

import pytest
from kitchen_core import catalog
from kitchen_core.catalog_schemas import ExperienceUpdate
from kitchen_core.models import Dish, Kitchen, KitchenMember, Membership, User
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_auth import oidc_admin_client as oidc_admin_client
from test_auth import redis_store as redis_store
from test_development_phone_auth import (
    development_phone_configuration as development_phone_configuration,
)
from test_onboarding import as_user
from test_onboarding import onboarding_market as onboarding_market


def join(session, market, status="active"):
    membership = Membership(
        user_id=market["user"].id, community_id=market["community"].id, status=status
    )
    session.add(membership)
    session.commit()
    return membership


def kitchen(session, market, role="owner", status="pending"):
    row = Kitchen(
        community_id=market["community"].id,
        name="Private Kitchen",
        status=status,
        zone_id=market["zone"].id,
        address_label="Private home",
        upi_id="private@bank",
        pickup_enabled=True,
        delivery_enabled=False,
    )
    session.add(row)
    session.flush()
    session.add(KitchenMember(kitchen_id=row.id, user_id=market["user"].id, role=role))
    session.commit()
    return row


def test_new_account_has_no_chosen_mode_and_cannot_choose_before_join(
    client, session, onboarding_market
):
    market = onboarding_market
    as_user(client, market["user"])
    assert client.get("/api/v1/me/experience").json() == {"mode": None, "owned_kitchen": None}
    response = client.patch("/api/v1/me/experience", json={"mode": "kitchen_owner"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "membership_required"
    session.refresh(market["user"])
    assert market["user"].preferred_mode is None
    assert session.scalar(select(func.count()).select_from(KitchenMember)) == 0


@pytest.mark.parametrize("mode", ["customer", "kitchen_owner"])
@pytest.mark.parametrize("status", ["active", "suspended"])
def test_joined_account_can_save_and_reload_a_mode_without_gaining_kitchen_access(
    client, session, onboarding_market, mode, status
):
    market = onboarding_market
    join(session, market, status)
    as_user(client, market["user"])
    response = client.patch("/api/v1/me/experience", json={"mode": mode})
    assert response.status_code == 200, response.text
    assert response.json() == {"mode": mode, "owned_kitchen": None}
    assert client.get("/api/v1/me/experience").json() == response.json()
    assert client.get("/api/v1/me/onboarding").json()["completed"] is True
    session.refresh(market["user"])
    assert market["user"].preferred_mode == mode
    assert session.scalar(select(func.count()).select_from(KitchenMember)) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"mode": None},
        {"mode": "owner"},
        {"mode": "admin"},
        {"mode": "customer", "roles": ["platform_admin"]},
        {"mode": "customer", "user_id": "another-user"},
        {"mode": "customer", "owned_kitchen": {"id": "fake"}},
    ],
)
def test_mode_schema_rejects_unknown_values_and_permission_fields(
    client, session, onboarding_market, body
):
    market = onboarding_market
    join(session, market)
    as_user(client, market["user"])
    assert client.patch("/api/v1/me/experience", json=body).status_code == 422
    session.refresh(market["user"])
    assert market["user"].preferred_mode is None


@pytest.mark.parametrize("status", ["pending", "approved", "suspended"])
def test_actual_owner_without_a_preference_is_inferred_even_when_kitchen_is_not_approved(
    client, session, onboarding_market, status
):
    market = onboarding_market
    join(session, market)
    owned = kitchen(session, market, status=status)
    as_user(client, market["user"])
    result = client.get("/api/v1/me/experience").json()
    assert result["mode"] == "kitchen_owner"
    assert result["owned_kitchen"]["id"] == str(owned.id)
    assert result["owned_kitchen"]["status"] == status
    assert result["owned_kitchen"]["address_label"] == "Private home"
    assert result["owned_kitchen"]["upi_id"] == "private@bank"
    session.refresh(market["user"])
    assert market["user"].preferred_mode is None


def test_returning_to_customer_mode_keeps_ownership_and_one_kitchen_limit(
    client, session, onboarding_market
):
    market = onboarding_market
    join(session, market)
    owned = kitchen(session, market)
    as_user(client, market["user"])
    result = client.patch("/api/v1/me/experience", json={"mode": "customer"}).json()
    assert result["mode"] == "customer"
    assert result["owned_kitchen"]["id"] == str(owned.id)
    assert session.get(KitchenMember, (owned.id, market["user"].id)).role == "owner"
    assert (
        client.post(
            f"/api/v1/kitchens/{owned.id}/dishes", json={"name": "Owner's dish"}
        ).status_code
        == 201
    )
    attempted = client.post(
        "/api/v1/kitchens",
        json={"community_id": str(market["community"].id), "name": "Another Kitchen"},
    )
    assert attempted.status_code == 409
    assert attempted.json()["detail"]["code"] == "kitchen_exists"


def test_manager_association_does_not_count_as_ownership(client, session, onboarding_market):
    market = onboarding_market
    join(session, market)
    managed = kitchen(session, market, role="manager")
    as_user(client, market["user"])
    assert client.get("/api/v1/me/experience").json() == {"mode": None, "owned_kitchen": None}
    response = client.patch("/api/v1/me/experience", json={"mode": "kitchen_owner"})
    assert response.json() == {"mode": "kitchen_owner", "owned_kitchen": None}
    assert session.get(KitchenMember, (managed.id, market["user"].id)).role == "manager"


def test_mode_and_owned_kitchen_never_leak_to_another_account(client, session, onboarding_market):
    market = onboarding_market
    join(session, market)
    owned = kitchen(session, market)
    market["user"].preferred_mode = "kitchen_owner"
    session.add(Membership(user_id=market["other_user"].id, community_id=market["community"].id))
    session.commit()
    as_user(client, market["other_user"])
    assert client.get("/api/v1/me/experience").json() == {"mode": None, "owned_kitchen": None}
    assert client.patch("/api/v1/me/experience", json={"mode": "customer"}).json() == {
        "mode": "customer",
        "owned_kitchen": None,
    }
    session.refresh(market["user"])
    assert market["user"].preferred_mode == "kitchen_owner"
    denied = client.patch(f"/api/v1/kitchens/{owned.id}", json={"name": "Changed by customer"})
    assert denied.status_code == 403


def test_owner_preference_cannot_manage_another_kitchen(client, session, onboarding_market):
    market = onboarding_market
    join(session, market)
    session.add(Membership(user_id=market["other_user"].id, community_id=market["community"].id))
    session.commit()
    owned = kitchen(session, market)
    as_user(client, market["other_user"])
    assert client.patch("/api/v1/me/experience", json={"mode": "kitchen_owner"}).status_code == 200
    assert (
        client.post(
            f"/api/v1/kitchens/{owned.id}/dishes", json={"name": "Unauthorized dish"}
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/kitchens/{owned.id}/dishes").status_code == 403
    assert session.scalar(select(func.count()).select_from(Dish)) == 0


def test_pending_kitchen_can_prepare_dishes_and_drafts_but_cannot_publish(
    client, session, onboarding_market
):
    market = onboarding_market
    join(session, market)
    pending = kitchen(session, market)
    as_user(client, market["user"])
    created = client.post(f"/api/v1/kitchens/{pending.id}/dishes", json={"name": "Soup"})
    assert created.status_code == 201
    dish = created.json()
    point = client.post(
        f"/api/v1/kitchens/{pending.id}/pickup-points",
        json={"name": "Front gate", "address_label": "Private home"},
    )
    assert point.status_code == 201
    ready = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=7, minute=30, second=0, microsecond=0
    )
    listing = {
        "pickup_point_ids": [point.json()["id"]],
        "dish_id": dish["id"],
        "service_date": ready.date().isoformat(),
        "available_from": ready.isoformat(),
        "available_until": (ready + timedelta(hours=2)).isoformat(),
        "order_cutoff": (ready - timedelta(hours=1)).isoformat(),
        "price_paise": 10000,
        "quantity_total": 5,
        "pickup_enabled": True,
        "delivery_enabled": False,
        "status": "draft",
    }
    draft = client.post(f"/api/v1/kitchens/{pending.id}/menu-listings", json=listing)
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "draft"
    assert (
        client.patch(
            f"/api/v1/menu-listings/{draft.json()['id']}", json={"status": "published"}
        ).status_code
        == 409
    )
    listing["status"] = "published"
    assert (
        client.post(f"/api/v1/kitchens/{pending.id}/menu-listings", json=listing).status_code == 409
    )


def test_experience_survives_phone_login_and_cannot_grant_admin_access(
    client, oidc_admin_client, redis_store, session, onboarding_market
):
    market = onboarding_market
    first = client.post("/api/v1/auth/mobile/phone", json={"phone": "+919876543210"}).json()
    headers = {"Authorization": "Bearer " + first["session_token"]}
    assert (
        client.post(
            "/api/v1/me/onboarding",
            json={"community_id": str(market["community"].id)},
            headers=headers,
        ).status_code
        == 200
    )
    selected = client.patch(
        "/api/v1/me/experience", json={"mode": "kitchen_owner"}, headers=headers
    )
    assert selected.json() == {"mode": "kitchen_owner", "owned_kitchen": None}
    assert oidc_admin_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    second = client.post("/api/v1/auth/mobile/phone", json={"phone": "+919876543210"}).json()
    assert second["user"]["id"] == first["user"]["id"]
    assert (
        client.get(
            "/api/v1/me/experience", headers={"Authorization": "Bearer " + second["session_token"]}
        ).json()
        == selected.json()
    )
    saved = session.get(User, UUID(second["user"]["id"]))
    saved.is_active = False
    session.commit()
    assert (
        client.patch(
            "/api/v1/me/experience",
            json={"mode": "customer"},
            headers={"Authorization": "Bearer " + second["session_token"]},
        ).status_code
        == 401
    )


def test_experience_routes_require_authentication(client, redis_store):
    assert client.get("/api/v1/me/experience").status_code == 401
    assert client.patch("/api/v1/me/experience", json={"mode": "customer"}).status_code == 401


def test_preference_database_constraint_accepts_only_defined_modes(session, onboarding_market):
    user = onboarding_market["user"]
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            text("UPDATE users SET preferred_mode = :mode WHERE id = :id"),
            {"mode": "platform_admin", "id": user.id},
        )
    session.refresh(user)
    assert user.preferred_mode is None


def test_concurrent_mode_updates_are_serialized_and_last_writer_persists(
    session_factory, session, onboarding_market
):
    market = onboarding_market
    join(session, market)
    first_saved, second_started, release_first = Event(), Event(), Event()

    def first_device():
        with session_factory() as transaction:
            user = transaction.get(User, market["user"].id)
            result = catalog.update_experience(transaction, user, ExperienceUpdate(mode="customer"))
            first_saved.set()
            assert release_first.wait(5)
            transaction.commit()
            return result

    def second_device():
        with session_factory() as transaction:
            user = transaction.get(User, market["user"].id)
            second_started.set()
            result = catalog.update_experience(
                transaction, user, ExperienceUpdate(mode="kitchen_owner")
            )
            transaction.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_device)
        assert first_saved.wait(5)
        second = executor.submit(second_device)
        assert second_started.wait(5)
        assert not second.done()
        release_first.set()
        assert first.result(5).mode == "customer"
        assert second.result(5).mode == "kitchen_owner"
    with session_factory() as transaction:
        assert catalog.experience_state(transaction, market["user"].id).mode == "kitchen_owner"
