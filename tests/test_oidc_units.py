"""Protocol failures and signed-token edge cases without external provider requests."""

import hashlib
import json
import time
from base64 import urlsafe_b64encode
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from kitchen_core import auth, oidc
from pydantic import SecretStr
from starlette.datastructures import QueryParams


@pytest.fixture
def provider_settings():
    return auth.ProviderSettings(
        oidc_issuer_url="https://identity.example.test",
        oidc_client_id="resident",
        oidc_client_secret=None,
        oidc_token_endpoint_auth_method="none",
        oidc_scopes=["profile", "openid"],
        oidc_organization_id="org",
        oidc_organization_scope_template="org:{organization_id}",
        oidc_organization_claim="org",
    )


@pytest.mark.parametrize(
    "method,secret,expected",
    [
        ("none", None, True),
        ("client_secret_basic", None, False),
        ("client_secret_post", "", False),
        ("client_secret_basic", "secret", True),
    ],
)
def test_provider_configuration_requires_credentials(provider_settings, method, secret, expected):
    settings = replace(
        provider_settings,
        oidc_token_endpoint_auth_method=method,
        oidc_client_secret=SecretStr(secret) if secret is not None else None,
    )
    assert oidc.configured(settings, base_url="https://ui.example.test") is expected
    assert not oidc.configured(settings, base_url=None)


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        "https://[invalid",
        "ftp://identity.example.test",
        "https:///",
        "https://a:secret@identity.example.test",
        "https://identity.example.test#fragment",
        "http://other.test",
    ],
)
def test_invalid_provider_endpoints_rejected(provider_settings, value):
    with pytest.raises(oidc.OIDCError, match="Invalid discovery endpoint"):
        oidc.endpoint(value, provider_settings)


def test_loopback_provider_endpoint_accepts_http(provider_settings):
    settings = replace(provider_settings, oidc_issuer_url="http://localhost:8080")
    assert oidc.endpoint("http://localhost:8080/token", settings) == "http://localhost:8080/token"
    assert oidc.endpoint("https://provider.test/token", settings) == "https://provider.test/token"


@pytest.mark.parametrize(
    "mutation,message",
    [
        ({"issuer": "https://wrong.test"}, "issuer mismatch"),
        ({"code_challenge_methods_supported": "S256"}, "capabilities"),
        ({"token_endpoint_auth_methods_supported": [1]}, "capabilities"),
        ({"code_challenge_methods_supported": ["plain"]}, "PKCE"),
        (
            {"token_endpoint_auth_methods_supported": ["client_secret_basic"]},
            "client authentication",
        ),
    ],
)
def test_discovery_rejects_incompatible_metadata(monkeypatch, provider_settings, mutation, message):
    metadata = {
        "issuer": provider_settings.oidc_issuer_url,
        "authorization_endpoint": "https://provider.test/authorize",
        "token_endpoint": "https://provider.test/token",
        "jwks_uri": "https://provider.test/keys",
        "userinfo_endpoint": "https://provider.test/userinfo",
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    } | mutation
    monkeypatch.setattr(oidc, "request_json", lambda *a, **kw: metadata)
    with pytest.raises(oidc.OIDCError, match=message):
        oidc.discovery(provider_settings)


def test_discovery_handles_optional_capabilities(monkeypatch, provider_settings):
    metadata = {
        "issuer": provider_settings.oidc_issuer_url,
        "authorization_endpoint": "https://provider.test/authorize",
        "token_endpoint": "https://provider.test/token",
        "jwks_uri": "https://provider.test/keys",
    }
    settings = replace(provider_settings, oidc_token_endpoint_auth_method="client_secret_basic")
    monkeypatch.setattr(oidc, "request_json", lambda *a, **kw: metadata)
    assert oidc.discovery(settings) == metadata


@pytest.mark.parametrize(
    "kind", ["valid", "redirect", "invalid_json", "array", "too_large", "http_error"]
)
def test_provider_requests_are_bounded_sanitized_and_do_not_follow_redirects(monkeypatch, kind):
    original = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        if kind == "http_error":
            raise httpx.ConnectError("private provider data", request=request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.test"})
        if kind == "invalid_json":
            return httpx.Response(200, content=b"private non-JSON")
        if kind == "array":
            return httpx.Response(200, json=[])
        if kind == "too_large":
            return httpx.Response(200, content=b"x" * 1_000_001)
        return httpx.Response(200, json={"issuer": "provider"})

    def client(**kwargs):
        assert kwargs == {"timeout": 10, "follow_redirects": False}
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(oidc.httpx, "Client", client)
    if kind == "valid":
        assert oidc.request_json("GET", "https://provider.test") == {"issuer": "provider"}
    else:
        with pytest.raises(oidc.OIDCError) as failure:
            oidc.request_json("GET", "https://provider.test")
        assert "private" not in str(failure.value)
    assert len(calls) == 1
    assert calls[0].headers["Accept"] == "application/json"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"{}",
        b"null",
        b'{"browser":1,"policy":"p"}',
        b'{"browser":"wrong","policy":"p"}',
        json.dumps({"browser": "b" * 43, "policy": "other"}).encode(),
    ],
)
def test_callback_rejects_corrupt_or_unbound_flow(payload):
    store = MagicMock()
    store.get.return_value = payload
    with pytest.raises(oidc.OIDCError, match="Invalid login state"):
        oidc.consume_callback_flow(
            query_params=QueryParams(),
            state="s" * 43,
            browser="b" * 43,
            redis=store,
            flow_key="flow",
            policy="p",
        )
    store.getdel.assert_not_called()


@pytest.mark.parametrize(
    "query,state,browser,payload,consumed,message",
    [
        ("code=a&code=b", "s" * 43, "b" * 43, b"{}", None, "Ambiguous"),
        ("", "invalid", "b" * 43, b"{}", None, "Missing login state"),
        ("", "s" * 43, "invalid", b"{}", None, "Missing login state"),
        ("", "s" * 43, "b" * 43, None, None, "Expired"),
        (
            "",
            "s" * 43,
            "b" * 43,
            json.dumps({"browser": "b" * 43, "policy": "p"}).encode(),
            None,
            "already used",
        ),
    ],
)
def test_callback_state_is_single_use(query, state, browser, payload, consumed, message):
    store = MagicMock()
    store.get.return_value, store.getdel.return_value = payload, consumed
    with pytest.raises(oidc.OIDCError, match=message):
        oidc.consume_callback_flow(
            query_params=QueryParams(query),
            state=state,
            browser=browser,
            redis=store,
            flow_key="flow",
            policy="p",
        )


@pytest.mark.parametrize(
    "code,error,issuer",
    [
        (None, None, None),
        ("code", "access_denied", None),
        ("x" * 4097, None, None),
        ("code", None, "https://wrong.test"),
    ],
)
def test_callback_response_rejects_failed_or_mismatched_authorization(code, error, issuer):
    with pytest.raises(oidc.OIDCError):
        oidc.validate_callback_response(
            code=code,
            provider_error=error,
            issuer=issuer,
            expected_issuer="https://identity.example.test",
        )


def test_start_preserves_query_and_reauthenticates(provider_settings):
    url, flow = oidc.start(
        provider_settings,
        {"authorization_endpoint": "https://provider.test/authorize?existing=yes"},
        redirect_uri="https://ui.test/callback",
        policy="p",
        register=True,
        reauthenticate=True,
        role_scope="admin-role",
        identity_provider_id="google",
    )
    params = parse_qs(urlsplit(url).query)
    assert params["existing"] == ["yes"]
    assert params["prompt"] == ["login"] and params["max_age"] == ["0"]
    assert "admin-role" in params["scope"][0]
    assert "urn:zitadel:iam:org:idp:id:google" in params["scope"][0]
    assert params["scope"][0].split().count("openid") == 1
    assert flow["reauthenticate"]
    with pytest.raises(oidc.OIDCError, match="Invalid identity provider"):
        oidc.start(
            provider_settings,
            {"authorization_endpoint": "https://provider.test"},
            redirect_uri="https://ui.test",
            policy="p",
            identity_provider_id="bad id",
        )


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def identity_exchange(monkeypatch, provider_settings, signing_key):
    now = int(time.time())
    claims = {
        "iss": provider_settings.oidc_issuer_url,
        "aud": "resident",
        "sub": "resident",
        "exp": now + 3600,
        "iat": now,
        "nonce": "nonce",
        "org": "org",
    }
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    key.update(kid="one", use="sig", alg="RS256")
    stub = SimpleNamespace(
        claims=claims,
        header={"kid": "one"},
        keys=[key],
        info={"sub": "resident"},
        access="access",
        tokens=None,
        request=None,
        flow={"nonce": "nonce", "verifier": "verifier", "started_at": now},
    )
    metadata = {
        "token_endpoint": "https://provider.test/token",
        "jwks_uri": "https://provider.test/keys",
        "userinfo_endpoint": "https://provider.test/info",
    }

    def request(method, url, **kwargs):
        if method == "POST":
            stub.request = kwargs
            return (
                stub.tokens
                if stub.tokens is not None
                else {
                    "id_token": jwt.encode(
                        stub.claims, signing_key, algorithm="RS256", headers=stub.header
                    ),
                    "access_token": stub.access,
                }
            )
        if url.endswith("keys"):
            return {"keys": stub.keys}
        return stub.info

    monkeypatch.setattr(oidc, "request_json", request)

    def exchange(settings=None):
        return oidc.identity(
            settings or provider_settings,
            metadata,
            stub.flow,
            "code",
            redirect_uri="https://ui.test/callback",
            session_ttl=600,
        )

    return stub, metadata, exchange


@pytest.mark.parametrize("method", ["none", "client_secret_basic", "client_secret_post"])
def test_identity_exchange_client_auth_and_verified_hashes(
    provider_settings, identity_exchange, method
):
    stub, _, exchange = identity_exchange
    for claim, value in (("at_hash", "access"), ("c_hash", "code")):
        digest = hashlib.sha256(value.encode()).digest()
        stub.claims[claim] = urlsafe_b64encode(digest[:16]).rstrip(b"=").decode()
    stub.header = {}  # A single eligible signing key may be selected without a kid.
    stub.claims.update(
        name="Resident",
        email="resident@example.test",
        phone_number="+919000000001",
        phone_number_verified=True,
        auth_time=int(time.time()),
    )
    stub.flow["reauthenticate"] = True
    settings = replace(
        provider_settings,
        oidc_token_endpoint_auth_method=method,
        oidc_client_secret=SecretStr("secret"),
    )
    result = exchange(settings)
    assert result["subject"] == "resident" and result["phone"] == "+919000000001"
    if method == "client_secret_basic":
        assert isinstance(stub.request["auth"], httpx.BasicAuth)
        assert "client_secret" not in stub.request["data"]
    else:
        assert stub.request["data"]["client_id"] == "resident"
        assert ("client_secret" in stub.request["data"]) == (method == "client_secret_post")


@pytest.mark.parametrize(
    "changes",
    [
        {"nonce": 5},
        {"nonce": "wrong"},
        {"azp": "another"},
        {"aud": ["resident", "other"]},
        {"sub": ""},
        {"exp": str(int(time.time()) + 3600)},
        {"iat": str(int(time.time()))},
        {"org": "wrong"},
        {"at_hash": 1},
        {"at_hash": "wrong"},
        {"c_hash": "wrong"},
    ],
)
def test_signed_but_invalid_identity_claims_rejected(identity_exchange, changes):
    stub, _, exchange = identity_exchange
    stub.claims.update(changes)
    with pytest.raises(oidc.OIDCError):
        exchange()


@pytest.mark.parametrize("auth_time", [None, "now", 1, int(time.time()) + 3600])
def test_reauthentication_requires_fresh_authentication(identity_exchange, auth_time):
    stub, _, exchange = identity_exchange
    stub.flow["reauthenticate"] = True
    stub.claims["auth_time"] = auth_time
    with pytest.raises(oidc.OIDCError, match="Fresh authentication"):
        exchange()


@pytest.mark.parametrize(
    "problem",
    [
        "missing_token",
        "malformed_token",
        "wrong_key",
        "multiple_keys",
        "wrong_subject",
        "conflicting_org",
        "missing_access_hash",
    ],
)
def test_identity_rejects_invalid_exchange_and_profile(identity_exchange, problem):
    stub, _, exchange = identity_exchange
    if problem == "missing_token":
        stub.tokens = {}
    elif problem == "malformed_token":
        stub.tokens = {"id_token": "invalid"}
    elif problem == "wrong_key":
        stub.header = {"kid": "another"}
    elif problem == "multiple_keys":
        stub.keys.append(stub.keys[0])
    elif problem == "wrong_subject":
        stub.info = {"sub": "another"}
    elif problem == "conflicting_org":
        stub.info = {"sub": "resident", "org": "another"}
    else:
        stub.access = None
        stub.claims["at_hash"] = "hash"
    with pytest.raises(oidc.OIDCError):
        exchange()


def test_identity_without_userinfo_and_bearer_header(identity_exchange):
    stub, metadata, exchange = identity_exchange
    metadata.pop("userinfo_endpoint")
    stub.claims.update(aud=["resident", "other"], azp="resident")
    assert exchange()["userinfo_claims"] == {}
    request = httpx.Request("GET", "https://provider.test")
    result = next(oidc.BearerToken("opaque").auth_flow(request))
    assert result.headers["Authorization"] == "Bearer opaque"
