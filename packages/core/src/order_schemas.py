"""Request and response contracts for direct-payment food orders."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from kitchen_core.catalog_schemas import StrictRequest
from pydantic import BaseModel, Field

FulfillmentType = Literal["pickup", "delivery"]
PaymentStatus = Literal["unpaid", "customer_reported", "kitchen_confirmed"]


class OrderItemCreate(StrictRequest):
    menu_listing_id: UUID
    quantity: int = Field(gt=0, le=100, strict=True)


class OrderCreate(StrictRequest):
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)
    fulfillment_type: FulfillmentType = "pickup"
    customer_note: str | None = Field(default=None, max_length=500)


class OrderReject(StrictRequest):
    reason: str = Field(min_length=1, max_length=300)


class OrderItemOut(BaseModel):
    menu_listing_id: UUID
    dish_name: str
    unit_price_paise: int
    quantity: int
    total_paise: int


class AddressSnapshot(BaseModel):
    society_name: str
    address: str
    city: str
    postal_code: str
    tower_name: str
    flat: str


class OrderEventOut(BaseModel):
    status: str
    reason: str | None
    created_at: datetime


class OrderOut(BaseModel):
    id: UUID
    order_number: int
    society_id: UUID
    kitchen_id: UUID
    customer_id: UUID
    kitchen_name: str
    customer_name: str
    status: str
    payment_status: PaymentStatus
    payment_instructions: str = "Pay the kitchen directly by cash or UPI."
    upi_id: str | None
    fulfillment_type: FulfillmentType
    customer_note: str | None
    rejection_reason: str | None
    items: list[OrderItemOut]
    subtotal_paise: int
    delivery_fee_paise: int
    total_paise: int
    available_from: datetime
    available_until: datetime
    pickup_address: AddressSnapshot
    delivery_address: AddressSnapshot
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    events: list[OrderEventOut]


class OrderPage(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int
