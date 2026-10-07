"""Generalize communities and introduce listing pickup points without rewriting history."""

import sqlalchemy as sa
from alembic import op

revision = "0005_communities_pickup"
down_revision = "0004_contact_phones"
branch_labels = None
depends_on = None


def upgrade():
    for old, new in (
        ("societies", "communities"),
        ("towers", "community_zones"),
        ("society_memberships", "community_memberships"),
    ):
        op.rename_table(old, new)
    for table in ("community_zones", "community_memberships", "kitchens", "orders"):
        op.alter_column(table, "society_id", new_column_name="community_id")
    for table in ("community_memberships", "kitchens"):
        op.alter_column(table, "tower_id", new_column_name="zone_id", nullable=True)
        op.alter_column(
            table, "flat", new_column_name="address_label", type_=sa.String(250), nullable=True
        )
    # PostgreSQL updates FK targets and expressions during renames. Keep the
    # constraint/index names consistent with the new ORM for future migrations.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("communities", "community_zones", "community_memberships", "kitchens", "orders"):
        constraints = [
            *inspector.get_foreign_keys(table),
            *inspector.get_unique_constraints(table),
            *inspector.get_check_constraints(table),
            inspector.get_pk_constraint(table),
        ]
        for constraint in constraints:
            old = constraint["name"]
            new = (
                old.replace("societies", "communities")
                .replace("society", "community")
                .replace("towers", "zones")
                .replace("tower", "zone")
            )
            if old != new:
                op.execute(sa.text(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"'))
        for index in inspector.get_indexes(table):
            if index.get("duplicates_constraint"):
                continue
            old = index["name"]
            new = old.replace("society", "community").replace("towers", "community_zones")
            if old != new:
                op.execute(sa.text(f'ALTER INDEX "{old}" RENAME TO "{new}"'))
    for column in ("address", "postal_code"):
        op.alter_column("communities", column, nullable=True)
    op.add_column(
        "communities",
        sa.Column("type", sa.String(30), nullable=False, server_default="residential_society"),
    )
    op.create_check_constraint(
        "communities_type_check",
        "communities",
        "type IN ('residential_society','cantonment','housing_colony',"
        "'university','corporate_campus','gated_community','other')",
    )
    op.add_column("community_zones", sa.Column("parent_zone_id", sa.Uuid(), nullable=True))
    op.add_column(
        "community_zones",
        sa.Column("zone_type", sa.String(20), nullable=False, server_default="tower"),
    )
    op.alter_column("community_zones", "zone_type", server_default="other")
    op.add_column(
        "community_zones",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_check_constraint(
        "community_zones_type_check",
        "community_zones",
        "zone_type IN ('tower','area','hostel','block','other')",
    )
    op.create_check_constraint(
        "zone_not_self_parent", "community_zones", "parent_zone_id IS NULL OR parent_zone_id != id"
    )
    op.create_foreign_key(
        "fk_zone_parent_community",
        "community_zones",
        "community_zones",
        ["parent_zone_id", "community_id"],
        ["id", "community_id"],
    )
    op.create_table(
        "pickup_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("community_id", sa.Uuid(), sa.ForeignKey("communities.id"), nullable=False),
        sa.Column("kitchen_id", sa.Uuid(), nullable=True),
        sa.Column("zone_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("address_label", sa.String(250), nullable=False),
        sa.Column("instructions", sa.String(1000), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("id", "community_id", name="uq_pickup_points_id_community"),
        sa.ForeignKeyConstraint(
            ["zone_id", "community_id"],
            ["community_zones.id", "community_zones.community_id"],
            name="fk_pickup_zone_community",
        ),
        sa.ForeignKeyConstraint(
            ["kitchen_id", "community_id"],
            ["kitchens.id", "kitchens.community_id"],
            name="fk_pickup_kitchen_community",
        ),
    )
    op.create_index("ix_pickup_points_community_id", "pickup_points", ["community_id"])
    op.create_index("ix_pickup_points_kitchen_id", "pickup_points", ["kitchen_id"])
    op.create_unique_constraint("uq_listings_id_kitchen", "menu_listings", ["id", "kitchen_id"])
    op.create_table(
        "listing_pickup_points",
        sa.Column("listing_id", sa.Uuid(), primary_key=True),
        sa.Column("pickup_point_id", sa.Uuid(), primary_key=True),
        sa.Column("kitchen_id", sa.Uuid(), nullable=False),
        sa.Column("community_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id", "kitchen_id"],
            ["menu_listings.id", "menu_listings.kitchen_id"],
            name="fk_listing_pickup_listing",
        ),
        sa.ForeignKeyConstraint(
            ["kitchen_id", "community_id"],
            ["kitchens.id", "kitchens.community_id"],
            name="fk_listing_pickup_kitchen",
        ),
        sa.ForeignKeyConstraint(
            ["pickup_point_id", "community_id"],
            ["pickup_points.id", "pickup_points.community_id"],
            name="fk_listing_pickup_point",
        ),
    )
    # Every existing kitchen address becomes a pickup point. IDs are independent
    # point identifiers even though using the kitchen UUID avoids extension needs.
    op.execute("""
        INSERT INTO pickup_points (id, created_at, community_id, kitchen_id, zone_id,
                                   name, address_label, active)
        SELECT id, created_at, community_id, id, zone_id, name, address_label, true FROM kitchens
    """)
    op.execute("""
        INSERT INTO listing_pickup_points (listing_id, pickup_point_id, kitchen_id, community_id)
        SELECT l.id, k.id, k.id, k.community_id FROM menu_listings l
        JOIN kitchens k ON k.id = l.kitchen_id WHERE l.pickup_enabled
    """)
    op.add_column("orders", sa.Column("pickup_point_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("fulfillment_snapshot", sa.JSON(), nullable=True))
    for column in ("pickup_address", "delivery_address"):
        op.alter_column("orders", column, nullable=True)
    op.create_foreign_key(
        "fk_order_pickup_community",
        "orders",
        "pickup_points",
        ["pickup_point_id", "community_id"],
        ["id", "community_id"],
    )
    op.create_check_constraint(
        "order_delivery_no_pickup",
        "orders",
        "fulfillment_type = 'pickup' OR pickup_point_id IS NULL",
    )
    # Historical JSON stays byte-for-byte untouched; serialization understands v1.
    op.execute("UPDATE orders SET pickup_point_id = kitchen_id WHERE fulfillment_type = 'pickup'")
    op.add_column(
        "order_idempotency",
        sa.Column("hash_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("order_idempotency", "hash_version", server_default="2")


def downgrade():
    raise RuntimeError(
        "This migration preserves legacy history but new community and pickup data cannot be "
        "represented by the society schema. Restore a pre-migration database backup to roll back."
    )
