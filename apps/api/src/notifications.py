from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from kitchen_core.auth_schemas import ResidentSession
from kitchen_core.db import get_session
from kitchen_core.errors import DomainError
from kitchen_core.models import Device, Notification, User, utcnow
from kitchen_http.auth import require_resident_session, require_user
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(tags=["Notifications"])
DB = Annotated[Session, Depends(get_session, scope="function")]
Actor = Annotated[User, Depends(require_user)]


class DeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    push_token: str = Field(
        pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$", max_length=250
    )
    platform: Literal["android", "ios"]


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    platform: str
    is_active: bool


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_id: UUID
    kind: str
    payload: dict
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationResponse]


@router.post("/devices", response_model=DeviceResponse)
def register_device(
    body: DeviceRequest,
    session: DB,
    user: Actor,
    auth_session: Annotated[ResidentSession, Depends(require_resident_session)],
):
    device = session.scalar(
        select(Device).where(Device.push_token == body.push_token).with_for_update()
    )
    if device is None:
        device = Device(
            user_id=user.id,
            session_key=auth_session.session_key,
            push_token=body.push_token,
            platform=body.platform,
        )
        session.add(device)
    else:
        # A device may move to a different signed-in account; never notify its former owner.
        device.user_id = user.id
        device.session_key = auth_session.session_key
        device.platform = body.platform
        device.is_active = True
    session.flush()
    return device


@router.delete("/devices/{device_id}", status_code=204)
def remove_device(device_id: UUID, session: DB, user: Actor):
    device = session.get(Device, device_id)
    if not device or device.user_id != user.id:
        raise DomainError(404, "device_not_found", "Device not found")
    device.is_active = False
    return Response(status_code=204)


@router.get("/notifications", response_model=NotificationPage)
def list_notifications(
    session: DB, user: Actor, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return NotificationPage(items=[NotificationResponse.model_validate(row) for row in rows])


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def read_notification(notification_id: UUID, session: DB, user: Actor):
    row = session.get(Notification, notification_id)
    if not row or row.user_id != user.id:
        raise DomainError(404, "notification_not_found", "Notification not found")
    row.read_at = row.read_at or utcnow()
    return row
