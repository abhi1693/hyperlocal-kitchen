"""Platform administration contracts for the existing order workflow."""

from typing import Literal
from uuid import UUID

from kitchen_core.order_schemas import OrderCreate

OrderStatus = Literal[
    "pending", "accepted", "preparing", "ready", "completed", "rejected", "cancelled", "expired"
]


class AdminOrderCreate(OrderCreate):
    customer_id: UUID
