"""Revocation, renewal races and malformed session/authorization records."""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from kitchen_core import auth, oidc
from kitchen_core.auth_schemas import AdminPrincipal
from kitchen_core.errors import DomainError
from kitchen_core.settings import Settings
from kitchen_http import auth as http_auth
from redis.exceptions import RedisError
from starlette.requests import Request


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="test",
        cookie_secure=True,
        oidc_issuer_url="https://identity.example.test",
        oidc_organization_id="org",
        user_base_url="https://user.example.test",
        admin_base_url="https://admin.example.test",
        user_oidc_client_id="resident",
        admin_oidc_client_id="admin",
        user_oidc_client_secret="private",
        admin_oidc_client_secret="private-admin",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(http_auth, "get_settings", lambda: settings)
    return settings


def request(method="GET", headers=None, cookies=None):
    headers = dict(headers or {})
    if cookies:
        headers["cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
    return Request(
        {
            "type": "http",
            "method": method,
            "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        }
    )


@pytest.fixture
def session_record():
    now = int(time.time())
    return {
        "policy": auth.policy_key("user"),
        "user_id": str(uuid4()),
        "subject": "resident",
        "issuer": "https://identity.example.test",
        "organization_id": "org",
        "expires_at": now + 1000,
        "absolute_expires_at": now + 2000,
        "renewed_at": now - 4000,
        "csrf_token": "c" * 43,
        "transport": "cookie",
    }


@pytest.mark.parametrize(
    "claims,info,expected",
    [
        ({}, {}, []),
        ({"roles": []}, {}, []),
        ({"roles": {"admin": {"org": "domain"}}}, {}, ["admin"]),
        ({"roles": {"admin": {"org": "domain"}}}, {"roles": {"admin": {"other": "domain"}}}, []),
        ({"roles": {1: {"org": "domain"}}}, {}, []),
        ({"roles": {"admin": []}}, {}, []),
        ({"roles": {"admin": {"org": 1}}}, {}, []),
        ({"roles": {"admin": {1: "domain"}}}, {}, []),
    ],
)
def test_role_assertions_require_consistent_typed_org_grants(
    configured_settings, claims, info, expected
):
    configured_settings.oidc_roles_claim = "roles"
    assert auth.verified_roles(claims, info) == expected


def test_auth_start_rejects_unconfigured_identity_provider():
    with pytest.raises(oidc.OIDCError, match="Identity provider is not configured"):
        auth.start("user", provider="google")


@pytest.mark.parametrize("kind,expires,roles", [("user", 1, {}), ("admin", 9999999999, {})])
def test_service_identity_rejects_expiry_and_missing_admin_role(monkeypatch, kind, expires, roles):
    monkeypatch.setattr(auth, "discovery", lambda kind: {})
    monkeypatch.setattr(
        oidc,
        "identity",
        lambda *a, **kw: {"expires_at": expires, "id_claims": roles, "userinfo_claims": {}},
    )
    with pytest.raises(oidc.OIDCError):
        auth.identity(kind, {}, "code")


def test_create_session_rejects_expired_identity():
    with pytest.raises(oidc.OIDCError, match="Expired identity"):
        auth.create_session("user", {"expires_at": 1})


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"broken-json", "invalid_session"),
        (None, "invalid_session"),
        (b"[]", "invalid_session"),
        (RedisError("offline"), "sessions_unavailable"),
    ],
)
def test_session_load_sanitizes_malformed_storage(monkeypatch, raw, code):
    redis = MagicMock()
    if isinstance(raw, Exception):
        redis.get.side_effect = raw
    else:
        redis.get.return_value = raw
    monkeypatch.setattr(auth, "get_redis", lambda: redis)
    with pytest.raises(DomainError) as error:
        auth.load_session("user", "s" * 43)
    assert error.value.code == code


@pytest.mark.parametrize("change", [{"transport": "bearer"}, {"user_id": "invalid"}])
def test_resident_session_rejects_wrong_transport_or_invalid_identity(
    monkeypatch, session_record, change
):
    session_record.update(change)
    monkeypatch.setattr(auth, "load_session", lambda *a: session_record)
    with pytest.raises(DomainError, match="Please sign in again"):
        auth.resident_session("s" * 43, transport="cookie")


@pytest.mark.parametrize("failure", ["missing", "expired", "revoked", "redis"])
def test_resident_renewal_cannot_recreate_revoked_or_invalid_sessions(
    monkeypatch, session_record, failure
):
    monkeypatch.setattr(auth, "load_session", lambda *a: dict(session_record))
    store = MagicMock()
    current = dict(session_record)
    if failure == "expired":
        current["expires_at"] = 1
    store.get.return_value = None if failure == "missing" else json.dumps(current).encode()
    store.eval.return_value = None
    if failure == "redis":
        store.get.side_effect = RedisError("offline")
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    with pytest.raises(DomainError) as error:
        auth.renew_resident_session("s" * 43)
    assert error.value.code == ("sessions_unavailable" if failure == "redis" else "invalid_session")


def test_resident_renewal_caps_idle_expiry_at_absolute_lifetime(monkeypatch, session_record):
    monkeypatch.setattr(auth, "load_session", lambda *a: dict(session_record))
    store = MagicMock()
    store.get.return_value = json.dumps(session_record).encode()
    store.eval.side_effect = lambda script, count, key, previous, renewed, ttl: renewed.encode()
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    result = auth.renew_resident_session("s" * 43)
    assert result["expires_at"] == session_record["absolute_expires_at"]
    assert result["renewed_at"] >= session_record["renewed_at"] + 4000
    assert store.eval.call_args.args[0] == auth.RENEW_SESSION


@pytest.mark.parametrize(
    "key,raw", [("wrong-prefix", None), ("kitchen:user:session:key", b"bad-json")]
)
def test_invalid_device_session_is_inactive(monkeypatch, key, raw):
    store = MagicMock()
    store.get.return_value = raw
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    assert not auth.device_session_active(key, uuid4())


def test_revocation_rejects_store_failure_and_ignores_invalid_token(monkeypatch):
    store = MagicMock()
    store.delete.side_effect = RedisError("offline")
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    session = MagicMock()
    auth.revoke_session(session, "user", "invalid")
    store.delete.assert_not_called()
    with pytest.raises(DomainError) as error:
        auth.revoke_session(session, "user", "s" * 43)
    assert error.value.code == "sessions_unavailable"
    session.execute.assert_not_called()


@pytest.mark.parametrize(
    "kind,authorization",
    [
        ("admin", "Bearer token"),
        ("user", "Basic token"),
        ("user", "Bearer"),
        ("user", "Bearer a b"),
    ],
)
def test_invalid_authorization_header_rejected(kind, authorization):
    with pytest.raises(DomainError):
        http_auth.request_token(request(headers={"Authorization": authorization}), kind)


@pytest.mark.parametrize(
    "record,headers",
    [
        ({"csrf_token": 1}, {}),
        ({"csrf_token": "invalid"}, {}),
        (
            {"csrf_token": "c" * 43},
            {"Origin": "https://user.example.test", "X-CSRF-Token": "invalid"},
        ),
        (
            {"csrf_token": "c" * 43},
            {"Origin": "https://user.example.test", "X-CSRF-Token": "d" * 43},
        ),
    ],
)
def test_csrf_requires_well_formed_matching_tokens(record, headers):
    with pytest.raises(DomainError) as error:
        http_auth.validate_csrf(request(headers=headers), "user", record)
    assert error.value.code == "invalid_csrf"


@pytest.mark.parametrize(
    "user",
    [
        None,
        SimpleNamespace(is_active=False),
        SimpleNamespace(is_active=True, oidc_subject="wrong", oidc_issuer="issuer"),
        SimpleNamespace(is_active=True, oidc_subject="subject", oidc_issuer="wrong"),
    ],
)
def test_authenticated_user_must_match_active_identity(user):
    session = MagicMock()
    session.get.return_value = user
    resident = SimpleNamespace(user_id=uuid4(), subject="subject", issuer="issuer")
    with pytest.raises(DomainError) as error:
        http_auth.require_user(session, resident)
    assert error.value.code == "invalid_session"


@pytest.fixture
def admin_record():
    return {
        "subject": "admin",
        "issuer": "https://identity.example.test",
        "organization_id": "org",
        "roles": ["platform_admin"],
        "expires_at": int(time.time()) + 1000,
        "csrf_token": "c" * 43,
    }


@pytest.mark.parametrize(
    "case", ["invalid", "role", "registration", "inactive", "issuer", "materialize"]
)
def test_admin_session_validates_roles_and_materializes_only_valid_accounts(
    monkeypatch, admin_record, case
):
    record = dict(admin_record)
    if case == "invalid":
        record["subject"] = None
    if case == "role":
        record["roles"] = []
    monkeypatch.setattr(auth, "load_session", lambda *a: record)
    session = MagicMock()
    user = SimpleNamespace(is_active=case != "inactive", oidc_issuer=record["issuer"])
    if case == "issuer":
        user.oidc_issuer = "wrong"
    session.scalar.return_value = None if case in {"registration", "materialize"} else user
    save = MagicMock(return_value=user)
    if case == "registration":
        save.side_effect = oidc.OIDCError("Account unavailable")
    monkeypatch.setattr(auth, "save_user", save)
    if case == "materialize":
        assert isinstance(http_auth.require_admin(request(), session), AdminPrincipal)
        save.assert_called_once_with(session, record, update_contact=False)
    else:
        with pytest.raises(DomainError):
            http_auth.require_admin(request(), session)


@pytest.mark.parametrize(
    "case",
    [
        "no_origin",
        "invalid_token",
        "no_record",
        "offline",
        "malformed",
        "wrong_transport",
        "cookie",
    ],
)
def test_logout_handles_missing_corrupt_and_unavailable_sessions(
    monkeypatch, configured_settings, case
):
    transport = "cookie" if case in {"no_origin", "cookie"} else "bearer"
    if case == "no_origin":
        configured_settings.user_base_url = None
    store = MagicMock()
    record = {
        "transport": "cookie" if case == "wrong_transport" else "bearer",
        "csrf_token": "c" * 43,
    }
    store.get.return_value = None if case == "no_record" else json.dumps(record).encode()
    if case == "malformed":
        store.get.return_value = b"bad-json"
    if case == "offline":
        store.get.side_effect = RedisError("offline")
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    req = request(headers={"Origin": "https://user.example.test", "X-CSRF-Token": "c" * 43})
    token = "invalid" if case == "invalid_token" else "s" * 43
    if case in {"invalid_token", "no_record", "cookie"}:
        http_auth.validate_logout(req, "user", token, transport)
    else:
        with pytest.raises(DomainError):
            http_auth.validate_logout(req, "user", token, transport)
