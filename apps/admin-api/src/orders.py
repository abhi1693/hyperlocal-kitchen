"""Platform order administration using the shared inventory and state machine."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from kitchen_admin_api.dependencies import DB, Admin
from kitchen_admin_api.pagination import Listing, Page, paginate, record
from kitchen_core import orders as service
from kitchen_core.admin_order_schemas import AdminOrderCreate, OrderStatus
from kitchen_core.models import Kitchen, Order, User
from kitchen_core.order_schemas import (
    FulfillmentGroup,
    OrderCreate,
    OrderOut,
    OrderReject,
    PaymentStatus,
    PrepSummary,
)
from kitchen_http.auth import require_admin
from sqlalchemy import String, cast, or_, select

router = APIRouter(tags=["admin-orders"], dependencies=[Depends(require_admin)])


@router.get("/orders", response_model=Page[OrderOut], operation_id="admin_orders_list")
def list_orders(
    session: DB,
    query: Listing,
    customer_id: UUID | None = None,
    kitchen_id: UUID | None = None,
    community_id: UUID | None = None,
    status: OrderStatus | None = None,
    payment_status: PaymentStatus | None = None,
):
    statement = (
        select(Order)
        .join(User, User.id == Order.customer_id)
        .join(Kitchen, Kitchen.id == Order.kitchen_id)
    )
    if query.q:
        number_query = query.q[1:] if query.q.startswith("#") and query.q[1:].isdigit() else query.q
        statement = statement.where(
            or_(
                cast(Order.order_number, String).icontains(number_query, autoescape=True),
                User.name.icontains(query.q, autoescape=True),
                Kitchen.name.icontains(query.q, autoescape=True),
            )
        )
    for column, value in (
        (Order.customer_id, customer_id),
        (Order.kitchen_id, kitchen_id),
        (Order.community_id, community_id),
        (Order.status, status),
        (Order.payment_status, payment_status),
    ):
        if value is not None:
            statement = statement.where(column == value)
    result = paginate(
        session,
        statement,
        query,
        {
            "created_at": Order.created_at,
            "order_number": Order.order_number,
            "customer_name": User.name,
            "kitchen_name": Kitchen.name,
            "status": Order.status,
            "payment_status": Order.payment_status,
            "total_paise": Order.total_paise,
        },
        default="-created_at",
    )
    result["items"] = [service.serialize_order(session, order) for order in result["items"]]
    return result


@router.get("/orders/{order_id}", response_model=OrderOut, operation_id="admin_order_get")
def order_detail(order_id: UUID, session: DB):
    return service.get_order(session, None, order_id, admin=True)


@router.post("/orders", response_model=OrderOut, status_code=201, operation_id="admin_order_create")
def create_order(
    payload: AdminOrderCreate,
    session: DB,
    admin: Admin,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
):
    customer = record(session, User, payload.customer_id)
    request = OrderCreate.model_validate(payload.model_dump(exclude={"customer_id"}))
    return service.create_order(session, customer, request, idempotency_key, admin=True)


@router.post(
    "/orders/{order_id}/accept", response_model=OrderOut, operation_id="admin_order_accept"
)
def accept_order(order_id: UUID, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "accept", admin=True)


@router.post(
    "/orders/{order_id}/reject", response_model=OrderOut, operation_id="admin_order_reject"
)
def reject_order(order_id: UUID, payload: OrderReject, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "reject", payload.reason, admin=True)


@router.post(
    "/orders/{order_id}/prepare", response_model=OrderOut, operation_id="admin_order_prepare"
)
def prepare_order(order_id: UUID, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "prepare", admin=True)


@router.post("/orders/{order_id}/ready", response_model=OrderOut, operation_id="admin_order_ready")
def ready_order(order_id: UUID, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "ready", admin=True)


@router.post(
    "/orders/{order_id}/complete", response_model=OrderOut, operation_id="admin_order_complete"
)
def complete_order(order_id: UUID, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "complete", admin=True)


@router.post(
    "/orders/{order_id}/cancel", response_model=OrderOut, operation_id="admin_order_cancel"
)
def cancel_order(order_id: UUID, session: DB, admin: Admin):
    return service.transition_order(session, None, order_id, "cancel", admin=True)


@router.post(
    "/orders/{order_id}/report-payment",
    response_model=OrderOut,
    operation_id="admin_order_report_payment",
)
def report_payment(order_id: UUID, session: DB, admin: Admin):
    return service.record_payment(session, None, order_id, "report", admin=True)


@router.post(
    "/orders/{order_id}/confirm-payment",
    response_model=OrderOut,
    operation_id="admin_order_confirm_payment",
)
def confirm_payment(order_id: UUID, session: DB, admin: Admin):
    return service.record_payment(session, None, order_id, "confirm", admin=True)


@router.get(
    "/kitchens/{kitchen_id}/prep-summary",
    response_model=PrepSummary,
    operation_id="admin_kitchen_prep_summary",
)
def kitchen_prep_summary(kitchen_id: UUID, on: Annotated[date, Query(alias="date")], session: DB):
    return service.prep_summary(session, None, kitchen_id, on, admin=True)


@router.get(
    "/kitchens/{kitchen_id}/fulfillment-groups",
    response_model=list[FulfillmentGroup],
    operation_id="admin_kitchen_fulfillment_groups",
)
def kitchen_fulfillment_groups(kitchen_id: UUID, service_date: date, session: DB):
    return service.fulfillment_groups(session, None, kitchen_id, service_date, admin=True)
