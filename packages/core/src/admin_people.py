"""Administrative account and address changes with relationship guards."""

from uuid import UUID

from kitchen_core import catalog
from kitchen_core.admin_people_schemas import (
    AdminUserOut,
    AdminUserUpdate,
    MembershipCreate,
    MembershipUpdate,
    TowerUpdate,
)
from kitchen_core.catalog_schemas import MembershipAdminOut, TowerOut
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Device,
    Kitchen,
    KitchenMember,
    Membership,
    Order,
    Society,
    Tower,
    User,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session


def locked(session: Session, model, identifier: UUID, *, key_share: bool = False):
    value = session.scalar(
        select(model)
        .where(model.id == identifier)
        .with_for_update(key_share=key_share)
        .execution_options(populate_existing=True)
    )
    if value is None:
        raise DomainError(404, "not_found", "The requested record was not found.")
    return value


def _prohibit_references(session: Session, references) -> None:
    for label, statement in references:
        if session.scalar(select(statement.exists())):
            raise DomainError(409, "record_in_use", f"Linked {label} prevent deleting this record.")


def update_user(session: Session, user_id: UUID, data: AdminUserUpdate) -> AdminUserOut:
    user = locked(session, User, user_id, key_share=True)
    user.name = data.name
    session.flush()
    return AdminUserOut.model_validate(user)


def set_user_active(session: Session, user_id: UUID, active: bool) -> AdminUserOut:
    # Match checkout's NO KEY UPDATE lock before touching memberships or kitchens.
    user = locked(session, User, user_id, key_share=True)
    user.is_active = active
    if not active:
        memberships = list(
            session.scalars(
                select(Membership)
                .where(Membership.user_id == user_id)
                .order_by(Membership.id)
                .with_for_update()
            )
        )
        # Membership UUID order can visit societies differently for two users.
        # Lock the full kitchen set once, in a shared order, before the per-society
        # suspension loop can acquire any kitchen locks.
        list(
            session.scalars(
                select(Kitchen)
                .join(KitchenMember)
                .where(KitchenMember.user_id == user_id)
                .order_by(Kitchen.id)
                .with_for_update(key_share=True, of=Kitchen)
                .execution_options(populate_existing=True)
            )
        )
        for membership in memberships:
            catalog.set_membership_status(session, membership.id, "suspended")
        session.execute(update(Device).where(Device.user_id == user_id).values(is_active=False))
    session.flush()
    return AdminUserOut.model_validate(user)


def delete_society(session: Session, society_id: UUID) -> None:
    locked(session, Society, society_id)
    _prohibit_references(
        session,
        [
            ("residents", select(Membership.id).where(Membership.society_id == society_id)),
            ("kitchens", select(Kitchen.id).where(Kitchen.society_id == society_id)),
            ("orders", select(Order.id).where(Order.society_id == society_id)),
        ],
    )
    # Towers are structural children; an otherwise unused society can remove them.
    session.execute(delete(Tower).where(Tower.society_id == society_id))
    session.execute(delete(Society).where(Society.id == society_id))
    session.flush()


def tower_view(tower: Tower) -> TowerOut:
    return TowerOut(id=tower.id, society_id=tower.society_id, name=tower.name)


def update_tower(session: Session, tower_id: UUID, data: TowerUpdate) -> TowerOut:
    tower = catalog._get(session, Tower, tower_id)
    locked(session, Society, tower.society_id)
    tower = locked(session, Tower, tower_id)
    duplicate = session.scalar(
        select(Tower.id).where(
            Tower.society_id == tower.society_id,
            Tower.id != tower_id,
            func.lower(Tower.name) == data.name.lower(),
        )
    )
    if duplicate is not None:
        raise DomainError(409, "duplicate_tower", "A tower with this name already exists.")
    tower.name = data.name
    session.flush()
    return tower_view(tower)


def delete_tower(session: Session, tower_id: UUID) -> None:
    tower = catalog._get(session, Tower, tower_id)
    society = locked(session, Society, tower.society_id)
    tower = locked(session, Tower, tower_id)
    _prohibit_references(
        session,
        [
            ("residents", select(Membership.id).where(Membership.tower_id == tower_id)),
            ("kitchens", select(Kitchen.id).where(Kitchen.tower_id == tower_id)),
        ],
    )
    another = session.scalar(
        select(Tower.id).where(Tower.society_id == society.id, Tower.id != tower_id).limit(1)
    )
    if society.status == "active" and another is None:
        raise DomainError(409, "towers_required", "An active society must retain a tower.")
    session.delete(tower)
    session.flush()


def create_membership(session: Session, data: MembershipCreate) -> MembershipAdminOut:
    user = locked(session, User, data.user_id, key_share=True)
    society = locked(session, Society, data.society_id)
    if not user.is_active:
        raise DomainError(409, "user_inactive", "An inactive account cannot join a society.")
    catalog.require_active_society(session, society.id)
    tower = catalog._get(session, Tower, data.tower_id)
    if tower.society_id != society.id:
        raise DomainError(422, "tower_society_mismatch", "Choose a tower in the selected society.")
    existing = session.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id, Membership.society_id == society.id
        )
    )
    if existing is not None:
        raise DomainError(409, "membership_exists", "This resident already has a membership.")
    membership = Membership(**data.model_dump(), status="active")
    session.add(membership)
    session.flush()
    return catalog.membership_view(session, membership, admin=True)


def _locked_membership(session: Session, membership_id: UUID) -> Membership:
    current = catalog._get(session, Membership, membership_id)
    locked(session, User, current.user_id, key_share=True)
    return locked(session, Membership, membership_id)


def _kitchen_memberships(membership: Membership):
    return (
        select(KitchenMember.user_id)
        .join(Kitchen)
        .where(
            KitchenMember.user_id == membership.user_id,
            Kitchen.society_id == membership.society_id,
        )
    )


def update_membership(
    session: Session, membership_id: UUID, data: MembershipUpdate
) -> MembershipAdminOut:
    membership = _locked_membership(session, membership_id)
    tower_id = data.tower_id or membership.tower_id
    flat = data.flat if data.flat is not None else membership.flat
    tower = catalog._get(session, Tower, tower_id)
    if tower.society_id != membership.society_id:
        raise DomainError(422, "tower_society_mismatch", "Choose a tower in the selected society.")
    changed = tower_id != membership.tower_id or flat != membership.flat
    if changed and session.scalar(select(_kitchen_memberships(membership).exists())):
        raise DomainError(
            409,
            "kitchen_address_in_use",
            "Manage the resident's kitchen relationships before changing this address.",
        )
    membership.tower_id = tower_id
    membership.flat = flat
    session.flush()
    return catalog.membership_view(session, membership, admin=True)


def delete_membership(session: Session, membership_id: UUID) -> None:
    membership = _locked_membership(session, membership_id)
    _prohibit_references(
        session,
        [
            ("kitchen memberships", _kitchen_memberships(membership)),
            (
                "orders",
                select(Order.id).where(
                    Order.customer_id == membership.user_id,
                    Order.society_id == membership.society_id,
                ),
            ),
        ],
    )
    session.delete(membership)
    session.flush()
