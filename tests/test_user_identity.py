"""Delivery contacts never merge or replace stable Zitadel-backed accounts."""

from kitchen_core.auth import save_user
from kitchen_core.models import Membership, Society, Tower, User
from sqlalchemy import func, select


def identity(subject, phone):
    # save_user receives this shape after the separate OIDC validation boundary.
    return {"issuer": "https://identity.example.test", "subject": subject, "phone": phone}


def household(session, first, second):
    society = Society(
        name="Shared household society",
        address="Society Road",
        city="Pune",
        postal_code="411001",
        status="active",
    )
    session.add(society)
    session.flush()
    tower = Tower(society_id=society.id, name="Tower A")
    session.add(tower)
    session.flush()
    memberships = [
        Membership(user_id=user.id, society_id=society.id, tower_id=tower.id, flat=flat)
        for user, flat in ((first, "101"), (second, "202"))
    ]
    session.add_all(memberships)
    session.flush()
    return memberships


def test_distinct_zitadel_subjects_can_share_a_verified_delivery_contact(session):
    phone = "+919876543210"
    first_record = identity("first-resident", phone)
    second_record = identity("second-resident", phone)
    first = save_user(session, first_record)
    second = save_user(session, second_record)
    first_id, second_id = first.id, second.id
    session.commit()

    assert first_id != second_id
    assert first_record["user_id"] == str(first_id)
    assert second_record["user_id"] == str(second_id)
    assert session.scalar(select(func.count()).select_from(User).where(User.phone == phone)) == 2
    assert save_user(session, identity("first-resident", phone)).id == first_id
    assert save_user(session, identity("second-resident", phone)).id == second_id
    assert session.scalar(select(func.count()).select_from(User)) == 2


def test_contact_reassignment_keeps_users_and_society_memberships_separate(session):
    original_phone, other_phone = "+919876543210", "+919876543211"
    first = save_user(session, identity("first-resident", original_phone))
    second = save_user(session, identity("second-resident", other_phone))
    memberships = household(session, first, second)
    first_id, second_id = first.id, second.id
    membership_ids = [membership.id for membership in memberships]
    session.commit()

    # An existing resident may adopt a contact already used by another account.
    changed = save_user(session, identity("first-resident", other_phone))
    assert changed.id == first_id
    # A recycled former contact still creates an independent provider identity.
    newcomer = save_user(session, identity("new-resident", original_phone))
    newcomer_id = newcomer.id
    session.commit()
    session.expire_all()

    assert len({first_id, second_id, newcomer_id}) == 3
    assert session.get(User, first_id).oidc_subject == "first-resident"
    assert session.get(User, second_id).oidc_subject == "second-resident"
    assert session.get(User, newcomer_id).oidc_subject == "new-resident"
    assert session.get(User, first_id).phone == other_phone
    assert session.get(User, second_id).phone == other_phone
    assert session.get(User, newcomer_id).phone == original_phone
    assert session.get(Membership, membership_ids[0]).user_id == first_id
    assert session.get(Membership, membership_ids[1]).user_id == second_id
    assert (
        session.scalar(
            select(func.count()).select_from(Membership).where(Membership.user_id == newcomer_id)
        )
        == 0
    )


def test_removing_a_delivery_contact_preserves_the_provider_account(session):
    record = identity("resident-with-contact", "+919876543210")
    user = save_user(session, record)
    identifier = user.id
    session.commit()

    missing_contact = identity("resident-with-contact", None)
    updated = save_user(session, missing_contact)
    session.commit()

    assert updated.id == identifier
    assert updated.phone is None
    assert missing_contact["user_id"] == str(identifier)
    assert session.scalar(select(func.count()).select_from(User)) == 1
