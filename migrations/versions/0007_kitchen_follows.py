"""Add kitchen follows with an opt-in menu notification preference."""

import sqlalchemy as sa
from alembic import op

revision = "0007_kitchen_follows"
down_revision = "0006_kitchen_availability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kitchen_follows",
        sa.Column("kitchen_id", sa.Uuid(), sa.ForeignKey("kitchens.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notify_new_menu", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("kitchen_id", "user_id"),
    )
    op.create_index("ix_kitchen_follows_user_id", "kitchen_follows", ["user_id"])


def downgrade():
    op.drop_table("kitchen_follows")
