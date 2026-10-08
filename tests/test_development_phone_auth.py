"""Explicit local phone bypass: account continuity and production isolation."""

import hashlib
import json
import time
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from kitchen_core import auth, oidc
from kitchen_core.models import Device, User
from kitchen_core.settings import Settings, get_settings
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from test_auth import oidc_admin_client as oidc_admin_client
from test_auth import redis_store as redis_store

PHONE = "+919876543210"


@pytest.fixture(autouse=True)
def development_phone_configuration(monkeypatch):
    redis_factory = auth.get_redis
    for field, value in {
        "ENVIRONMENT": "development",
        "DEVELOPMENT_PHONE_LOGIN": "true",
        "OIDC_ISSUER_URL": "",
        "OIDC_ORGANIZATION_ID": "",
        "USER_OIDC_CLIENT_ID": "",
        "ADMIN_OIDC_CLIENT_ID": "",
        "USER_BASE_URL": "",
        "ADMIN_BASE_URL": "",
        "COOKIE_SECURE": "true",
    }.items():
        monkeypatch.setenv("KITCHEN_" + field, value)
    get_settings.cache_clear()
    redis_factory.cache_clear()
    yield
    get_settings.cache_clear()
    redis_factory.cache_clear()


def sign_in(client, phone=PHONE):
    response = client.post("/api/v1/auth/mobile/phone", json={"phone": phone})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["session_token"]) == 43
    assert result["expires_at"] > int(time.time())
    return result


def test_phone_sign_in_is_opt_in_and_admin_never_enables_it(client, oidc_admin_client):
    assert client.get("/api/v1/auth/config").json() == {
        "enabled": True,
        "providers": [],
        "phone_login_enabled": True,
    }
    assert oidc_admin_client.get("/api/v1/auth/config").json() == {
        "enabled": False,
        "providers": [],
        "phone_login_enabled": False,
    }
    assert (
        oidc_admin_client.post("/api/v1/auth/mobile/phone", json={"phone": PHONE}).status_code
        == 404
    )


@pytest.mark.parametrize(
    "environment,enabled",
    [("development", False), ("test", True), ("production", True)],
)
def test_disabled_phone_sign_in_never_creates_an_account(
    client, session, monkeypatch, environment, enabled
):
    monkeypatch.setenv("KITCHEN_ENVIRONMENT", environment)
    monkeypatch.setenv("KITCHEN_DEVELOPMENT_PHONE_LOGIN", str(enabled).lower())
    get_settings.cache_clear()
    config = client.get("/api/v1/auth/config").json()
    assert config["phone_login_enabled"] is False
    assert config["enabled"] is False
    response = client.post("/api/v1/auth/mobile/phone", json={"phone": PHONE})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_not_configured"
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_phone_authentication_is_disabled_when_flag_is_absent(monkeypatch):
    monkeypatch.delenv("KITCHEN_DEVELOPMENT_PHONE_LOGIN")
    assert Settings(_env_file=None).development_phone_login is False


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"phone": "9876543210"},
        {"phone": "+012345678"},
        {"phone": "+1234567"},
        {"phone": "+1234567890123456"},
        {"phone": "+91 9876543210"},
        {"phone": "+９１９８７６５４３２１０"},
        {"phone": PHONE + "\n"},
        {"phone": 919876543210},
        {"phone": PHONE, "name": "Untrusted"},
        {"phone": PHONE, "roles": ["platform_admin"]},
        {"phone": PHONE, "user_id": "arbitrary-account"},
        {"phone": PHONE, "verified": True},
    ],
)
def test_phone_request_accepts_only_a_normalized_phone(client, session, body):
    assert client.post("/api/v1/auth/mobile/phone", json=body).status_code == 422
    assert session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("phone", ["+12345678", "+123456789012345"])
def test_phone_boundaries_are_accepted(client, redis_store, phone):
    assert sign_in(client, phone)["user"]["phone"] == phone


def test_phone_sign_in_reuses_account_with_a_local_unverified_identity(
    client, redis_store, session
):
    first = sign_in(client)
    second = sign_in(client)
    assert first["session_token"] != second["session_token"]
    assert first["user"] == second["user"]
    assert session.scalar(select(func.count()).select_from(User)) == 1
    user = session.get(User, UUID(first["user"]["id"]))
    assert user.oidc_issuer == "urn:kitchen:development:phone"
    assert user.oidc_subject == "development-phone:" + hashlib.sha256(PHONE.encode()).hexdigest()
    record = auth.load_session("user", first["session_token"])
    assert record["issuer"] == user.oidc_issuer
    assert record["phone"] == PHONE
    assert "phone_number_verified" not in record and "roles" not in record
    assert record["transport"] == "bearer"
    assert client.cookies.get(auth.cookie_name("user", "session")) is None
    other = sign_in(client, "+919876543211")
    assert other["user"]["id"] != first["user"]["id"]


def test_phone_session_renews_and_logout_revokes_its_device(client, redis_store, session):
    result = sign_in(client)
    token = result["session_token"]
    headers = {"Authorization": "Bearer " + token}
    session_key = auth.key("user", "session", token)
    record = json.loads(redis_store.get(session_key))
    record["renewed_at"] = int(time.time()) - 4000
    redis_store.set(session_key, json.dumps(record), ex=3600)
    identity = client.get("/api/v1/auth/me", headers=headers)
    assert identity.status_code == 200
    assert identity.json()["id"] == result["user"]["id"]
    renewed = auth.load_session("user", token)
    assert renewed["renewed_at"] > record["renewed_at"]
    assert renewed["expires_at"] <= renewed["absolute_expires_at"]
    device_result = client.post(
        "/api/v1/devices",
        json={"push_token": "ExpoPushToken[development-phone]", "platform": "android"},
        headers=headers,
    )
    assert device_result.status_code == 200
    user_id = UUID(result["user"]["id"])
    assert auth.device_session_active(session_key, user_id)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert not redis_store.exists(session_key)
    assert not auth.device_session_active(session_key, user_id)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    device = session.get(Device, UUID(device_result.json()["id"]))
    assert device.is_active is False


def test_phone_session_cannot_access_admin_or_cookie_transport(
    client, oidc_admin_client, redis_store
):
    token = sign_in(client)["session_token"]
    headers = {"Authorization": "Bearer " + token}
    assert oidc_admin_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    client.cookies.set(auth.cookie_name("user", "session"), token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_suspended_local_account_cannot_sign_in_again(client, redis_store, session):
    result = sign_in(client)
    user = session.get(User, UUID(result["user"]["id"]))
    user.is_active = False
    session.commit()
    response = client.post("/api/v1/auth/mobile/phone", json={"phone": PHONE})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "account_unavailable"
    headers = {"Authorization": "Bearer " + result["session_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_matching_zitadel_contact_does_not_merge_accounts(client, redis_store, session):
    existing = User(
        oidc_subject="zitadel-resident", oidc_issuer="https://identity.test", phone=PHONE
    )
    session.add(existing)
    session.commit()
    result = sign_in(client)
    assert UUID(result["user"]["id"]) != existing.id
    assert session.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.parametrize("failure", ["redis", "database", "identity"])
def test_phone_authentication_sanitizes_storage_and_identity_errors(
    client, session, monkeypatch, failure
):
    if failure == "redis":
        store = MagicMock()
        store.set.side_effect = RedisError("private credential and connection")
        monkeypatch.setattr(auth, "get_redis", lambda: store)
    else:
        error = (
            SQLAlchemyError("private database credential")
            if failure == "database"
            else oidc.OIDCError("private unavailable account")
        )
        monkeypatch.setattr(auth, "save_user", MagicMock(side_effect=error))
    response = client.post("/api/v1/auth/mobile/phone", json={"phone": PHONE})
    assert response.status_code == (401 if failure == "identity" else 503)
    assert "private" not in response.text
    assert session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("environment", ["test", "production"])
def test_development_phone_session_policy_does_not_survive_environment_change(
    client, redis_store, monkeypatch, environment
):
    # An independently configured provider must not make the local bypass session valid.
    monkeypatch.setenv("KITCHEN_OIDC_ISSUER_URL", "https://identity.example.test")
    monkeypatch.setenv("KITCHEN_OIDC_ORGANIZATION_ID", "org")
    monkeypatch.setenv("KITCHEN_USER_OIDC_CLIENT_ID", "resident")
    monkeypatch.setenv("KITCHEN_USER_BASE_URL", "https://user.example.test")
    get_settings.cache_clear()
    token = sign_in(client)["session_token"]
    monkeypatch.setenv("KITCHEN_ENVIRONMENT", environment)
    get_settings.cache_clear()
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("provider_enabled", [False, True])
def test_disabling_phone_bypass_invalidates_its_session(
    client, redis_store, monkeypatch, provider_enabled
):
    if provider_enabled:
        monkeypatch.setenv("KITCHEN_OIDC_ISSUER_URL", "https://identity.example.test")
        monkeypatch.setenv("KITCHEN_OIDC_ORGANIZATION_ID", "org")
        monkeypatch.setenv("KITCHEN_USER_OIDC_CLIENT_ID", "resident")
        monkeypatch.setenv("KITCHEN_USER_BASE_URL", "https://user.example.test")
        get_settings.cache_clear()
    token = sign_in(client)["session_token"]
    monkeypatch.setenv("KITCHEN_DEVELOPMENT_PHONE_LOGIN", "false")
    get_settings.cache_clear()
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == (
        401 if provider_enabled else 503
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/login", None),
        ("GET", "/callback", None),
        ("POST", "/mobile/start", {"code_challenge": "c" * 43}),
        ("POST", "/mobile/exchange", {"code": "c" * 43, "code_verifier": "v" * 43}),
    ],
)
def test_phone_bypass_does_not_enable_unconfigured_hosted_oidc(client, method, path, body):
    response = client.request(method, "/api/v1/auth" + path, json=body)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_not_configured"
