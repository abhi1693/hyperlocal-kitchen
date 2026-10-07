"""Administrative account and address changes with relationship guards."""

from uuid import UUID

from kitchen_core import catalog
from kitchen_core.admin_people_schemas import (
    AdminUserOut,
    AdminUserUpdate,
    CommunityZoneUpdate,
    MembershipCreate,
    MembershipUpdate,
)
from kitchen_core.catalog_schemas import CommunityZoneOut, MembershipAdminOut
from kitchen_core.errors import DomainError
from kitchen_core.models import (
    Community,
    CommunityZone,
    Device,
    Kitchen,
    KitchenMember,
    Membership,
    Order,
    PickupPoint,
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
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    session.flush()
    return AdminUserOut.model_validate(user)


def delete_user(session: Session, user_id: UUID) -> None:
    user = locked(session, User, user_id)
    # Include every foreign key to preserve orders, audit history and future relations.
    references = []
    for table in User.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.column is User.__table__.c.id:
                references.append((table.name, select(table).where(foreign_key.parent == user_id)))
    _prohibit_references(session, references)
    session.delete(user)
    session.flush()


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
        # Membership UUID order can visit communities differently for two users.
        # Lock the full kitchen set once, in a shared order, before the per-community
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


def delete_community(session: Session, community_id: UUID) -> None:
    locked(session, Community, community_id)
    _prohibit_references(
        session,
        [
            ("residents", select(Membership.id).where(Membership.community_id == community_id)),
            ("kitchens", select(Kitchen.id).where(Kitchen.community_id == community_id)),
            ("orders", select(Order.id).where(Order.community_id == community_id)),
            (
                "pickup points",
                select(PickupPoint.id).where(PickupPoint.community_id == community_id),
            ),
        ],
    )
    # CommunityZones are structural children; an otherwise unused community can remove them.
    # Self-referencing zones must be detached before removing the unused hierarchy.
    session.execute(
        update(CommunityZone)
        .where(CommunityZone.community_id == community_id)
        .values(parent_zone_id=None)
    )
    session.execute(delete(CommunityZone).where(CommunityZone.community_id == community_id))
    session.execute(delete(Community).where(Community.id == community_id))
    session.flush()


def zone_view(zone: CommunityZone) -> CommunityZoneOut:
    return catalog.zone_view(zone)


def update_zone(session: Session, zone_id: UUID, data: CommunityZoneUpdate) -> CommunityZoneOut:
    zone = catalog._get(session, CommunityZone, zone_id)
    locked(session, Community, zone.community_id)
    zone = locked(session, CommunityZone, zone_id)
    values = data.model_dump(exclude_unset=True)
    if any(
        values.get(field) is None for field in ("name", "zone_type", "active") if field in values
    ):
        raise DomainError(422, "required_field", "Name, type and active cannot be empty.")
    if "name" in values and session.scalar(
        select(CommunityZone.id).where(
            CommunityZone.community_id == zone.community_id,
            CommunityZone.id != zone_id,
            func.lower(CommunityZone.name) == values["name"].lower(),
        )
    ):
        raise DomainError(409, "duplicate_zone", "A zone with this name already exists.")
    if "parent_zone_id" in values:
        catalog.validate_zone(session, zone.community_id, values["parent_zone_id"])
        parent_id = values["parent_zone_id"]
        visited = {zone_id}
        while parent_id is not None:
            if parent_id in visited:
                raise DomainError(422, "zone_cycle", "Zones cannot form a cycle.")
            visited.add(parent_id)
            parent_id = catalog._get(session, CommunityZone, parent_id).parent_zone_id
    for field, value in values.items():
        setattr(zone, field, value)
    session.flush()
    return zone_view(zone)


def delete_zone(session: Session, zone_id: UUID) -> None:
    zone = catalog._get(session, CommunityZone, zone_id)
    locked(session, Community, zone.community_id)
    zone = locked(session, CommunityZone, zone_id)
    _prohibit_references(
        session,
        [
            ("members", select(Membership.id).where(Membership.zone_id == zone_id)),
            ("kitchens", select(Kitchen.id).where(Kitchen.zone_id == zone_id)),
            (
                "child zones",
                select(CommunityZone.id).where(CommunityZone.parent_zone_id == zone_id),
            ),
            ("pickup points", select(PickupPoint.id).where(PickupPoint.zone_id == zone_id)),
        ],
    )
    session.delete(zone)
    session.flush()


def create_membership(session: Session, data: MembershipCreate) -> MembershipAdminOut:
    user = locked(session, User, data.user_id, key_share=True)
    community = locked(session, Community, data.community_id)
    if not user.is_active:
        raise DomainError(409, "user_inactive", "An inactive account cannot join a community.")
    catalog.require_active_community(session, community.id)
    catalog.validate_zone(session, community.id, data.zone_id)
    existing = session.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id, Membership.community_id == community.id
        )
    )
    if existing is not None:
        raise DomainError(409, "membership_exists", "This member already has a membership.")
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
            Kitchen.community_id == membership.community_id,
        )
    )


def update_membership(
    session: Session, membership_id: UUID, data: MembershipUpdate
) -> MembershipAdminOut:
    membership = _locked_membership(session, membership_id)
    values = data.model_dump(exclude_unset=True)
    if "zone_id" in values:
        catalog.validate_zone(session, membership.community_id, values["zone_id"])
    for field, value in values.items():
        setattr(membership, field, value)
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
                    Order.community_id == membership.community_id,
                ),
            ),
        ],
    )
    session.delete(membership)
    session.flush()
