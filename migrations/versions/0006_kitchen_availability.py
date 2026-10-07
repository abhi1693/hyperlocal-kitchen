"""Add immediate kitchen pause/resume without changing existing availability."""

import sqlalchemy as sa
from alembic import op

revision = "0006_kitchen_availability"
down_revision = "0005_communities_pickup"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "kitchens",
        sa.Column("is_accepting_orders", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("kitchens", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("kitchens", sa.Column("pause_reason", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("kitchens", "pause_reason")
    op.drop_column("kitchens", "paused_at")
    op.drop_column("kitchens", "is_accepting_orders")
