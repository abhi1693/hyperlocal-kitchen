import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("KITCHEN_ENVIRONMENT", "test")
os.environ.setdefault("KITCHEN_REDIS_URL", "redis://127.0.0.1:56379/15")

from kitchen_core.db import get_session
from kitchen_core.models import Base
from kitchen_core.settings import get_settings


@pytest.fixture(autouse=True)
def settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("KITCHEN_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set KITCHEN_TEST_DATABASE_URL to a disposable PostgreSQL *_test database")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Integration database name must end with _test")
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    with engine.begin() as connection:
        tables = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        from sqlalchemy import text

        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session
        session.rollback()


def override_session(app: FastAPI, session_factory):
    def dependency():
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_session] = dependency


@pytest.fixture
def client(session_factory):
    from kitchen_api.main import create_app

    app = create_app()
    override_session(app, session_factory)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin_client(session_factory):
    from kitchen_admin_api.main import create_app
    from kitchen_core.auth_schemas import AdminPrincipal
    from kitchen_http.auth import require_admin

    app = create_app()
    override_session(app, session_factory)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        subject="test-admin",
        issuer="https://identity.example.test",
        organization_id="test-org",
        roles=["platform_admin"],
        expires_at=4_000_000_000,
        csrf_token="test-csrf",
    )
    with TestClient(app) as client:
        yield client
