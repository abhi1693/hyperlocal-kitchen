"""Runtime boundaries: configuration, transactions, readiness and worker recovery."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from kitchen_core import db
from kitchen_core.settings import Settings
from kitchen_http import application
from kitchen_worker import main as worker
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError


@pytest.fixture(autouse=True)
def runtime_settings(monkeypatch):
    monkeypatch.setattr(application, "get_settings", lambda: SimpleNamespace(cors_origins=[]))


@pytest.mark.parametrize(
    "changes",
    [
        {"database_url": "sqlite:///local"},
        {"redis_url": "https://redis.invalid"},
        {"user_session_ttl_seconds": 1000, "user_session_absolute_ttl_seconds": 500},
        {"user_base_url": "https://example.test?query=yes"},
        {"user_base_url": "https://example.test#fragment"},
        {"user_base_url": "https://user:password@example.test"},
        {"user_base_url": "ftp://example.test"},
        {"user_base_url": "https:///"},
        {"user_base_url": "https://example.test/path"},
        {"user_base_url": "http://example.test"},
        {"oidc_issuer_url": "http://identity.example.test"},
        {
            "environment": "production",
            "cookie_secure": False,
            "user_base_url": "http://localhost",
            "admin_base_url": "http://localhost",
        },
        {
            "environment": "production",
            "cookie_secure": False,
            "user_base_url": None,
            "admin_base_url": None,
            "oidc_issuer_url": None,
        },
        {"user_oidc_client_id": "same", "admin_oidc_client_id": "same"},
        {"admin_required_role": ""},
        {"admin_required_role": "bad role"},
        {"oidc_organization_id": "bad org"},
        {"mobile_redirect_uri": "https://auth/callback"},
        {"mobile_redirect_uri": "hyperlocal-kitchen://other/callback"},
        {"mobile_redirect_uri": "hyperlocal-kitchen://auth/elsewhere"},
        {"mobile_redirect_uri": "hyperlocal-kitchen://auth/callback?x=1"},
        {"mobile_redirect_uri": "hyperlocal-kitchen://auth/callback#x"},
    ],
)
def test_invalid_configuration_rejected(changes):
    values = dict(
        environment="test",
        cookie_secure=True,
        user_base_url="https://user.example.test",
        admin_base_url="https://admin.example.test",
        oidc_issuer_url="https://identity.example.test",
        user_oidc_client_id="resident",
        admin_oidc_client_id="admin",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(values | changes))


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_http_oidc_loopback_is_valid_in_development(host):
    settings = Settings(
        _env_file=None,
        environment="development",
        cookie_secure=False,
        oidc_issuer_url=f"http://{host}",
        user_base_url="http://localhost",
        admin_base_url="http://localhost",
    )
    assert settings.oidc_issuer_url == f"http://{host}"


def test_database_factories_cache_and_disable_expiry(monkeypatch):
    engine = MagicMock()
    create = MagicMock(return_value=engine)
    factory = MagicMock()
    sessionmaker = MagicMock(return_value=factory)
    monkeypatch.setattr(db, "create_engine", create)
    monkeypatch.setattr(db, "sessionmaker", sessionmaker)
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_url="test-database"))
    db.get_engine.cache_clear()
    db.get_session_factory.cache_clear()
    try:
        assert db.get_engine() is db.get_engine() is engine
        assert db.get_session_factory() is db.get_session_factory() is factory
        create.assert_called_once_with("test-database", pool_pre_ping=True)
        sessionmaker.assert_called_once_with(engine, expire_on_commit=False)
    finally:
        db.get_session_factory.cache_clear()
        db.get_engine.cache_clear()


@pytest.mark.parametrize("failure", [False, True])
def test_session_dependency_commits_or_rolls_back(monkeypatch, failure):
    session = MagicMock()
    session.__enter__.return_value = session
    monkeypatch.setattr(db, "get_session_factory", lambda: lambda: session)
    dependency = db.get_session()
    assert next(dependency) is session
    if failure:
        with pytest.raises(RuntimeError, match="write failed"):
            dependency.throw(RuntimeError("write failed"))
        session.rollback.assert_called_once()
        session.commit.assert_not_called()
    else:
        with pytest.raises(StopIteration):
            next(dependency)
        session.commit.assert_called_once()
        session.rollback.assert_not_called()


@pytest.mark.parametrize(
    "revision,status,code",
    [
        ("0008_single_kitchen_owner", 200, None),
        ("0007_kitchen_follows", 503, "migration_required"),
        (None, 503, "migration_required"),
    ],
)
def test_readiness_requires_current_migration(monkeypatch, revision, status, code):
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = (
        revision
    )
    monkeypatch.setattr(application, "get_engine", lambda: engine)
    with TestClient(application.configure_app("Readiness")) as client:
        response = client.get("/ready")
        assert response.status_code == status
        if code:
            assert response.json()["detail"]["code"] == code
        else:
            assert response.json()["status"] == "ready"
        assert client.get("/health").json()["status"] == "ok"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Request-ID"]


def test_readiness_sanitizes_connection_errors(monkeypatch):
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("secret connection parameters")
    monkeypatch.setattr(application, "get_engine", lambda: engine)
    with TestClient(application.configure_app("Readiness")) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "database_unavailable"
        assert "secret" not in response.text


def test_integrity_conflicts_are_sanitized_and_cors_applies(monkeypatch):
    settings = SimpleNamespace(cors_origins=["https://ui.example.test"])
    monkeypatch.setattr(application, "get_settings", lambda: settings)
    app = application.configure_app("Conflicts")

    @app.get("/conflict")
    def conflict():
        raise IntegrityError("private SQL", {}, ValueError("private parameters"))

    with TestClient(app) as client:
        response = client.get("/conflict", headers={"Origin": "https://ui.example.test"})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"
        assert "private" not in response.text
        assert response.headers["access-control-allow-origin"] == "https://ui.example.test"


@pytest.mark.parametrize("has_work", [False, True])
def test_worker_cycle_commits_each_item_and_bounds_work(monkeypatch, has_work):
    commits = []

    @contextmanager
    def begin():
        yield object()
        commits.append("commit")

    factory = SimpleNamespace(begin=begin)
    expire = MagicMock(return_value=int(has_work))
    dispatch = MagicMock(return_value=int(has_work))
    monkeypatch.setattr(worker, "get_session_factory", lambda: factory)
    monkeypatch.setattr(worker, "expire_pending", expire)
    monkeypatch.setattr(worker, "dispatch_notifications", dispatch)
    monkeypatch.setattr(worker.httpx, "Client", MagicMock())
    worker.run_once()
    assert expire.call_count == (100 if has_work else 1)
    assert dispatch.call_count == (20 if has_work else 1)
    assert len(commits) == expire.call_count + dispatch.call_count


@pytest.mark.parametrize("failed_cycle", [False, True])
def test_worker_loop_recovers_without_logging_sensitive_errors(monkeypatch, caplog, failed_cycle):
    class StopWorker(BaseException):
        pass

    run = MagicMock(side_effect=RuntimeError("private tokens") if failed_cycle else None)
    sleep = MagicMock(side_effect=StopWorker)
    monkeypatch.setattr(worker, "run_once", run)
    monkeypatch.setattr(worker.time, "sleep", sleep)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(worker_poll_seconds=3))
    with pytest.raises(StopWorker):
        worker.main()
    run.assert_called_once()
    sleep.assert_called_once_with(3)
    assert "private tokens" not in caplog.text
    assert ("Worker cycle failed" in caplog.text) == failed_cycle
