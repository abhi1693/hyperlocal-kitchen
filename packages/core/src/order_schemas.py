"""Request and response contracts for direct-payment food orders."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from kitchen_core.catalog_schemas import StrictRequest
from pydantic import BaseModel, Field, model_validator

FulfillmentType = Literal["pickup", "delivery"]
PaymentStatus = Literal["unpaid", "customer_reported", "kitchen_confirmed"]


class OrderItemCreate(StrictRequest):
    menu_listing_id: UUID
    quantity: int = Field(gt=0, le=100, strict=True)


class DeliveryAddress(StrictRequest):
    zone_id: UUID | None = None
    address_label: str = Field(min_length=1, max_length=250)


class OrderCreate(StrictRequest):
    pickup_point_id: UUID | None = None
    delivery_address: DeliveryAddress | None = None
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)
    fulfillment_type: FulfillmentType = "pickup"
    customer_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def destination(self):
        if self.fulfillment_type == "delivery" and self.pickup_point_id is not None:
            raise ValueError("Delivery cannot select a pickup point.")
        if self.fulfillment_type == "pickup" and self.delivery_address is not None:
            raise ValueError("Pickup cannot include a delivery address.")
        return self


class OrderReject(StrictRequest):
    reason: str = Field(min_length=1, max_length=300)


class OrderItemOut(BaseModel):
    menu_listing_id: UUID
    dish_name: str
    unit_price_paise: int
    quantity: int
    total_paise: int


class AddressSnapshot(BaseModel):
    version: int = 2
    community_name: str
    address: str | None = None
    city: str
    postal_code: str | None = None
    zone_name: str | None = None
    address_label: str | None = None
    name: str | None = None
    instructions: str | None = None


class OrderEventOut(BaseModel):
    status: str
    reason: str | None
    created_at: datetime


class OrderOut(BaseModel):
    id: UUID
    order_number: int
    community_id: UUID
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
    pickup_point_id: UUID | None
    fulfillment_snapshot: AddressSnapshot
    pickup_address: AddressSnapshot | None
    delivery_address: AddressSnapshot | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    events: list[OrderEventOut]


class OrderPage(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int


class FulfillmentGroup(BaseModel):
    fulfillment_type: FulfillmentType
    pickup_point_id: UUID | None
    fulfillment_snapshot: AddressSnapshot
    available_from: datetime
    available_until: datetime
    order_count: int
    portion_count: int
    order_ids: list[UUID]
