"""Resident pickup edits obey kitchen eligibility and ownership boundaries."""

from uuid import UUID

import pytest
from kitchen_core.models import Membership, PickupPoint
from sqlalchemy import select
from test_catalog import as_user
from test_catalog import market as catalog_market


@pytest.fixture
def market(session):
    return catalog_market.__wrapped__(session)


def own_point(session, market):
    return session.scalar(select(PickupPoint).where(PickupPoint.kitchen_id == market["kitchen"].id))


@pytest.mark.parametrize("kitchen_status", ["pending", "approved"])
def test_eligible_kitchen_owner_can_edit_and_reactivate_a_pickup_point(
    client, session, market, kitchen_status
):
    market["kitchen"].status = kitchen_status
    pickup = own_point(session, market)
    pickup.active = False
    session.commit()
    as_user(client, market["owner"])
    result = client.patch(
        f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points/{pickup.id}",
        json={"active": True, "address_label": "South gate", "instructions": "Ring the bell"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["active"] is True
    assert result.json()["address_label"] == "South gate"
    session.refresh(pickup)
    assert pickup.active is True and pickup.instructions == "Ring the bell"
    assert market["kitchen"].address_label == "B-1204"


@pytest.mark.parametrize(
    "restriction,status,code",
    [
        ("kitchen", 403, "kitchen_suspended"),
        ("community", 409, "community_unavailable"),
        ("membership", 403, "membership_required"),
    ],
)
@pytest.mark.parametrize("body", [{"active": True}, {"address_label": "Changed pickup"}])
def test_ineligible_owner_cannot_change_or_reactivate_a_pickup_point(
    client, session, market, restriction, status, code, body
):
    pickup = own_point(session, market)
    pickup.active = False
    if restriction == "kitchen":
        market["kitchen"].status = "suspended"
    elif restriction == "community":
        market["community"].status = "paused"
    else:
        membership = session.scalar(
            select(Membership).where(Membership.user_id == market["owner"].id)
        )
        membership.status = "suspended"
    session.commit()
    as_user(client, market["owner"])
    denied = client.patch(
        f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points/{pickup.id}", json=body
    )
    assert denied.status_code == status, denied.text
    assert denied.json()["detail"]["code"] == code
    session.refresh(pickup)
    assert pickup.active is False and pickup.address_label == "B-1204"


@pytest.mark.parametrize("account", ["customer", "outsider"])
def test_app_mode_does_not_grant_access_to_another_kitchens_pickup_point(
    client, session, market, account
):
    pickup = own_point(session, market)
    market[account].preferred_mode = "kitchen_owner"
    session.commit()
    as_user(client, market[account])
    denied = client.patch(
        f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points/{pickup.id}",
        json={"address_label": "Changed by someone else"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "kitchen_access_denied"
    session.refresh(pickup)
    assert pickup.address_label == "B-1204"


def test_kitchen_owner_cannot_edit_a_shared_or_another_kitchens_pickup_point(
    client, session, market
):
    shared = PickupPoint(
        community_id=market["community"].id, name="Community gate", address_label="Main road"
    )
    session.add(shared)
    session.commit()
    as_user(client, market["customer"])
    created = client.post(
        "/api/v1/kitchens",
        json={
            "community_id": str(market["community"].id),
            "name": "Other owner's kitchen",
            "address_label": "House 42",
        },
    )
    assert created.status_code == 201, created.text
    other_id = created.json()["id"]
    other_pickup = session.scalar(
        select(PickupPoint).where(PickupPoint.kitchen_id == UUID(other_id))
    )
    as_user(client, market["owner"])
    for pickup in (shared, other_pickup):
        denied = client.patch(
            f"/api/v1/kitchens/{market['kitchen'].id}/pickup-points/{pickup.id}",
            json={"active": False},
        )
        assert denied.status_code == 404
        session.refresh(pickup)
        assert pickup.active is True
    own = own_point(session, market)
    denied = client.patch(
        f"/api/v1/kitchens/{other_id}/pickup-points/{own.id}", json={"active": False}
    )
    assert denied.status_code == 403
    session.refresh(own)
    assert own.active is True
