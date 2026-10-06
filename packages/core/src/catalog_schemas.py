"""Typed contracts for society onboarding, kitchens and dated food listings."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
    model_validator,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def database_text(cls, value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Text cannot contain a null character.")
        return value


class TowerCreate(StrictRequest):
    name: str = Field(min_length=1, max_length=100)


class SocietyCreate(StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    towers: list[TowerCreate] = Field(default_factory=list, max_length=100)


class SocietyUpdate(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)


class TowerOut(BaseModel):
    id: UUID
    society_id: UUID
    name: str


class SocietyOut(BaseModel):
    id: UUID
    name: str
    address: str
    city: str
    postal_code: str
    status: str
    towers: list[TowerOut]


class SocietyPage(BaseModel):
    items: list[SocietyOut]
    total: int
    limit: int
    offset: int


class MembershipJoin(StrictRequest):
    tower_id: UUID
    flat: str = Field(min_length=1, max_length=50)


class MembershipOut(BaseModel):
    id: UUID
    society_id: UUID
    user_id: UUID
    society_name: str
    tower_id: UUID
    tower_name: str
    flat: str
    status: str


class MembershipAdminOut(MembershipOut):
    user_name: str | None
    phone: str | None


class MembershipPage(BaseModel):
    items: list[MembershipAdminOut]
    total: int
    limit: int
    offset: int


class KitchenCreate(StrictRequest):
    society_id: UUID
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    pickup_enabled: bool = True
    delivery_enabled: bool = False
    delivery_fee_paise: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    upi_id: str | None = Field(
        default=None, max_length=150, pattern=r"^[A-Za-z0-9._-]{2,}@[A-Za-z0-9.-]{2,}$"
    )
    fssai_number: str | None = Field(default=None, pattern=r"^\d{14}$")

    @model_validator(mode="after")
    def fulfillment_available(self):
        if not self.pickup_enabled and not self.delivery_enabled:
            raise ValueError("Enable pickup or delivery.")
        return self


class KitchenUpdate(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    pickup_enabled: bool | None = None
    delivery_enabled: bool | None = None
    delivery_fee_paise: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)
    upi_id: str | None = Field(
        default=None, max_length=150, pattern=r"^[A-Za-z0-9._-]{2,}@[A-Za-z0-9.-]{2,}$"
    )
    fssai_number: str | None = Field(default=None, pattern=r"^\d{14}$")


class KitchenApprove(StrictRequest):
    fssai_number: str = Field(pattern=r"^\d{14}$")


class KitchenOut(BaseModel):
    id: UUID
    society_id: UUID
    name: str
    description: str | None
    tower_name: str
    pickup_enabled: bool
    delivery_enabled: bool
    delivery_fee_paise: int
    status: str
    fssai_number: str | None


class KitchenOwnOut(KitchenOut):
    tower_id: UUID
    flat: str
    upi_id: str | None


class KitchenPage(BaseModel):
    items: list[KitchenOut]
    total: int
    limit: int
    offset: int


class KitchenAdminPage(BaseModel):
    items: list[KitchenOwnOut]
    total: int
    limit: int
    offset: int


class PhotoRequest(StrictRequest):
    @field_validator("image_url", check_fields=False)
    @classmethod
    def https_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = TypeAdapter(HttpUrl).validate_python(value)
        if url.scheme != "https" or url.username or url.password:
            raise ValueError("Use an HTTPS photo URL without embedded credentials.")
        return str(url)


class DishCreate(PhotoRequest):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=2048)


class DishUpdate(PhotoRequest):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=2048)


class DishOut(BaseModel):
    id: UUID
    kitchen_id: UUID
    name: str
    description: str | None
    image_url: str | None
    is_active: bool


class ListingCreate(StrictRequest):
    dish_id: UUID
    service_date: date
    available_from: AwareDatetime
    available_until: AwareDatetime
    order_cutoff: AwareDatetime
    price_paise: int = Field(gt=0, le=10_000_000, strict=True)
    quantity_total: int = Field(gt=0, le=10_000, strict=True)
    pickup_enabled: bool = True
    delivery_enabled: bool = False
    status: Literal["draft", "published"] = "published"


class ListingUpdate(StrictRequest):
    service_date: date | None = None
    available_from: AwareDatetime | None = None
    available_until: AwareDatetime | None = None
    order_cutoff: AwareDatetime | None = None
    price_paise: int | None = Field(default=None, gt=0, le=10_000_000, strict=True)
    quantity_total: int | None = Field(default=None, gt=0, le=10_000, strict=True)
    pickup_enabled: bool | None = None
    delivery_enabled: bool | None = None
    status: Literal["draft", "published", "cancelled"] | None = None


class ListingOut(BaseModel):
    id: UUID
    kitchen: KitchenOut
    dish: DishOut
    service_date: date
    available_from: datetime
    available_until: datetime
    order_cutoff: datetime
    price_paise: int
    quantity_total: int
    quantity_remaining: int
    pickup_enabled: bool
    delivery_enabled: bool
    delivery_fee_paise: int
    status: str
    is_orderable: bool


class ListingPage(BaseModel):
    items: list[ListingOut]
    total: int
    limit: int
    offset: int


class MessageOut(BaseModel):
    message: str
