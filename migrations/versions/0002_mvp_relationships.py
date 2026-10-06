"""Enforce MVP relationships and remove duplicate fields."""

import sqlalchemy as sa
from alembic import op

revision = "0002_mvp_relationships"
down_revision = "0001_mvp"
branch_labels = None
depends_on = None


def upgrade():
    # Create the referenced composite keys before replacing child references.
    op.create_unique_constraint("uq_towers_id_society", "towers", ["id", "society_id"])
    op.create_unique_constraint("uq_kitchens_id_society", "kitchens", ["id", "society_id"])
    op.create_unique_constraint("uq_dishes_id_kitchen", "dishes", ["id", "kitchen_id"])
    op.create_unique_constraint("uq_orders_id_customer", "orders", ["id", "customer_id"])

    op.drop_constraint("society_memberships_tower_id_fkey", "society_memberships", "foreignkey")
    op.create_foreign_key(
        "fk_membership_tower_society",
        "society_memberships",
        "towers",
        ["tower_id", "society_id"],
        ["id", "society_id"],
    )
    op.drop_constraint("kitchens_tower_id_fkey", "kitchens", "foreignkey")
    op.create_foreign_key(
        "fk_kitchen_tower_society",
        "kitchens",
        "towers",
        ["tower_id", "society_id"],
        ["id", "society_id"],
    )
    op.drop_constraint("menu_listings_dish_id_fkey", "menu_listings", "foreignkey")
    op.create_foreign_key(
        "fk_listing_dish_kitchen",
        "menu_listings",
        "dishes",
        ["dish_id", "kitchen_id"],
        ["id", "kitchen_id"],
    )
    op.drop_constraint("orders_kitchen_id_fkey", "orders", "foreignkey")
    op.create_foreign_key(
        "fk_order_kitchen_society",
        "orders",
        "kitchens",
        ["kitchen_id", "society_id"],
        ["id", "society_id"],
    )
    op.drop_constraint("order_idempotency_order_id_fkey", "order_idempotency", "foreignkey")
    op.create_foreign_key(
        "fk_idempotency_order_customer",
        "order_idempotency",
        "orders",
        ["order_id", "customer_id"],
        ["id", "customer_id"],
    )

    # Preserve a legacy rejection reason in the existing order timeline.
    op.execute("""
        UPDATE order_events AS event
        SET reason = orders.rejection_reason
        FROM orders
        WHERE event.order_id = orders.id AND event.status = 'rejected'
          AND event.reason IS NULL AND orders.rejection_reason IS NOT NULL
    """)
    op.drop_column("menu_listings", "delivery_fee_paise")
    for column in (
        "kitchen_name",
        "accepted_at",
        "preparing_at",
        "ready_at",
        "completed_at",
        "cancelled_at",
        "rejected_at",
        "rejection_reason",
    ):
        op.drop_column("orders", column)


def downgrade():
    # Restore values before making the legacy columns non-nullable.
    op.add_column("menu_listings", sa.Column("delivery_fee_paise", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE menu_listings AS listing
        SET delivery_fee_paise = CASE WHEN listing.delivery_enabled
            THEN kitchens.delivery_fee_paise ELSE 0 END
        FROM kitchens WHERE listing.kitchen_id = kitchens.id
    """)
    op.alter_column("menu_listings", "delivery_fee_paise", nullable=False)
    op.create_check_constraint(
        "menu_listings_delivery_fee_paise_check", "menu_listings", "delivery_fee_paise >= 0"
    )
    op.add_column("orders", sa.Column("kitchen_name", sa.String(150), nullable=True))
    op.execute("""
        UPDATE orders SET kitchen_name = kitchens.name
        FROM kitchens WHERE orders.kitchen_id = kitchens.id
    """)
    op.alter_column("orders", "kitchen_name", nullable=False)
    for status in ("accepted", "preparing", "ready", "completed", "cancelled", "rejected"):
        op.add_column("orders", sa.Column(f"{status}_at", sa.DateTime(timezone=True)))
        op.execute(
            sa.text(f"""
            UPDATE orders SET {status}_at = (
                SELECT min(created_at) FROM order_events
                WHERE order_events.order_id = orders.id AND order_events.status = :status
            )
        """).bindparams(status=status)
        )
    op.add_column("orders", sa.Column("rejection_reason", sa.String(500)))
    op.execute("""
        UPDATE orders SET rejection_reason = (
            SELECT reason FROM order_events
            WHERE order_events.order_id = orders.id AND order_events.status = 'rejected'
            ORDER BY created_at DESC, id DESC LIMIT 1
        )
    """)

    op.drop_constraint("fk_idempotency_order_customer", "order_idempotency", "foreignkey")
    op.create_foreign_key(
        "order_idempotency_order_id_fkey", "order_idempotency", "orders", ["order_id"], ["id"]
    )
    op.drop_constraint("fk_order_kitchen_society", "orders", "foreignkey")
    op.create_foreign_key("orders_kitchen_id_fkey", "orders", "kitchens", ["kitchen_id"], ["id"])
    op.drop_constraint("fk_listing_dish_kitchen", "menu_listings", "foreignkey")
    op.create_foreign_key(
        "menu_listings_dish_id_fkey", "menu_listings", "dishes", ["dish_id"], ["id"]
    )
    op.drop_constraint("fk_kitchen_tower_society", "kitchens", "foreignkey")
    op.create_foreign_key("kitchens_tower_id_fkey", "kitchens", "towers", ["tower_id"], ["id"])
    op.drop_constraint("fk_membership_tower_society", "society_memberships", "foreignkey")
    op.create_foreign_key(
        "society_memberships_tower_id_fkey", "society_memberships", "towers", ["tower_id"], ["id"]
    )
    op.drop_constraint("uq_orders_id_customer", "orders", "unique")
    op.drop_constraint("uq_dishes_id_kitchen", "dishes", "unique")
    op.drop_constraint("uq_kitchens_id_society", "kitchens", "unique")
    op.drop_constraint("uq_towers_id_society", "towers", "unique")
