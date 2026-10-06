"""Allow delivery contact phones to be shared across distinct identities."""

from alembic import op

revision = "0004_contact_phones"
down_revision = "0003_self_service_memberships"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("users_phone_key", "users", type_="unique")


def downgrade():
    # Contact sharing is valid at this revision. Refuse an incompatible rollback
    # without merging accounts, deleting users or changing their delivery contacts.
    op.execute("LOCK TABLE users IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT phone FROM users
                WHERE phone IS NOT NULL
                GROUP BY phone HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: users share delivery contact phones. '
                    'Resolve the contacts explicitly before restoring uniqueness.'
                    USING ERRCODE = '23505';
            END IF;
        END $$
    """)
    op.create_unique_constraint("users_phone_key", "users", ["phone"])
