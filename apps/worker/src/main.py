import logging
import time
from datetime import timedelta

import httpx
from kitchen_core.auth import device_session_active
from kitchen_core.db import get_session_factory
from kitchen_core.models import Device, Notification, Order, User, utcnow
from kitchen_core.orders import expire_order
from kitchen_core.settings import get_settings
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def expire_pending(session: Session) -> int:
    now = utcnow()
    orders = session.scalars(
        select(Order)
        .where(Order.status == "pending", Order.expires_at <= now)
        .order_by(Order.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).all()
    return sum(expire_order(session, order, now=now) for order in orders)


def dispatch_notifications(session: Session, client: httpx.Client) -> int:
    """Claim one notification; the caller commits before claiming another recipient."""
    if not get_settings().push_enabled:
        return 0
    notifications = session.scalars(
        select(Notification)
        .where(
            Notification.dispatched_at.is_(None),
            Notification.next_attempt_at <= utcnow(),
        )
        .order_by(Notification.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).all()
    for notification in notifications:
        notification.attempts += 1
        try:
            # Rebinding a token to another account must wait until this send
            # finishes. All workers acquire a user's device locks in ID order.
            devices = session.scalars(
                select(Device)
                .join(User, User.id == Device.user_id)
                .where(
                    Device.user_id == notification.user_id,
                    Device.is_active.is_(True),
                    User.is_active.is_(True),
                )
                .order_by(Device.id)
                .with_for_update(of=Device)
                .execution_options(populate_existing=True)
            ).all()
            devices = [
                device
                for device in devices
                if device_session_active(device.session_key, device.user_id)
            ]
            if devices:
                messages = [
                    {
                        "to": device.push_token,
                        "title": "Kitchen order update",
                        "body": f"Order update: {notification.kind.replace('_', ' ')}",
                        "data": {
                            "order_id": str(notification.order_id),
                            "notification_id": str(notification.id),
                        },
                        "sound": "default",
                    }
                    for device in devices
                ]
                response = client.post(EXPO_PUSH_URL, json=messages)
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("Invalid push response")
                tickets = body.get("data", [])
                if not isinstance(tickets, list) or len(tickets) != len(devices):
                    raise ValueError("Invalid push response")
                retry = False
                for device, ticket in zip(devices, tickets, strict=True):
                    if not isinstance(ticket, dict) or ticket.get("status") not in ("ok", "error"):
                        raise ValueError("Invalid push ticket")
                    if ticket.get("status") == "ok":
                        receipt_id = ticket.get("id")
                        if not isinstance(receipt_id, str) or not receipt_id:
                            raise ValueError("Missing push receipt ID")
                    if ticket.get("status") == "error":
                        details = ticket.get("details", {})
                        if not isinstance(details, dict):
                            raise ValueError("Invalid push error details")
                        if details.get("error") == "DeviceNotRegistered":
                            device.is_active = False
                        else:
                            retry = True
                if retry:
                    raise ValueError("Push delivery was not accepted")
            notification.dispatched_at = utcnow()
        except (httpx.HTTPError, RedisError, ValueError):
            # Notification IDs let clients deduplicate at-least-once delivery.
            notification.next_attempt_at = utcnow() + timedelta(
                seconds=min(3600, 2 ** min(notification.attempts, 10))
            )
    return len(notifications)


def run_once() -> None:
    factory = get_session_factory()
    # Each expiry transaction holds only one order's inventory locks. Separate
    # workers cannot accumulate overlapping sets of listing locks in reverse order.
    for _ in range(100):
        with factory.begin() as session:
            expired = expire_pending(session)
        if not expired:
            break
    with httpx.Client(timeout=10) as client:
        # Device locks protect an in-flight send, but must not span recipients:
        # another worker may visit those recipients in the opposite order.
        for _ in range(20):
            with factory.begin() as session:
                dispatched = dispatch_notifications(session, client)
            if not dispatched:
                break


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            run_once()
        except Exception:
            # Do not log database parameters or outbound tokens.
            logger.error("Worker cycle failed; retrying on the next cycle")
        time.sleep(get_settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
