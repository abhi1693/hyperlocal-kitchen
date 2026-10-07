"""Zitadel authorization-code identity and isolated, revocable Redis sessions."""

import hashlib
import json
import secrets
import time
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast
from uuid import UUID

from kitchen_core import oidc
from kitchen_core.auth_schemas import ResidentSession
from kitchen_core.errors import DomainError
from kitchen_core.models import Device, User
from kitchen_core.settings import get_settings
from pydantic import SecretStr
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

Kind = Literal["user", "admin"]
TOKEN = oidc.TOKEN
FLOW_TTL = oidc.FLOW_TTL
# A compare-and-set prevents a renewal racing logout from recreating a session.
RENEW_SESSION = """
local current = redis.call('GET', KEYS[1])
if not current then return false end
if current ~= ARGV[1] then return current end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return ARGV[2]
"""


@dataclass
class ProviderSettings:
    oidc_issuer_url: str | None
    oidc_client_id: str | None
    oidc_client_secret: SecretStr | None
    oidc_token_endpoint_auth_method: str
    oidc_scopes: list[str]
    oidc_organization_id: str | None
    oidc_organization_scope_template: str
    oidc_organization_claim: str


def provider_settings(kind: Kind) -> ProviderSettings:
    settings = get_settings()
    return ProviderSettings(
        oidc_issuer_url=settings.oidc_issuer_url,
        oidc_client_id=getattr(settings, f"{kind}_oidc_client_id"),
        oidc_client_secret=getattr(settings, f"{kind}_oidc_client_secret"),
        oidc_token_endpoint_auth_method=settings.oidc_token_endpoint_auth_method,
        oidc_scopes=settings.oidc_scopes,
        oidc_organization_id=settings.oidc_organization_id,
        oidc_organization_scope_template=settings.oidc_organization_scope_template,
        oidc_organization_claim=settings.oidc_organization_claim,
    )


def configured(kind: Kind) -> bool:
    return oidc.configured(
        provider_settings(kind), base_url=getattr(get_settings(), f"{kind}_base_url")
    )


def require_config(kind: Kind) -> None:
    if not configured(kind):
        raise DomainError(503, "auth_not_configured", "Zitadel sign-in is not configured")


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_timeout=5, socket_connect_timeout=5)


def key(kind: Kind, record_type: str, token: str) -> str:
    return f"kitchen:{kind}:{record_type}:{hashlib.sha256(token.encode()).hexdigest()}"


def cookie_name(kind: Kind, cookie_type: str) -> str:
    return oidc.cookie_name(kind, cookie_type, secure=get_settings().cookie_secure)


def policy_key(kind: Kind) -> str:
    settings = get_settings()
    values = {
        field: value
        for field, value in settings.model_dump(mode="json").items()
        if field.startswith(("oidc_", f"{kind}_"))
        or field in {"cookie_secure", "mobile_redirect_uri"}
    }
    secret = getattr(settings, f"{kind}_oidc_client_secret")
    if secret:
        values[f"{kind}_oidc_client_secret"] = secret.get_secret_value()
    if kind == "admin":
        values["admin_required_role"] = settings.admin_required_role
    values["authorization_policy_version"] = f"zitadel-{kind}-v1"
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def redirect_uri(kind: Kind) -> str:
    origin = str(getattr(get_settings(), f"{kind}_base_url")).rstrip("/")
    return origin + "/api/v1/auth/callback"


def discovery(kind: Kind) -> dict:
    require_config(kind)
    return oidc.discovery(provider_settings(kind))


def start(kind: Kind, *, register=False, reauthenticate=False, provider=None) -> tuple[str, dict]:
    require_config(kind)
    settings = get_settings()
    provider_id = getattr(settings, f"oidc_{provider}_idp_id") if provider else None
    if provider and not provider_id:
        raise oidc.OIDCError("Identity provider is not configured")
    return oidc.start(
        provider_settings(kind),
        discovery(kind),
        redirect_uri=redirect_uri(kind),
        policy=policy_key(kind),
        register=register if kind == "user" else False,
        reauthenticate=reauthenticate,
        identity_provider_id=provider_id,
        role_scope=(
            f"urn:zitadel:iam:org:project:role:{settings.admin_required_role}"
            if kind == "admin"
            else None
        ),
    )


def verified_roles(id_claims: dict, userinfo: dict) -> list[str]:
    settings = get_settings()
    assertions = []
    for claims in (id_claims, userinfo):
        if settings.oidc_roles_claim not in claims:
            continue
        value = claims[settings.oidc_roles_claim]
        roles: set[str] = set()
        if not isinstance(value, dict):
            assertions.append(roles)
            continue
        for role, grants in value.items():
            if (
                not isinstance(role, str)
                or not isinstance(grants, dict)
                or not all(
                    isinstance(org, str) and isinstance(domain, str)
                    for org, domain in grants.items()
                )
            ):
                roles = set()
                break
            if grants.get(settings.oidc_organization_id):
                roles.add(role)
        assertions.append(roles)
    return sorted(set.intersection(*assertions)) if assertions else []


def identity(kind: Kind, flow: dict, code: str) -> dict:
    settings = get_settings()
    result = oidc.identity(
        provider_settings(kind),
        discovery(kind),
        flow,
        code,
        redirect_uri=redirect_uri(kind),
        session_ttl=(
            settings.user_session_ttl_seconds
            if kind == "user"
            else settings.admin_session_ttl_seconds
        ),
    )
    roles = verified_roles(result.pop("id_claims"), result.pop("userinfo_claims"))
    now = int(time.time())
    if result["expires_at"] <= now:
        raise oidc.OIDCError("Expired identity")
    if kind == "admin":
        if settings.admin_required_role not in roles:
            raise oidc.OIDCError("Required administrator role is not granted")
        result["roles"] = roles
    else:
        # Like DevFeed, the validated ID token authenticates this login; a separate
        # revocable session has its own fixed maximum lifetime and renewable idle window.
        result.update(
            expires_at=now + settings.user_session_ttl_seconds,
            absolute_expires_at=now + settings.user_session_absolute_ttl_seconds,
            renewed_at=now,
        )
    result["policy"] = policy_key(kind)
    result["csrf_token"] = secrets.token_urlsafe(32)
    return result


def save_user(session: Session, record: dict, *, update_contact: bool = True) -> User:
    # A stable advisory lock serializes first sign-ins before an account row exists.
    digest = hashlib.sha256((record["issuer"] + ":" + record["subject"]).encode()).digest()
    session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(digest[:8], signed=True))))
    user = session.scalar(
        select(User).where(User.oidc_subject == record["subject"]).with_for_update()
    )
    if user is None:
        user = User(
            oidc_subject=record["subject"],
            oidc_issuer=record["issuer"],
            name=record.get("name"),
            phone=record.get("phone"),
        )
        session.add(user)
        session.flush()
    if user.oidc_issuer != record["issuer"] or not user.is_active:
        raise oidc.OIDCError("Account unavailable")
    # Profile phone is delivery contact only, never an authentication identity.
    if update_contact:
        user.phone = record.get("phone")
    record["user_id"] = str(user.id)
    return user


def create_session(kind: Kind, record: dict, *, transport="cookie") -> str:
    token = secrets.token_urlsafe(32)
    if kind == "user":
        record["transport"] = transport
    ttl = record["expires_at"] - int(time.time())
    if ttl <= 0:
        raise oidc.OIDCError("Expired identity")
    get_redis().set(key(kind, "session", token), json.dumps(record), ex=ttl)
    return token


def _valid_record(kind: Kind, record: dict) -> bool:
    now = int(time.time())
    return (
        record.get("policy") == policy_key(kind)
        and type(record.get("expires_at")) is int
        and record["expires_at"] > now
        and (
            kind != "user"
            or type(record.get("absolute_expires_at")) is int
            and record["absolute_expires_at"] > now
        )
    )


def load_session(kind: Kind, token: str) -> dict:
    require_config(kind)
    if not TOKEN.fullmatch(token):
        raise DomainError(401, "sign_in_required", "Please sign in to continue")
    try:
        raw = cast(bytes | None, get_redis().get(key(kind, "session", token)))
        record = json.loads(raw) if raw else None
    except RedisError as exc:
        raise DomainError(
            503, "sessions_unavailable", "Sign-in sessions temporarily unavailable"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise DomainError(401, "invalid_session", "Please sign in again") from exc
    if not isinstance(record, dict) or not _valid_record(kind, record):
        raise DomainError(401, "invalid_session", "Please sign in again")
    return record


def resident_session(token: str, *, transport: str) -> ResidentSession:
    record = load_session("user", token)
    if record.get("transport") != transport:
        raise DomainError(401, "invalid_session", "Please sign in again")
    try:
        return ResidentSession.model_validate(
            {**record, "session_key": key("user", "session", token)}
        )
    except ValueError as exc:
        raise DomainError(401, "invalid_session", "Please sign in again") from exc


def renew_resident_session(token: str) -> dict:
    record = load_session("user", token)
    now = int(time.time())
    settings = get_settings()
    if record["renewed_at"] > now - min(3600, settings.user_session_ttl_seconds // 2):
        return record
    session_key = key("user", "session", token)
    try:
        redis = get_redis()
        previous = cast(bytes | None, redis.get(session_key))
        if previous is None:
            raise DomainError(401, "invalid_session", "Please sign in again")
        current = json.loads(previous)
        if not _valid_record("user", current):
            raise DomainError(401, "invalid_session", "Please sign in again")
        current.update(
            expires_at=min(now + settings.user_session_ttl_seconds, current["absolute_expires_at"]),
            renewed_at=now,
        )
        result = redis.eval(
            RENEW_SESSION,
            1,
            session_key,
            previous,
            json.dumps(current),
            current["expires_at"] - now,
        )
        if not result:
            raise DomainError(401, "invalid_session", "Please sign in again")
        return json.loads(cast(bytes, result))
    except RedisError as exc:
        raise DomainError(
            503, "sessions_unavailable", "Sign-in sessions temporarily unavailable"
        ) from exc


def device_session_active(session_key: str, user_id: UUID) -> bool:
    if not session_key.startswith("kitchen:user:session:"):
        return False
    try:
        raw = cast(bytes | None, get_redis().get(session_key))
        record = json.loads(raw) if raw else None
        return (
            isinstance(record, dict)
            and _valid_record("user", record)
            and record.get("user_id") == str(user_id)
        )
    except (ValueError, TypeError):
        return False


def revoke_session(session: Session, kind: Kind, token: str) -> None:
    if not TOKEN.fullmatch(token):
        return
    session_key = key(kind, "session", token)
    try:
        get_redis().delete(session_key)
    except RedisError as exc:
        raise DomainError(
            503, "sessions_unavailable", "Could not revoke session; retry sign-out"
        ) from exc
    if kind == "user":
        session.execute(
            update(Device).where(Device.session_key == session_key).values(is_active=False)
        )


def pkce_challenge(verifier: str) -> str:
    return urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
