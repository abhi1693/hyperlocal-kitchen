"""Adding experience preferences preserves existing users and owner associations."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from kitchen_core import catalog
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_experience_migration_preserves_accounts_and_can_be_reapplied(engine):
    schema = "experience_migration_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(url)
    env = {**os.environ, "KITCHEN_DATABASE_URL": url.render_as_string(hide_password=False)}

    def alembic(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    try:
        alembic("upgrade", "0008_single_kitchen_owner")
        metadata = MetaData()
        metadata.reflect(isolated)
        now = datetime.now(UTC)
        community_id, owner_id, customer_id, kitchen_id = (uuid4() for _ in range(4))
        membership_ids = {owner_id: uuid4(), customer_id: uuid4()}
        with isolated.begin() as connection:
            connection.execute(
                metadata.tables["communities"].insert(),
                {
                    "id": community_id,
                    "name": "Legacy community",
                    "city": "Pune",
                    "status": "active",
                    "created_at": now,
                },
            )
            for user_id, subject in ((owner_id, "legacy-owner"), (customer_id, "legacy-customer")):
                connection.execute(
                    metadata.tables["users"].insert(),
                    {
                        "id": user_id,
                        "oidc_subject": subject,
                        "oidc_issuer": "https://identity.test",
                        "is_active": True,
                        "created_at": now,
                    },
                )
                connection.execute(
                    metadata.tables["community_memberships"].insert(),
                    {
                        "id": membership_ids[user_id],
                        "user_id": user_id,
                        "community_id": community_id,
                        "status": "active",
                        "created_at": now,
                    },
                )
            connection.execute(
                metadata.tables["kitchens"].insert(),
                {
                    "id": kitchen_id,
                    "community_id": community_id,
                    "name": "Legacy Kitchen",
                    "status": "pending",
                    "pickup_enabled": True,
                    "delivery_enabled": False,
                    "delivery_fee_paise": 0,
                    "created_at": now,
                },
            )
            connection.execute(
                metadata.tables["kitchen_members"].insert(),
                {"kitchen_id": kitchen_id, "user_id": owner_id, "role": "owner"},
            )
        alembic("upgrade", "head")
        alembic("check")
        upgraded = MetaData()
        upgraded.reflect(isolated)
        users = upgraded.tables["users"]
        with isolated.connect() as connection:
            rows = dict(connection.execute(select(users.c.id, users.c.preferred_mode)).all())
            assert rows == {owner_id: None, customer_id: None}
            actual = dict(
                connection.execute(
                    select(
                        upgraded.tables["community_memberships"].c.user_id,
                        upgraded.tables["community_memberships"].c.id,
                    )
                ).all()
            )
            assert actual == membership_ids
        with Session(isolated) as session:
            owner = catalog.experience_state(session, owner_id)
            assert owner.mode == "kitchen_owner" and owner.owned_kitchen.id == kitchen_id
            assert catalog.experience_state(session, customer_id).mode is None
        constraints = {item["name"] for item in inspect(isolated).get_check_constraints("users")}
        assert "users_preferred_mode_check" in constraints
        for mode in ("customer", "kitchen_owner", None):
            with isolated.begin() as connection:
                connection.execute(
                    users.update().where(users.c.id == owner_id).values(preferred_mode=mode)
                )
        with pytest.raises(IntegrityError), isolated.begin() as connection:
            connection.execute(
                users.update().where(users.c.id == owner_id).values(preferred_mode="admin")
            )
        alembic("downgrade", "0008_single_kitchen_owner")
        assert "preferred_mode" not in {
            item["name"] for item in inspect(isolated).get_columns("users")
        }
        alembic("upgrade", "head")
        alembic("check")
        with Session(isolated) as session:
            assert catalog.experience_state(session, owner_id).owned_kitchen.id == kitchen_id
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
