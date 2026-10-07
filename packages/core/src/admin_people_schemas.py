"""Platform-admin contracts without provider-owned identity mutation."""

from datetime import datetime
from uuid import UUID

from kitchen_core.catalog_schemas import StrictRequest, ZoneType
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    phone: str | None
    is_active: bool
    created_at: datetime


class AdminUserUpdate(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=120)

    phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")

    @model_validator(mode="after")
    def provided_name(self):
        if not self.model_fields_set:
            raise ValueError("Provide a name or contact phone to update.")
        return self


class CommunityZoneUpdate(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_zone_id: UUID | None = None
    zone_type: ZoneType | None = None
    active: bool | None = None


class MembershipCreate(StrictRequest):
    user_id: UUID
    community_id: UUID
    zone_id: UUID | None = None
    address_label: str | None = Field(default=None, min_length=1, max_length=250)


class MembershipUpdate(StrictRequest):
    zone_id: UUID | None = None
    address_label: str | None = Field(default=None, min_length=1, max_length=250)

    @model_validator(mode="after")
    def provided_address(self):
        if not self.model_fields_set:
            raise ValueError("Provide a home zone or address to update.")
        return self
