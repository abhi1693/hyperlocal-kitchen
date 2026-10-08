"""Limit each user to ownership of one kitchen across all communities."""

import sqlalchemy as sa
from alembic import op

revision = "0008_single_kitchen_owner"
down_revision = "0007_kitchen_follows"
branch_labels = None
depends_on = None


def upgrade():
    # Existing duplicate ownership must be resolved explicitly before upgrading.
    op.create_index(
        "uq_kitchen_members_owner_user_id",
        "kitchen_members",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
        sqlite_where=sa.text("role = 'owner'"),
    )


def downgrade():
    op.drop_index("uq_kitchen_members_owner_user_id", table_name="kitchen_members")
