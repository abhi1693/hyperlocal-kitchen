"""Joining any community completes first-use setup; an address stays optional."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from kitchen_core import catalog
from kitchen_core.catalog_schemas import OnboardingComplete
from kitchen_core.models import Community, CommunityZone, Membership, User
from kitchen_http.auth import require_user
from sqlalchemy import func, select
from test_auth import redis_store as redis_store
from test_development_phone_auth import (
    development_phone_configuration as development_phone_configuration,
)


@pytest.fixture
def onboarding_market(session):
    user = User(oidc_subject="onboarding-resident", oidc_issuer="https://identity.test")
    other_user = User(oidc_subject="onboarding-other", oidc_issuer="https://identity.test")
    community = Community(name="Home", city="Pune", status="active")
    other = Community(name="Office", city="Pune", status="active")
    session.add_all([user, other_user, community, other])
    session.flush()
    zone = CommunityZone(community_id=community.id, name="Tower A", active=True)
    disabled = CommunityZone(community_id=community.id, name="Tower Old", active=False)
    outside = CommunityZone(community_id=other.id, name="Office Zone", active=True)
    session.add_all([zone, disabled, outside])
    session.commit()
    return dict(
        user=user,
        other_user=other_user,
        community=community,
        other=other,
        zone=zone,
        disabled=disabled,
        outside=outside,
    )


def as_user(client, user):
    client.app.dependency_overrides[require_user] = lambda: user


def payload(market, **changes):
    return {
        "community_id": str(market["community"].id),
        "zone_id": str(market["zone"].id),
        "address_label": " A-1204 ",
        **changes,
    }


def membership(session, market, **changes):
    row = Membership(
        user_id=market["user"].id,
        community_id=market["community"].id,
        zone_id=market["zone"].id,
        status="active",
        **changes,
    )
    session.add(row)
    session.commit()
    return row


@pytest.mark.parametrize("address", [None, " Home 12 "])
def test_new_user_completes_setup_by_joining_with_optional_address(
    client, session, onboarding_market, address
):
    market = onboarding_market
    as_user(client, market["user"])
    assert client.get("/api/v1/me/onboarding").json() == {"completed": False, "membership": None}
    saved = client.post("/api/v1/me/onboarding", json=payload(market, address_label=address))
    assert saved.status_code == 200, saved.text
    state = saved.json()
    assert state["completed"] is True
    assert state["membership"]["address_label"] == (address.strip() if address else None)
    assert state["membership"]["zone_id"] == str(market["zone"].id)
    assert state["membership"]["status"] == "active"
    assert client.get("/api/v1/me/onboarding").json() == state
    repeated = client.post("/api/v1/me/onboarding", json=payload(market, address_label="A-999"))
    assert repeated.json() == state
    assert session.scalar(select(func.count()).select_from(Membership)) == 1


@pytest.mark.parametrize("address", [None, "", " \t\n\u2003"])
def test_existing_join_completes_onboarding_without_address_requirements(
    client, session, onboarding_market, address
):
    market = onboarding_market
    existing = membership(session, market, address_label=address)
    as_user(client, market["user"])
    state = client.get("/api/v1/me/onboarding").json()
    assert state["completed"] is True
    assert state["membership"]["id"] == str(existing.id)
    assert state["membership"]["address_label"] == address
    saved = client.post("/api/v1/me/onboarding", json=payload(market))
    assert saved.status_code == 200, saved.text
    assert saved.json()["completed"] is True
    assert saved.json()["membership"]["id"] == str(existing.id)
    assert saved.json() == state


def test_community_without_zones_accepts_an_optional_address(client, session, onboarding_market):
    market = onboarding_market
    empty = Community(name="Independent Homes", city="Pune", status="active")
    session.add(empty)
    session.commit()
    as_user(client, market["user"])
    saved = client.post("/api/v1/me/onboarding", json={"community_id": str(empty.id)})
    assert saved.status_code == 200
    assert saved.json()["membership"]["zone_id"] is None
    assert saved.json()["membership"]["address_label"] is None


@pytest.mark.parametrize(
    "restriction",
    [
        "paused",
        "disabled_zone",
        "other_zone",
        "missing_zone",
        "missing_community",
        "inactive_user",
    ],
)
def test_invalid_initial_setup_is_atomic(client, session, onboarding_market, restriction):
    market = onboarding_market
    body = payload(market)
    expected = 422
    if restriction == "paused":
        market["community"].status = "paused"
        expected = 409
    elif restriction == "disabled_zone":
        body["zone_id"] = str(market["disabled"].id)
    elif restriction == "other_zone":
        body["zone_id"] = str(market["outside"].id)
    elif restriction == "missing_zone":
        body["zone_id"] = str(uuid4())
        expected = 404
    elif restriction == "missing_community":
        body["community_id"] = str(uuid4())
        expected = 404
    else:
        market["user"].is_active = False
        expected = 403
    session.commit()
    as_user(client, market["user"])
    response = client.post("/api/v1/me/onboarding", json=body)
    assert response.status_code == expected, response.text
    assert session.scalar(select(func.count()).select_from(Membership)) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"address_label": "Home"},
        {"address_label": " \t\u2003"},
        {"address_label": "x" * 251},
        {"address_label": "x\x00y"},
        {"address_label": "Home", "user_id": str(uuid4())},
        {"address_label": "Home", "completed": True},
    ],
)
def test_setup_payload_requires_community_and_rejects_invalid_optional_address(
    client, session, onboarding_market, body
):
    market = onboarding_market
    as_user(client, market["user"])
    submitted = {"community_id": str(market["community"].id), **body}
    if body in ({}, {"address_label": "Home"}):
        submitted.pop("community_id")
    assert client.post("/api/v1/me/onboarding", json=submitted).status_code == 422
    assert session.scalar(select(func.count()).select_from(Membership)) == 0


@pytest.mark.parametrize("change", ["suspended", "paused", "disabled_zone", "clear_address"])
def test_completed_onboarding_is_not_repeated_after_later_membership_changes(
    client, session, onboarding_market, change
):
    market = onboarding_market
    as_user(client, market["user"])
    saved = client.post("/api/v1/me/onboarding", json=payload(market)).json()
    existing = session.get(Membership, UUID(saved["membership"]["id"]))
    if change == "suspended":
        existing.status = "suspended"
    elif change == "paused":
        market["community"].status = "paused"
    elif change == "disabled_zone":
        market["zone"].active = False
    else:
        existing.address_label = None
    session.commit()
    state = client.get("/api/v1/me/onboarding").json()
    assert state["completed"] is True
    response = client.post("/api/v1/me/onboarding", json=payload(market, address_label="Other"))
    assert response.json() == state


def test_generic_join_and_legacy_memberships_are_recognized_without_a_local_flag(
    client, session, onboarding_market
):
    market = onboarding_market
    as_user(client, market["user"])
    joined = client.post(f"/api/v1/communities/{market['community'].id}/join", json={})
    assert joined.status_code == 201
    state = client.get("/api/v1/me/onboarding").json()
    assert state["completed"] is True
    assert state["membership"]["id"] == joined.json()["id"]


def test_another_users_address_cannot_complete_or_prefill_onboarding(
    client, session, onboarding_market
):
    market = onboarding_market
    membership(session, market, address_label="Home")
    as_user(client, market["other_user"])
    assert client.get("/api/v1/me/onboarding").json() == {"completed": False, "membership": None}


def test_completion_is_detected_beyond_membership_pagination(client, session, onboarding_market):
    market = onboarding_market
    rows = []
    for index in range(35):
        community = Community(name=f"Community {index:02}", city="Pune", status="active")
        session.add(community)
        session.flush()
        row = Membership(
            user_id=market["user"].id,
            community_id=community.id,
            address_label="Home" if index == 34 else None,
            created_at=datetime.now(UTC) + timedelta(seconds=index),
        )
        session.add(row)
        rows.append(row)
    session.commit()
    as_user(client, market["user"])
    assert len(client.get("/api/v1/me/communities").json()) == 30
    state = client.get("/api/v1/me/onboarding").json()
    assert state["completed"] is True
    assert state["membership"]["id"] == str(rows[0].id)


def test_onboarding_persists_across_development_phone_sessions(
    client, redis_store, session, onboarding_market
):
    market = onboarding_market
    first = client.post("/api/v1/auth/mobile/phone", json={"phone": "+919876543210"}).json()
    headers = {"Authorization": "Bearer " + first["session_token"]}
    assert client.get("/api/v1/me/onboarding", headers=headers).json()["completed"] is False
    saved = client.post(
        "/api/v1/me/onboarding", headers=headers, json={"community_id": str(market["community"].id)}
    )
    assert saved.status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    second = client.post("/api/v1/auth/mobile/phone", json={"phone": "+919876543210"}).json()
    assert second["user"]["id"] == first["user"]["id"]
    assert second["session_token"] != first["session_token"]
    assert (
        client.get(
            "/api/v1/me/onboarding", headers={"Authorization": "Bearer " + second["session_token"]}
        ).json()
        == saved.json()
    )


def test_onboarding_requires_authentication(client, redis_store, onboarding_market):
    assert client.get("/api/v1/me/onboarding").status_code == 401
    assert client.post("/api/v1/me/onboarding", json=payload(onboarding_market)).status_code == 401


def test_concurrent_devices_only_save_first_completed_setup(session_factory, onboarding_market):
    market = onboarding_market
    first_saved = Event()
    second_started = Event()
    release_first = Event()

    def first_device():
        with session_factory() as session:
            user = session.get(User, market["user"].id)
            state = catalog.complete_onboarding(
                session,
                user,
                OnboardingComplete(
                    community_id=market["community"].id, address_label="First device"
                ),
            )
            first_saved.set()
            assert release_first.wait(5)
            session.commit()
            return state

    def second_device():
        with session_factory() as session:
            user = session.get(User, market["user"].id)
            second_started.set()
            state = catalog.complete_onboarding(
                session,
                user,
                OnboardingComplete(community_id=market["other"].id, address_label="Second device"),
            )
            session.commit()
            return state

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_device)
        assert first_saved.wait(5)
        second = executor.submit(second_device)
        assert second_started.wait(5)
        assert not second.done()
        release_first.set()
        assert first.result(5).model_dump() == second.result(5).model_dump()
    with session_factory() as session:
        rows = list(
            session.scalars(select(Membership).where(Membership.user_id == market["user"].id))
        )
        assert len(rows) == 1
        assert rows[0].address_label == "First device"
