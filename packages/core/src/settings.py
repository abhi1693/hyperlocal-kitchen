from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KITCHEN_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "production"
    database_url: str = "postgresql+psycopg://kitchen:kitchen@localhost:5432/kitchen"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = []
    pending_order_minutes: int = Field(default=15, ge=1, le=60)
    worker_poll_seconds: int = Field(default=5, ge=1, le=60)
    push_enabled: bool = False
    oidc_issuer_url: str | None = None
    oidc_organization_id: str | None = None
    oidc_organization_scope_template: str = "urn:zitadel:iam:org:id:{organization_id}"
    oidc_organization_claim: str = "urn:zitadel:iam:user:resourceowner:id"
    oidc_roles_claim: str = "urn:zitadel:iam:org:project:roles"
    oidc_scopes: list[str] = ["openid", "profile", "email", "phone"]
    oidc_token_endpoint_auth_method: Literal[
        "none", "client_secret_basic", "client_secret_post"
    ] = "none"
    oidc_google_idp_id: str | None = None
    oidc_github_idp_id: str | None = None
    user_base_url: str | None = None
    user_oidc_client_id: str | None = None
    user_oidc_client_secret: SecretStr | None = None
    admin_base_url: str | None = None
    admin_oidc_client_id: str | None = None
    admin_oidc_client_secret: SecretStr | None = None
    admin_required_role: str = "platform_admin"
    cookie_secure: bool = True
    user_session_ttl_seconds: int = Field(default=30 * 86400, ge=300, le=90 * 86400)
    user_session_absolute_ttl_seconds: int = Field(default=90 * 86400, ge=300, le=90 * 86400)
    admin_session_ttl_seconds: int = Field(default=28800, ge=300, le=86400)
    mobile_redirect_uri: str = "hyperlocal-kitchen://auth/callback"

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("PostgreSQL with psycopg is required for inventory transactions")
        if not self.redis_url.startswith(("redis://", "rediss://")):
            raise ValueError("A Redis session store URL is required")
        if self.user_session_ttl_seconds > self.user_session_absolute_ttl_seconds:
            raise ValueError("Resident idle timeout cannot exceed the absolute session lifetime")
        for name in ("oidc_issuer_url", "user_base_url", "admin_base_url"):
            value = getattr(self, name)
            if not value:
                continue
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"{name} must be an absolute URL without credentials or query")
            if name == "oidc_issuer_url":
                if parsed.scheme == "http" and parsed.hostname not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    raise ValueError("OIDC issuer requires HTTPS except on loopback")
            elif parsed.path not in {"", "/"}:
                raise ValueError(f"{name} must be an origin without a path")
            elif (parsed.scheme == "https") != self.cookie_secure:
                raise ValueError(
                    "HTTPS origins require secure cookies; HTTP development disables them"
                )
            if self.environment == "production" and parsed.scheme != "https":
                raise ValueError("Production authentication requires HTTPS")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("Production requires secure authentication cookies")
        if self.user_oidc_client_id and self.user_oidc_client_id == self.admin_oidc_client_id:
            raise ValueError("Residents and administrators require distinct Zitadel applications")
        if not self.admin_required_role or any(char.isspace() for char in self.admin_required_role):
            raise ValueError("Administrator role must be an exact role key")
        if self.oidc_organization_id and any(char.isspace() for char in self.oidc_organization_id):
            raise ValueError("Organization ID cannot contain whitespace")
        redirect = urlsplit(self.mobile_redirect_uri)
        if (
            redirect.scheme != "hyperlocal-kitchen"
            or redirect.netloc != "auth"
            or redirect.path != "/callback"
            or redirect.query
            or redirect.fragment
        ):
            raise ValueError("Mobile redirect must be the registered app callback")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
