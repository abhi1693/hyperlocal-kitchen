"""Shared OIDC route mechanics; each API mounts only its own authorization boundary."""

import hmac
import json
import logging
import secrets
import time
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from kitchen_core import auth, oidc
from kitchen_core.auth_schemas import (
    AdminPrincipal,
    AuthConfig,
    CallbackQuery,
    DevelopmentPhoneLogin,
    MobileExchange,
    MobileSessionResult,
    MobileStart,
    MobileStartResult,
    UserIdentity,
)
from kitchen_core.errors import DomainError
from kitchen_core.settings import get_settings
from kitchen_http.auth import (
    DB,
    Admin,
    CurrentUser,
    request_token,
    validate_logout,
)
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def cookie(response: Response, kind: auth.Kind, cookie_type: str, value: str, ttl: int) -> None:
    response.set_cookie(
        auth.cookie_name(kind, cookie_type),
        value,
        max_age=ttl,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )


def build_auth_router(kind: auth.Kind) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=[f"{kind}-authentication"])

    @router.get("/config", response_model=AuthConfig)
    def config() -> AuthConfig:
        settings = get_settings()
        providers = []
        if auth.oidc_configured(kind):
            providers = [
                provider
                for provider in ("google", "github")
                if getattr(settings, f"oidc_{provider}_idp_id")
            ]
        return AuthConfig(
            enabled=auth.configured(kind),
            providers=providers,
            phone_login_enabled=auth.development_phone_login_enabled(kind),
        )

    @router.get("/login", status_code=302, response_class=RedirectResponse)
    def login(
        register: bool = False,
        reauthenticate: bool = False,
        provider: Literal["google", "github"] | None = None,
        mobile_request: str | None = None,
    ) -> RedirectResponse:
        auth.require_oidc_config(kind)
        try:
            location, flow = auth.start(
                kind, register=register, reauthenticate=reauthenticate, provider=provider
            )
            redis = auth.get_redis()
            if mobile_request is not None:
                if kind != "user" or not auth.TOKEN.fullmatch(mobile_request):
                    raise oidc.OIDCError("Invalid mobile sign-in request")
                mobile_raw = cast(
                    bytes | None, redis.getdel(auth.key("user", "mobile", mobile_request))
                )
                if not mobile_raw:
                    raise oidc.OIDCError("Expired mobile sign-in request")
                mobile = json.loads(mobile_raw)
                if mobile.get("policy") != auth.policy_key("user"):
                    raise oidc.OIDCError("Invalid mobile sign-in policy")
                flow["mobile_challenge"] = mobile["challenge"]
            redis.set(auth.key(kind, "flow", flow["state"]), json.dumps(flow), ex=auth.FLOW_TTL)
        except (oidc.OIDCError, RedisError, ValueError, KeyError, TypeError) as exc:
            raise DomainError(
                503, "login_unavailable", "Zitadel sign-in temporarily unavailable"
            ) from exc
        response = RedirectResponse(location, 302)
        cookie(response, kind, "state", flow["browser"], auth.FLOW_TTL)
        return response

    @router.get("/callback", status_code=302, response_class=RedirectResponse)
    def callback(
        request: Request, params: Annotated[CallbackQuery, Query()], session: DB
    ) -> RedirectResponse:
        auth.require_oidc_config(kind)
        settings = get_settings()
        bound_flow = False
        native_flow = False
        flow = {}
        try:
            state = params.state or ""
            redis = auth.get_redis()
            flow = oidc.consume_callback_flow(
                query_params=request.query_params,
                state=state,
                browser=request.cookies.get(auth.cookie_name(kind, "state"), ""),
                redis=redis,
                flow_key=auth.key(kind, "flow", state),
                policy=auth.policy_key(kind),
            )
            bound_flow = True
            native_flow = kind == "user" and "mobile_challenge" in flow
            # A native handoff creates its own session without replacing the browser login.
            if not native_flow:
                previous = request.cookies.get(auth.cookie_name(kind, "session"), "")
                if auth.TOKEN.fullmatch(previous):
                    auth.revoke_session(session, kind, previous)
            code = oidc.validate_callback_response(
                code=params.code,
                provider_error=params.error,
                issuer=params.iss,
                expected_issuer=settings.oidc_issuer_url,
            )
            record = auth.identity(kind, flow, code)
            # Admin and resident logins share the same application account.
            auth.save_user(session, record, update_contact=kind == "user")
            if native_flow:
                handoff = secrets.token_urlsafe(32)
                redis.set(
                    auth.key("user", "handoff", handoff),
                    json.dumps({"record": record, "challenge": flow["mobile_challenge"]}),
                    ex=60,
                )
                response = RedirectResponse(
                    settings.mobile_redirect_uri + "?" + urlencode({"code": handoff}), 302
                )
            else:
                token = auth.create_session(kind, record)
                origin = str(getattr(settings, f"{kind}_base_url")).rstrip("/")
                response = RedirectResponse(origin + ("/start" if kind == "admin" else "/"), 302)
                ttl = record.get("absolute_expires_at", record["expires_at"]) - int(time.time())
                cookie(response, kind, "session", token, ttl)
        except (
            oidc.OIDCError,
            RedisError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            # OIDCError messages are fixed local strings; other errors may contain secrets.
            reason = str(exc) if isinstance(exc, oidc.OIDCError) else type(exc).__name__
            logger.warning("%s sign-in callback failed: %s", kind, reason)
            session.rollback()
            if bound_flow and native_flow:
                destination = settings.mobile_redirect_uri + "?error=login_failed"
            else:
                destination = (
                    str(getattr(settings, f"{kind}_base_url")).rstrip("/")
                    + "/login?error=login_failed"
                )
            response = RedirectResponse(destination, 302)
            if bound_flow and not native_flow:
                cookie(response, kind, "session", "", 0)
        cookie(response, kind, "state", "", 0)
        return response

    @router.post("/logout", status_code=204, response_class=Response, response_model=None)
    def logout(request: Request, session: DB) -> Response:
        token, transport = request_token(request, kind)
        validate_logout(request, kind, token, transport)
        auth.revoke_session(session, kind, token)
        response = Response(status_code=204)
        cookie(response, kind, "session", "", 0)
        cookie(response, kind, "state", "", 0)
        return response

    if kind == "admin":

        @router.get("/me", response_model=AdminPrincipal)
        def admin_me(admin: Admin) -> AdminPrincipal:
            return admin
    else:

        @router.get("/me", response_model=UserIdentity)
        def me(request: Request, user: CurrentUser) -> UserIdentity:
            token, _ = request_token(request, "user")
            record = auth.renew_resident_session(token)
            return UserIdentity.model_validate(user).model_copy(
                update={"expires_at": record["expires_at"], "csrf_token": record["csrf_token"]}
            )

        @router.post("/mobile/start", response_model=MobileStartResult)
        def mobile_start(body: MobileStart) -> MobileStartResult:
            auth.require_oidc_config("user")
            request_id = secrets.token_urlsafe(32)
            try:
                auth.get_redis().set(
                    auth.key("user", "mobile", request_id),
                    json.dumps(
                        {"challenge": body.code_challenge, "policy": auth.policy_key("user")}
                    ),
                    ex=auth.FLOW_TTL,
                )
            except RedisError as exc:
                raise DomainError(
                    503, "login_unavailable", "Zitadel sign-in temporarily unavailable"
                ) from exc
            query = urlencode(
                {"mobile_request": request_id, "register": str(body.register_user).lower()}
            )
            return MobileStartResult(
                authorization_url=str(get_settings().user_base_url).rstrip("/")
                + "/api/v1/auth/login?"
                + query
            )

        @router.post("/mobile/exchange", response_model=MobileSessionResult)
        def mobile_exchange(body: MobileExchange, session: DB) -> MobileSessionResult:
            auth.require_oidc_config("user")
            try:
                redis = auth.get_redis()
                handoff_key = auth.key("user", "handoff", body.code)
                raw = cast(bytes | None, redis.get(handoff_key))
                if not raw:
                    raise DomainError(401, "invalid_handoff", "Please start sign-in again")
                handoff = json.loads(raw)
                if (
                    not hmac.compare_digest(
                        auth.pkce_challenge(body.code_verifier), handoff["challenge"]
                    )
                    or handoff["record"].get("policy") != auth.policy_key("user")
                    or redis.getdel(handoff_key) != raw
                ):
                    raise DomainError(401, "invalid_handoff", "Please start sign-in again")
                record = handoff["record"]
                user = auth.save_user(session, record)
                token = auth.create_session("user", record, transport="bearer")
                return MobileSessionResult(
                    session_token=token,
                    expires_at=record["expires_at"],
                    user=UserIdentity.model_validate(user),
                )
            except RedisError as exc:
                raise DomainError(
                    503, "sessions_unavailable", "Sign-in sessions temporarily unavailable"
                ) from exc
            except (ValueError, KeyError, TypeError, oidc.OIDCError) as exc:
                raise DomainError(401, "invalid_handoff", "Please start sign-in again") from exc

        @router.post("/mobile/phone", response_model=MobileSessionResult)
        def development_phone_login(
            body: DevelopmentPhoneLogin, session: DB
        ) -> MobileSessionResult:
            record = auth.development_phone_identity(body.phone)
            try:
                user = auth.save_user(session, record)
                token = auth.create_session("user", record, transport="bearer")
                return MobileSessionResult(
                    session_token=token,
                    expires_at=record["expires_at"],
                    user=UserIdentity.model_validate(user),
                )
            except oidc.OIDCError as exc:
                raise DomainError(
                    401, "account_unavailable", "This account is unavailable"
                ) from exc
            except RedisError as exc:
                raise DomainError(
                    503, "sessions_unavailable", "Sign-in sessions temporarily unavailable"
                ) from exc
            except SQLAlchemyError as exc:
                raise DomainError(
                    503, "accounts_unavailable", "Sign-in accounts temporarily unavailable"
                ) from exc

    return router
