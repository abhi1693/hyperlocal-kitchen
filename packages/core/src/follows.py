"""Community-scoped kitchen follows and opt-in menu notification preferences."""

from uuid import UUID

from kitchen_core import catalog
from kitchen_core.catalog_schemas import (
    FollowedKitchenOut,
    FollowedKitchenPage,
    KitchenFollowRequest,
)
from kitchen_core.models import Community, Kitchen, KitchenFollow, Membership, utcnow
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def follow_view(session: Session, follow: KitchenFollow, kitchen: Kitchen) -> FollowedKitchenOut:
    return FollowedKitchenOut(
        kitchen=catalog.kitchen_view(session, kitchen),
        followed_at=follow.created_at,
        notify_new_menu=follow.notify_new_menu,
    )


def follow_kitchen(
    session: Session, user_id: UUID, kitchen_id: UUID, data: KitchenFollowRequest | None
) -> FollowedKitchenOut:
    catalog.get_kitchen(session, user_id, kitchen_id)
    statement = insert(KitchenFollow).values(
        kitchen_id=kitchen_id,
        user_id=user_id,
        notify_new_menu=data.notify_new_menu if data else False,
        created_at=utcnow(),
    )
    if data is not None and "notify_new_menu" in data.model_fields_set:
        statement = statement.on_conflict_do_update(
            index_elements=[KitchenFollow.kitchen_id, KitchenFollow.user_id],
            set_={"notify_new_menu": data.notify_new_menu},
        )
    else:
        statement = statement.on_conflict_do_nothing(
            index_elements=[KitchenFollow.kitchen_id, KitchenFollow.user_id]
        )
    session.execute(statement)
    follow = session.scalar(
        select(KitchenFollow)
        .where(KitchenFollow.kitchen_id == kitchen_id, KitchenFollow.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    assert follow is not None
    return follow_view(session, follow, catalog._get(session, Kitchen, kitchen_id))


def unfollow_kitchen(session: Session, user_id: UUID, kitchen_id: UUID) -> None:
    # Allow cleanup even after membership loss or kitchen/community suspension.
    session.execute(
        delete(KitchenFollow).where(
            KitchenFollow.kitchen_id == kitchen_id, KitchenFollow.user_id == user_id
        )
    )


def followed_kitchens(
    session: Session, user_id: UUID, limit: int, offset: int
) -> FollowedKitchenPage:
    statement = (
        select(KitchenFollow)
        .join(Kitchen, Kitchen.id == KitchenFollow.kitchen_id)
        .join(Community, Community.id == Kitchen.community_id)
        .join(
            Membership,
            (Membership.community_id == Kitchen.community_id)
            & (Membership.user_id == KitchenFollow.user_id),
        )
        .where(
            KitchenFollow.user_id == user_id,
            Membership.status == "active",
            Community.status == "active",
            Kitchen.status == "approved",
        )
        .order_by(KitchenFollow.created_at.desc(), KitchenFollow.kitchen_id)
    )
    rows, total = catalog._page(session, statement, limit, offset)
    return FollowedKitchenPage(
        items=[
            follow_view(session, row, catalog._get(session, Kitchen, row.kitchen_id))
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
