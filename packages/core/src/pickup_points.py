"""Community collection locations, managed by platform admins or owning kitchens."""

from uuid import UUID

from kitchen_core import catalog
from kitchen_core.catalog_schemas import PickupPointCreate, PickupPointOut, PickupPointUpdate
from kitchen_core.errors import DomainError
from kitchen_core.models import PickupPoint, eligible_pickup_point
from sqlalchemy import select
from sqlalchemy.orm import Session


def list_points(
    session: Session,
    community_id: UUID,
    *,
    kitchen_id: UUID | None = None,
    include_inactive: bool = False,
) -> list[PickupPointOut]:
    statement = select(PickupPoint).where(PickupPoint.community_id == community_id)
    if kitchen_id is not None:
        statement = statement.where(PickupPoint.kitchen_id == kitchen_id)
    if not include_inactive:
        statement = statement.where(eligible_pickup_point())
    return [
        PickupPointOut.model_validate(p)
        for p in session.scalars(statement.order_by(PickupPoint.name, PickupPoint.id))
    ]


def create_point(
    session: Session, community_id: UUID, data: PickupPointCreate, *, kitchen_id: UUID | None = None
) -> PickupPointOut:
    catalog.require_active_community(session, community_id)
    catalog.validate_zone(session, community_id, data.zone_id)
    point = PickupPoint(community_id=community_id, kitchen_id=kitchen_id, **data.model_dump())
    session.add(point)
    session.flush()
    return PickupPointOut.model_validate(point)


def update_point(
    session: Session, point_id: UUID, data: PickupPointUpdate, *, kitchen_id: UUID | None = None
) -> PickupPointOut:
    point = catalog._locked(session, PickupPoint, point_id)
    if kitchen_id is not None and point.kitchen_id != kitchen_id:
        raise DomainError(404, "not_found", "Pickup point was not found in this kitchen.")
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "address_label", "active"):
        if field in values and values[field] is None:
            raise DomainError(422, "required_field", f"{field} cannot be empty.")
    if "zone_id" in values:
        catalog.validate_zone(session, point.community_id, values["zone_id"])
    for field, value in values.items():
        setattr(point, field, value)
    session.flush()
    return PickupPointOut.model_validate(point)
