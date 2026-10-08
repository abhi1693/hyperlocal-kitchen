from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserIdentity(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    phone: str | None = None
    name: str | None = None
    expires_at: int | None = None
    csrf_token: str | None = None


class AuthConfig(BaseModel):
    enabled: bool
    providers: list[Literal["google", "github"]] = []
    phone_login_enabled: bool = False


class AdminPrincipal(BaseModel):
    subject: str
    issuer: str
    organization_id: str
    roles: list[str]
    name: str | None = None
    email: str | None = None
    expires_at: int
    csrf_token: str


class ResidentSession(BaseModel):
    user_id: UUID
    subject: str
    issuer: str
    organization_id: str
    expires_at: int
    absolute_expires_at: int
    renewed_at: int
    csrf_token: str
    policy: str
    transport: Literal["cookie", "bearer"]
    session_key: str


class CallbackQuery(BaseModel):
    state: str | None = None
    code: str | None = None
    error: str | None = None
    iss: str | None = None


class MobileStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    register_user: bool = Field(default=False, alias="register")


class MobileStartResult(BaseModel):
    authorization_url: str


class DevelopmentPhoneLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class MobileExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    code_verifier: str = Field(pattern=r"^[A-Za-z0-9._~-]{43,128}$")


class MobileSessionResult(BaseModel):
    session_token: str
    expires_at: int
    user: UserIdentity
