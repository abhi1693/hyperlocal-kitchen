import hmac
import json
from typing import Annotated, cast

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from kitchen_core import auth
from kitchen_core.auth_schemas import AdminPrincipal, ResidentSession
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import User
from kitchen_core.settings import get_settings
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

DB = Annotated[Session, Depends(get_session, scope="function")]
user_cookie = APIKeyCookie(name="__Host-kitchen_user_session", auto_error=False)
admin_cookie = APIKeyCookie(name="__Host-kitchen_admin_session", auto_error=False)
user_bearer = HTTPBearer(
    auto_error=False, description="Opaque mobile session, never a provider JWT"
)


def request_token(request: Request, kind: auth.Kind) -> tuple[str, str]:
    authorization = request.headers.get("authorization")
    if authorization:
        if kind != "user":
            raise DomainError(401, "admin_sign_in_required", "Administrator sign-in required")
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise DomainError(401, "invalid_session", "Please sign in again")
        return parts[1], "bearer"
    return request.cookies.get(auth.cookie_name(kind, "session"), ""), "cookie"


def validate_csrf(request: Request, kind: auth.Kind, record: dict) -> None:
    settings = get_settings()
    origin = getattr(settings, f"{kind}_base_url")
    expected = record.get("csrf_token", "")
    supplied = request.headers.get("x-csrf-token", "")
    if (
        not origin
        or request.headers.get("origin") != origin.rstrip("/")
        or not isinstance(expected, str)
        or not auth.TOKEN.fullmatch(expected)
        or not auth.TOKEN.fullmatch(supplied)
        or not hmac.compare_digest(supplied, expected)
    ):
        raise DomainError(403, "invalid_csrf", "Invalid request origin or CSRF token")


def require_resident_session(
    request: Request,
    _cookie: Annotated[str | None, Security(user_cookie)] = None,
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(user_bearer)] = None,
) -> ResidentSession:
    token, transport = request_token(request, "user")
    record = auth.resident_session(token, transport=transport)
    if transport == "cookie" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        validate_csrf(request, "user", record.model_dump())
    request.state.resident_session = record
    return record


def require_user(
    session: DB,
    resident: Annotated[ResidentSession, Depends(require_resident_session)],
) -> User:
    user = session.get(User, resident.user_id)
    if (
        user is None
        or not user.is_active
        or user.oidc_subject != resident.subject
        or user.oidc_issuer != resident.issuer
    ):
        raise DomainError(401, "invalid_session", "Please sign in again")
    return user


def require_admin(
    request: Request,
    _cookie: Annotated[str | None, Security(admin_cookie)] = None,
) -> AdminPrincipal:
    token, _ = request_token(request, "admin")
    record = auth.load_session("admin", token)
    try:
        admin = AdminPrincipal.model_validate(record)
    except ValueError as exc:
        raise DomainError(401, "invalid_session", "Administrator sign-in required") from exc
    if get_settings().admin_required_role not in admin.roles:
        raise DomainError(403, "admin_role_required", "Platform administrator access required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        validate_csrf(request, "admin", record)
    return admin


def validate_logout(request: Request, kind: auth.Kind, token: str, transport: str) -> None:
    if transport == "cookie":
        origin = getattr(get_settings(), f"{kind}_base_url")
        if not origin or request.headers.get("origin") != origin.rstrip("/"):
            raise DomainError(403, "invalid_csrf", "Invalid request origin")
    if not auth.TOKEN.fullmatch(token):
        return
    try:
        raw = cast(bytes | None, auth.get_redis().get(auth.key(kind, "session", token)))
    except RedisError as exc:
        raise DomainError(
            503, "sessions_unavailable", "Could not revoke session; retry sign-out"
        ) from exc
    if raw:
        try:
            record = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise DomainError(401, "invalid_session", "Please sign in again") from exc
        if transport == "cookie":
            validate_csrf(request, kind, record)
        elif record.get("transport") != "bearer":
            raise DomainError(401, "invalid_session", "Please sign in again")


current_user = require_user
require_resident = require_user
CurrentUser = Annotated[User, Depends(require_user)]
Admin = Annotated[AdminPrincipal, Depends(require_admin)]
