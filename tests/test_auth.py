import json
import secrets
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from kitchen_core import auth, oidc
from kitchen_core.models import User
from kitchen_core.settings import Settings, get_settings
from redis import Redis
from redis.exceptions import RedisError


@pytest.fixture(autouse=True)
def auth_configuration(monkeypatch):
    redis_factory = auth.get_redis
    for field, value in {
        "ENVIRONMENT": "test",
        "OIDC_ISSUER_URL": "https://identity.example.test",
        "OIDC_ORGANIZATION_ID": "pilot-org",
        "USER_BASE_URL": "http://testserver",
        "ADMIN_BASE_URL": "http://testserver",
        "USER_OIDC_CLIENT_ID": "resident-client",
        "ADMIN_OIDC_CLIENT_ID": "admin-client",
        "COOKIE_SECURE": "false",
    }.items():
        monkeypatch.setenv("KITCHEN_" + field, value)
    get_settings.cache_clear()
    redis_factory.cache_clear()
    yield
    get_settings.cache_clear()
    redis_factory.cache_clear()


@pytest.fixture
def redis_store():
    url = get_settings().redis_url
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/15":
        pytest.fail("Authentication tests require disposable loopback Redis database 15")
    redis = Redis.from_url(url)
    redis.flushdb()
    yield redis
    redis.flushdb()
    redis.close()


@pytest.fixture
def provider(monkeypatch, redis_store):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update(kid="key-one", use="sig", alg="RS256")
    stub = SimpleNamespace(
        nonce=None,
        client_id=None,
        claims={},
        info={},
        exchanged=None,
        key=private_key,
        subject="resident-one",
        bad_signature=False,
    )
    issuer = get_settings().oidc_issuer_url
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/oauth/v2/authorize",
        "token_endpoint": issuer + "/oauth/v2/token",
        "jwks_uri": issuer + "/oauth/v2/keys",
        "userinfo_endpoint": issuer + "/oidc/v1/userinfo",
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }

    def request_json(method, url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return metadata
        if url == metadata["jwks_uri"]:
            return {"keys": [jwk]}
        claims = {
            "iss": issuer,
            "aud": stub.client_id,
            "sub": stub.subject,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "nonce": stub.nonce,
            get_settings().oidc_organization_claim: "pilot-org",
            get_settings().oidc_roles_claim: {"platform_admin": {"pilot-org": "pilot.test"}},
            **stub.claims,
        }
        if method == "POST" and url == metadata["token_endpoint"]:
            stub.exchanged = kwargs["data"]
            key = stub.key
            if stub.bad_signature:
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            return {
                "id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key-one"}),
                "access_token": "provider-access-token-stays-server-side",
            }
        if url == metadata["userinfo_endpoint"]:
            return {
                "sub": stub.subject,
                "name": "Resident One",
                "phone_number": "+919876543210",
                "phone_number_verified": True,
                get_settings().oidc_organization_claim: "pilot-org",
                **stub.info,
            }
        pytest.fail("Unexpected provider endpoint")

    monkeypatch.setattr(oidc, "request_json", request_json)
    return stub


@pytest.fixture
def oidc_admin_client(session_factory):
    from conftest import override_session
    from kitchen_admin_api.main import create_app

    app = create_app()
    override_session(app, session_factory)
    with TestClient(app) as client:
        yield client


def begin(client, provider, kind="user", url=None):
    prefix = "/api/v1/auth"
    response = client.get(url or prefix + "/login", follow_redirects=False)
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    provider.nonce = query["nonce"][0]
    provider.client_id = query["client_id"][0]
    return query


def complete(client, provider, kind="user", query=None):
    prefix = "/api/v1/auth"
    query = query or begin(client, provider, kind)
    return client.get(
        prefix + "/callback",
        params={
            "state": query["state"][0],
            "code": "provider-code",
            "iss": get_settings().oidc_issuer_url,
        },
        follow_redirects=False,
    )


def test_unconfigured_auth_is_disabled_without_any_local_fallback(client, monkeypatch):
    monkeypatch.delenv("KITCHEN_USER_OIDC_CLIENT_ID")
    get_settings.cache_clear()
    assert client.get("/api/v1/auth/config").json()["enabled"] is False
    assert client.get("/api/v1/auth/login").status_code == 503
    assert (
        client.post("/api/v1/auth/otp/request", json={"phone": "+919876543210"}).status_code == 404
    )
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 43}).status_code == 404


def test_pkce_browser_binding_single_use_and_cookie_csrf(client, provider, redis_store):
    query = begin(client, provider)
    flow = json.loads(redis_store.get(auth.key("user", "flow", query["state"][0])))
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0] == auth.pkce_challenge(flow["verifier"])
    assert flow["verifier"] not in str(query)
    assert complete(client, provider, query=query).headers["location"] == "http://testserver/"
    assert provider.exchanged["code_verifier"] == flow["verifier"]
    assert provider.exchanged["redirect_uri"] == "http://testserver/api/v1/auth/callback"
    identity = client.get("/api/v1/auth/me").json()
    assert identity["phone"] == "+919876543210"
    assert "oidc_subject" not in identity and "oidc_issuer" not in identity
    assert client.patch("/api/v1/me", json={"name": "Updated"}).status_code == 403
    headers = {"Origin": "http://testserver", "X-CSRF-Token": identity["csrf_token"]}
    assert client.patch("/api/v1/me", json={"name": "Updated"}, headers=headers).status_code == 200
    # Replayed callbacks never erase an existing, unrelated valid session.
    assert "login_failed" in complete(client, provider, query=query).headers["location"]
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_callback_wrong_browser_does_not_consume_flow(client, provider, redis_store):
    query = begin(client, provider)
    client.cookies.set(auth.cookie_name("user", "state"), secrets.token_urlsafe(32))
    assert "login_failed" in complete(client, provider, query=query).headers["location"]
    assert redis_store.exists(auth.key("user", "flow", query["state"][0]))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_browser_login_replaces_and_revokes_the_previous_browser_session(
    client, provider, redis_store
):
    complete(client, provider)
    previous = client.cookies.get(auth.cookie_name("user", "session"))
    identity = client.get("/api/v1/auth/me").json()
    assert redis_store.exists(auth.key("user", "session", previous))

    assert complete(client, provider).headers["location"] == "http://testserver/"
    current = client.cookies.get(auth.cookie_name("user", "session"))
    assert current != previous
    assert not redis_store.exists(auth.key("user", "session", previous))
    assert redis_store.exists(auth.key("user", "session", current))
    assert client.get("/api/v1/auth/me").json()["id"] == identity["id"]


@pytest.mark.parametrize("native", [False, True])
def test_bound_callback_failure_preserves_browser_login_only_for_native_flow(
    client, provider, redis_store, native
):
    complete(client, provider)
    previous = client.cookies.get(auth.cookie_name("user", "session"))
    identity = client.get("/api/v1/auth/me").json()
    if native:
        verifier = secrets.token_urlsafe(48)
        result = client.post(
            "/api/v1/auth/mobile/start", json={"code_challenge": auth.pkce_challenge(verifier)}
        )
        assert result.status_code == 200, result.text
        query = begin(client, provider, url=result.json()["authorization_url"])
    else:
        query = begin(client, provider)
    provider.bad_signature = True

    callback = complete(client, provider, query=query)
    assert callback.status_code == 302
    if native:
        assert callback.headers["location"] == (
            "hyperlocal-kitchen://auth/callback?error=login_failed"
        )
        assert client.cookies.get(auth.cookie_name("user", "session")) == previous
        assert all(
            not header.startswith(auth.cookie_name("user", "session") + "=")
            for header in callback.headers.get_list("set-cookie")
        )
        assert redis_store.exists(auth.key("user", "session", previous))
        assert client.get("/api/v1/auth/me").json()["id"] == identity["id"]
    else:
        assert callback.headers["location"] == "http://testserver/login?error=login_failed"
        assert not redis_store.exists(auth.key("user", "session", previous))
        assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "failure", ["nonce", "audience", "issuer", "userinfo_subject", "organization", "signature"]
)
def test_provider_validation_rejects_invalid_identity(client, provider, failure):
    query = begin(client, provider)
    if failure == "nonce":
        provider.claims["nonce"] = "wrong-nonce"
    elif failure == "audience":
        provider.claims["aud"] = "wrong-client"
    elif failure == "issuer":
        provider.claims["iss"] = "https://other.example.test"
    elif failure == "userinfo_subject":
        provider.info["sub"] = "different-account"
    elif failure == "organization":
        provider.info[get_settings().oidc_organization_claim] = "other-org"
    else:
        provider.bad_signature = True
    assert "login_failed" in complete(client, provider, query=query).headers["location"]
    assert client.get("/api/v1/auth/me").status_code == 401


def test_admin_requires_exact_role_in_exact_zitadel_organization(oidc_admin_client, provider):
    provider.claims[get_settings().oidc_roles_claim] = {
        "platform_admin": {"other-org": "other.test"}
    }
    assert "login_failed" in complete(oidc_admin_client, provider, "admin").headers["location"]
    assert oidc_admin_client.get("/api/v1/auth/me").status_code == 401
    provider.claims = {}
    assert (
        complete(oidc_admin_client, provider, "admin").headers["location"]
        == "http://testserver/start"
    )
    identity = oidc_admin_client.get("/api/v1/auth/me").json()
    assert identity["roles"] == ["platform_admin"]
    assert oidc_admin_client.post("/api/v1/auth/logout").status_code == 403
    assert (
        oidc_admin_client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://testserver", "X-CSRF-Token": identity["csrf_token"]},
        ).status_code
        == 204
    )
    assert oidc_admin_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("first", ["user", "admin"])
@pytest.mark.parametrize("role", ["platform_admin", "superuser"])
def test_admin_and_resident_logins_share_one_listed_user(
    client, oidc_admin_client, provider, session, monkeypatch, first, role
):
    monkeypatch.setenv("KITCHEN_ADMIN_REQUIRED_ROLE", role)
    get_settings.cache_clear()
    provider.claims[get_settings().oidc_roles_claim] = {role: {"pilot-org": "pilot.test"}}
    logins = {"user": client, "admin": oidc_admin_client}
    assert "login_failed" not in complete(logins[first], provider, first).headers["location"]
    user = session.query(User).filter_by(oidc_subject=provider.subject).one()
    user_id = str(user.id)
    # Admin login must preserve the application's existing delivery contact.
    user.phone = "+919000000001"
    session.commit()
    second = "admin" if first == "user" else "user"
    assert "login_failed" not in complete(logins[second], provider, second).headers["location"]
    listed = oidc_admin_client.get("/api/v1/users").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == user_id
    assert listed["items"][0]["name"] == "Resident One"
    assert client.get("/api/v1/auth/me").json()["id"] == user_id
    if second == "admin":
        assert listed["items"][0]["phone"] == "+919000000001"
    else:
        assert listed["items"][0]["phone"] == "+919876543210"


def test_existing_admin_session_registers_missing_application_user(
    oidc_admin_client, provider, session
):
    assert complete(oidc_admin_client, provider, "admin").headers["location"].endswith("/start")
    session.query(User).filter_by(oidc_subject=provider.subject).delete()
    session.commit()
    # Simulate a session issued by the previous admin-only login implementation.
    listed = oidc_admin_client.get("/api/v1/users").json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "Resident One"
    assert (
        oidc_admin_client.get("/api/v1/users").json()["items"][0]["id"] == listed["items"][0]["id"]
    )


def test_ungranted_admin_login_does_not_create_user(oidc_admin_client, provider, session):
    provider.claims[get_settings().oidc_roles_claim] = {"owner": {"pilot-org": "pilot.test"}}
    assert "login_failed" in complete(oidc_admin_client, provider, "admin").headers["location"]
    assert session.query(User).count() == 0


def test_disabled_user_cannot_keep_admin_access(oidc_admin_client, provider, session):
    assert complete(oidc_admin_client, provider, "admin").headers["location"].endswith("/start")
    user = session.query(User).filter_by(oidc_subject=provider.subject).one()
    user.is_active = False
    session.commit()
    assert oidc_admin_client.get("/api/v1/users").status_code == 401
    assert "login_failed" in complete(oidc_admin_client, provider, "admin").headers["location"]
    session.refresh(user)
    assert user.is_active is False


def test_conflicting_verified_role_assertions_never_expand_access(oidc_admin_client, provider):
    provider.info[get_settings().oidc_roles_claim] = {"kitchen_owner": {"pilot-org": "pilot.test"}}
    assert "login_failed" in complete(oidc_admin_client, provider, "admin").headers["location"]


def test_native_handoff_is_pkce_bound_single_use_and_revocable(client, provider, redis_store):
    verifier = secrets.token_urlsafe(48)
    result = client.post(
        "/api/v1/auth/mobile/start", json={"code_challenge": auth.pkce_challenge(verifier)}
    )
    query = begin(client, provider, url=result.json()["authorization_url"])
    callback = complete(client, provider, query=query)
    location = callback.headers["location"]
    assert location.startswith("hyperlocal-kitchen://auth/callback?code=")
    assert "provider-access-token" not in location
    code = parse_qs(urlsplit(location).query)["code"][0]
    assert (
        client.post(
            "/api/v1/auth/mobile/exchange", json={"code": code, "code_verifier": "x" * 43}
        ).status_code
        == 401
    )
    response = client.post(
        "/api/v1/auth/mobile/exchange", json={"code": code, "code_verifier": verifier}
    )
    assert response.status_code == 200, response.text
    token = response.json()["session_token"]
    assert len(token) == 43
    assert (
        client.post(
            "/api/v1/auth/mobile/exchange", json={"code": code, "code_verifier": verifier}
        ).status_code
        == 401
    )
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    user_id = response.json()["user"]["id"]
    from uuid import UUID

    assert auth.device_session_active(auth.key("user", "session", token), UUID(user_id))
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert not redis_store.exists(auth.key("user", "session", token))
    assert not auth.device_session_active(auth.key("user", "session", token), UUID(user_id))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_native_sign_in_and_logout_preserve_an_existing_browser_login(
    client, provider, redis_store
):
    complete(client, provider)
    browser_token = client.cookies.get(auth.cookie_name("user", "session"))
    browser_identity = client.get("/api/v1/auth/me").json()
    browser_session_key = auth.key("user", "session", browser_token)

    provider.subject = "mobile-resident"
    provider.info = {"name": "Mobile Resident", "phone_number": "+919876543211"}
    verifier = secrets.token_urlsafe(48)
    result = client.post(
        "/api/v1/auth/mobile/start", json={"code_challenge": auth.pkce_challenge(verifier)}
    )
    assert result.status_code == 200, result.text
    query = begin(client, provider, url=result.json()["authorization_url"])
    callback = complete(client, provider, query=query)
    assert callback.headers["location"].startswith("hyperlocal-kitchen://auth/callback?code=")
    assert all(
        not header.startswith(auth.cookie_name("user", "session") + "=")
        for header in callback.headers.get_list("set-cookie")
    )
    assert client.cookies.get(auth.cookie_name("user", "session")) == browser_token
    assert redis_store.exists(browser_session_key)
    assert client.get("/api/v1/auth/me").json()["id"] == browser_identity["id"]

    code = parse_qs(urlsplit(callback.headers["location"]).query)["code"][0]
    exchange = client.post(
        "/api/v1/auth/mobile/exchange", json={"code": code, "code_verifier": verifier}
    )
    assert exchange.status_code == 200, exchange.text
    native_identity = exchange.json()["user"]
    native_token = exchange.json()["session_token"]
    assert native_identity["id"] != browser_identity["id"]
    assert native_token != browser_token
    assert client.cookies.get(auth.cookie_name("user", "session")) == browser_token
    assert redis_store.exists(browser_session_key)
    native_headers = {"Authorization": "Bearer " + native_token}
    native_me = client.get("/api/v1/auth/me", headers=native_headers)
    assert native_me.status_code == 200, native_me.text
    assert native_me.json()["id"] == native_identity["id"]
    assert client.get("/api/v1/auth/me").json()["id"] == browser_identity["id"]

    with TestClient(client.app) as native_client:
        assert native_client.post("/api/v1/auth/logout", headers=native_headers).status_code == 204
        assert native_client.get("/api/v1/auth/me", headers=native_headers).status_code == 401
    assert not redis_store.exists(auth.key("user", "session", native_token))
    assert redis_store.exists(browser_session_key)
    browser_me = client.get("/api/v1/auth/me")
    assert browser_me.status_code == 200, browser_me.text
    assert browser_me.json()["id"] == browser_identity["id"]
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": browser_me.json()["csrf_token"],
            },
        ).status_code
        == 204
    )
    assert not redis_store.exists(browser_session_key)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_unverified_provider_phone_never_becomes_delivery_contact(client, provider, session):
    provider.info["phone_number_verified"] = False
    complete(client, provider)
    assert client.get("/api/v1/auth/me").json()["phone"] is None
    user = session.query(User).one()
    assert user.phone is None


def test_policy_change_invalidates_existing_session(client, provider, monkeypatch):
    complete(client, provider)
    monkeypatch.setenv("KITCHEN_USER_OIDC_CLIENT_ID", "new-resident-client")
    get_settings.cache_clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_configuration_requires_separate_clients_and_secure_production_cookies():
    with pytest.raises(ValueError):
        Settings(user_oidc_client_id="same", admin_oidc_client_id="same")
    with pytest.raises(ValueError):
        Settings(environment="production", cookie_secure=False)


def test_device_session_lookup_preserves_redis_outage_for_worker_retry(monkeypatch):
    def unavailable_lookup(key):
        raise RedisError("Session store unavailable")

    monkeypatch.setattr(auth, "get_redis", lambda: SimpleNamespace(get=unavailable_lookup))
    with pytest.raises(RedisError):
        auth.device_session_active("kitchen:user:session:" + "a" * 64, uuid4())
