"""Provider configuration and mobile handoff storage failure responses."""

import json
from unittest.mock import MagicMock

import pytest
from kitchen_core import auth, oidc
from kitchen_core.settings import get_settings
from redis.exceptions import RedisError
from test_auth import auth_configuration as auth_configuration
from test_auth import oidc_admin_client as oidc_admin_client
from test_auth import provider as provider
from test_auth import redis_store as redis_store


def test_auth_config_lists_configured_social_providers(client, monkeypatch):
    monkeypatch.setenv("KITCHEN_OIDC_GOOGLE_IDP_ID", "google-id")
    monkeypatch.setenv("KITCHEN_OIDC_GITHUB_IDP_ID", "github-id")
    get_settings.cache_clear()
    assert client.get("/api/v1/auth/config").json() == {
        "enabled": True,
        "providers": ["google", "github"],
        "phone_login_enabled": False,
    }


@pytest.mark.parametrize("case", ["invalid", "expired", "malformed", "policy", "missing_challenge"])
def test_mobile_login_rejects_invalid_start_records(client, provider, redis_store, case):
    request_id = "m" * 43
    if case != "expired":
        record = {"policy": auth.policy_key("user"), "challenge": "c" * 43}
        if case == "policy":
            record["policy"] = "old"
        if case == "missing_challenge":
            record.pop("challenge")
        raw = "bad-json" if case == "malformed" else json.dumps(record)
        redis_store.set(auth.key("user", "mobile", request_id), raw, ex=60)
    if case == "invalid":
        request_id = "invalid"
    response = client.get(
        "/api/v1/auth/login", params={"mobile_request": request_id}, follow_redirects=False
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "login_unavailable"


def test_admin_login_rejects_mobile_request(oidc_admin_client, provider):
    response = oidc_admin_client.get(
        "/api/v1/auth/login", params={"mobile_request": "m" * 43}, follow_redirects=False
    )
    assert response.status_code == 503


def test_mobile_start_reports_unavailable_session_store(client, monkeypatch):
    redis = MagicMock()
    redis.set.side_effect = RedisError("private connection information")
    monkeypatch.setattr(auth, "get_redis", lambda: redis)
    response = client.post("/api/v1/auth/mobile/start", json={"code_challenge": "c" * 43})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "login_unavailable"
    assert "private" not in response.text


@pytest.mark.parametrize("case", ["redis", "malformed", "invalid_record", "invalid_account"])
def test_mobile_exchange_sanitizes_storage_and_identity_errors(client, monkeypatch, case):
    verifier, code = "v" * 43, "c" * 43
    record = {"policy": auth.policy_key("user")}
    handoff = {"challenge": auth.pkce_challenge(verifier), "record": record}
    raw = json.dumps(handoff).encode()
    if case == "malformed":
        raw = b"bad-json"
    if case == "invalid_record":
        raw = b"{}"
    redis = MagicMock()
    redis.get.return_value = redis.getdel.return_value = raw
    if case == "redis":
        redis.get.side_effect = RedisError("private connection information")
    if case == "invalid_account":
        monkeypatch.setattr(
            auth, "save_user", MagicMock(side_effect=oidc.OIDCError("Account unavailable"))
        )
    monkeypatch.setattr(auth, "get_redis", lambda: redis)
    response = client.post(
        "/api/v1/auth/mobile/exchange", json={"code": code, "code_verifier": verifier}
    )
    assert response.status_code == (503 if case == "redis" else 401)
    assert response.json()["detail"]["code"] == (
        "sessions_unavailable" if case == "redis" else "invalid_handoff"
    )
    assert "private" not in response.text
