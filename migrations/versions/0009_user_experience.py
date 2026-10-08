"""Store the selected app experience without assigning kitchen permissions."""

import sqlalchemy as sa
from alembic import op

revision = "0009_user_experience"
down_revision = "0008_single_kitchen_owner"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("preferred_mode", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "users_preferred_mode_check",
        "users",
        "preferred_mode IS NULL OR preferred_mode IN ('customer','kitchen_owner')",
    )


def downgrade():
    op.drop_constraint("users_preferred_mode_check", "users", type_="check")
    op.drop_column("users", "preferred_mode")
