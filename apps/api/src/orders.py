"""Resident and kitchen order HTTP endpoints."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from kitchen_core import orders
from kitchen_core.db import get_session
from kitchen_core.models import User
from kitchen_core.order_schemas import (
    FulfillmentGroup,
    OrderCreate,
    OrderOut,
    OrderPage,
    OrderReject,
)
from kitchen_http.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(tags=["orders"])
Database = Annotated[Session, Depends(get_session, scope="function")]
Resident = Annotated[User, Depends(require_user)]


@router.post("/orders", response_model=OrderOut, status_code=201)
def place_order(
    payload: OrderCreate,
    session: Database,
    user: Resident,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
):
    return orders.create_order(session, user, payload, idempotency_key)


@router.get("/orders", response_model=OrderPage)
def customer_orders(
    session: Database,
    user: Resident,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return orders.list_customer_orders(session, user, limit, offset)


@router.get("/kitchens/{kitchen_id}/orders", response_model=OrderPage)
def kitchen_orders(
    kitchen_id: UUID,
    session: Database,
    user: Resident,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return orders.list_kitchen_orders(session, user, kitchen_id, limit, offset)


@router.get("/orders/{order_id}", response_model=OrderOut)
def order_detail(order_id: UUID, session: Database, user: Resident):
    return orders.get_order(session, user, order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: UUID, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "cancel")


@router.post("/orders/{order_id}/accept", response_model=OrderOut)
def accept_order(order_id: UUID, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "accept")


@router.post("/orders/{order_id}/reject", response_model=OrderOut)
def reject_order(order_id: UUID, payload: OrderReject, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "reject", payload.reason)


@router.post("/orders/{order_id}/prepare", response_model=OrderOut)
def prepare_order(order_id: UUID, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "prepare")


@router.post("/orders/{order_id}/ready", response_model=OrderOut)
def ready_order(order_id: UUID, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "ready")


@router.post("/orders/{order_id}/complete", response_model=OrderOut)
def complete_order(order_id: UUID, session: Database, user: Resident):
    return orders.transition_order(session, user, order_id, "complete")


@router.post("/orders/{order_id}/report-payment", response_model=OrderOut)
def report_payment(order_id: UUID, session: Database, user: Resident):
    return orders.record_payment(session, user, order_id, "report")


@router.post("/orders/{order_id}/confirm-payment", response_model=OrderOut)
def confirm_payment(order_id: UUID, session: Database, user: Resident):
    return orders.record_payment(session, user, order_id, "confirm")


@router.get("/kitchens/{kitchen_id}/fulfillment-groups", response_model=list[FulfillmentGroup])
def kitchen_fulfillment_groups(
    kitchen_id: UUID, service_date: date, session: Database, user: Resident
):
    return orders.fulfillment_groups(session, user, kitchen_id, service_date)
