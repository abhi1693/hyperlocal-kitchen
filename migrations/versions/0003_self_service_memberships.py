"""Make resident memberships self-service and remove invitations."""

import sqlalchemy as sa
from alembic import op

revision = "0003_self_service_memberships"
down_revision = "0002_mvp_relationships"
branch_labels = None
depends_on = None


def upgrade():
    # Existing residents keep their accounts and addresses; waiting joins become active.
    op.execute("UPDATE society_memberships SET status = 'active' WHERE status = 'pending'")
    op.drop_constraint("society_memberships_status_check", "society_memberships", "check")
    op.create_check_constraint(
        "society_memberships_status_check",
        "society_memberships",
        "status IN ('active','suspended')",
    )
    op.alter_column(
        "society_memberships",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=sa.text("'active'"),
    )
    op.drop_index("ix_society_invitations_society_id", table_name="society_invitations")
    op.drop_table("society_invitations")


def downgrade():
    # Recreate the former structure; deleted invitation contents cannot be restored.
    op.create_table(
        "society_invitations",
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(
        "ix_society_invitations_society_id", "society_invitations", ["society_id"], unique=False
    )
    op.alter_column(
        "society_memberships",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=None,
    )
    op.drop_constraint("society_memberships_status_check", "society_memberships", "check")
    op.create_check_constraint(
        "society_memberships_status_check",
        "society_memberships",
        "status IN ('pending','active','suspended')",
    )
