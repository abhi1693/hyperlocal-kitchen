"""Check that commit validation cannot inherit application service destinations."""

from pathlib import Path
from runpy import run_path

import pytest

check_backend = run_path(str(Path(__file__).parents[1] / "scripts/check_backend.py"))
test_environment = check_backend["test_environment"]
test_environment.__test__ = False


@pytest.mark.parametrize(
    ("database", "redis"),
    [
        ("postgresql+psycopg://ci:ci@localhost/kitchen", "redis://localhost/15"),
        ("sqlite:///kitchen_test", "redis://localhost/15"),
        ("postgresql+psycopg://ci:ci@localhost/kitchen_test", "redis://localhost/0"),
        ("postgresql+psycopg://ci:ci@localhost/kitchen_test", "https://localhost/15"),
    ],
)
def test_commit_checks_reject_non_test_destinations(database, redis):
    with pytest.raises(ValueError):
        test_environment(database, redis)


def test_commit_checks_override_application_settings(monkeypatch):
    monkeypatch.setenv("KITCHEN_ENVIRONMENT", "production")
    monkeypatch.setenv("KITCHEN_DATABASE_URL", "postgresql+psycopg://app@localhost/application")
    monkeypatch.setenv("KITCHEN_REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("KITCHEN_COOKIE_SECURE", "false")
    monkeypatch.setenv("KITCHEN_ADMIN_BASE_URL", "http://localhost:3001")
    database = "postgresql+psycopg://ci:ci@localhost/kitchen_test"
    redis = "redis://localhost/15"
    env = test_environment(database, redis)
    assert env["KITCHEN_ENVIRONMENT"] == "test"
    assert env["KITCHEN_DATABASE_URL"] == env["KITCHEN_TEST_DATABASE_URL"] == database
    assert env["KITCHEN_REDIS_URL"] == redis
    assert env["KITCHEN_COOKIE_SECURE"] == "true"
    assert env["KITCHEN_ADMIN_BASE_URL"] == "https://admin.example.test"
