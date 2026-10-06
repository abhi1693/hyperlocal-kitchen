import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Lock
from uuid import UUID

import httpx
import pytest
from kitchen_core import auth
from kitchen_core.models import Device, MenuListing, Notification, Order, User
from kitchen_core.orders import transition_order
from kitchen_core.settings import get_settings
from kitchen_worker import main as worker
from kitchen_worker.main import dispatch_notifications, expire_pending
from redis.exceptions import RedisError
from sqlalchemy import delete, select, text
from test_orders import order_seed as order_seed
from test_orders import place


class SessionStore:
    def __init__(self):
        self.records = {}
        self.unavailable = False

    def get(self, key):
        if self.unavailable:
            raise RedisError("Session store temporarily unavailable")
        return self.records.get(key)


@pytest.fixture
def push_setup(session_factory, order_seed, monkeypatch):
    monkeypatch.setenv("KITCHEN_PUSH_ENABLED", "true")
    get_settings.cache_clear()
    store = SessionStore()
    monkeypatch.setattr(auth, "get_redis", lambda: store)
    seed = order_seed
    order = place(session_factory, seed)
    session_key = auth.key("user", "session", "w" * 43)
    now = int(time.time())
    record = {
        "policy": auth.policy_key("user"),
        "user_id": str(seed["owner"]),
        "expires_at": now + 1000,
        "absolute_expires_at": now + 2000,
    }
    store.records[session_key] = json.dumps(record).encode()
    with session_factory() as session:
        device = Device(
            user_id=seed["owner"],
            session_key=session_key,
            push_token="ExpoPushToken[worker_one]",
            platform="android",
        )
        session.add(device)
        session.flush()
        notification = session.scalar(select(Notification).where(Notification.order_id == order.id))
        ids = {"device": device.id, "notification": notification.id}
        session.commit()
    return {"seed": seed, "store": store, "key": session_key, "record": record, **ids}


def dispatch(session_factory, handler):
    with (
        session_factory() as session,
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
    ):
        count = dispatch_notifications(session, client)
        session.commit()
        return count


def test_worker_expires_only_pending_and_releases_once(session_factory, order_seed):
    seed = order_seed
    pending = place(session_factory, seed)
    accepted = place(session_factory, seed)
    with session_factory() as session:
        transition_order(session, session.get(User, seed["owner"]), accepted.id, "accept")
        for order_id in (pending.id, accepted.id):
            session.get(Order, order_id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with session_factory() as session:
        assert expire_pending(session) == 1
        assert expire_pending(session) == 0
        session.commit()
    with session_factory() as session:
        assert session.get(Order, pending.id).status == "expired"
        assert session.get(Order, accepted.id).status == "accepted"
        assert session.get(MenuListing, seed["listing"]).quantity_reserved == 2


def test_push_uses_current_session_and_contains_no_food_or_address_data(
    session_factory, push_setup
):
    sent = []

    def send(request):
        sent.extend(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"status": "ok", "id": "receipt-one"}]})

    assert dispatch(session_factory, send) == 1
    assert len(sent) == 1
    assert sent[0]["to"] == "ExpoPushToken[worker_one]"
    assert set(sent[0]["data"]) == {"order_id", "notification_id"}
    assert "Rajma" not in json.dumps(sent)
    assert "B-101" not in json.dumps(sent)
    with session_factory() as session:
        row = session.get(Notification, push_setup["notification"])
        assert row.dispatched_at is not None
        assert row.attempts == 1


@pytest.mark.parametrize("invalid", ["revoked", "expired", "wrong_user", "old_policy"])
def test_push_does_not_reach_invalid_or_other_user_session(session_factory, push_setup, invalid):
    setup = push_setup
    record = dict(setup["record"])
    if invalid == "revoked":
        setup["store"].records.pop(setup["key"])
    else:
        if invalid == "expired":
            record["expires_at"] = int(time.time()) - 1
        elif invalid == "wrong_user":
            record["user_id"] = str(setup["seed"]["customer"])
        else:
            record["policy"] = "outdated-policy"
        setup["store"].records[setup["key"]] = json.dumps(record).encode()

    def should_not_send(request):
        pytest.fail("Invalid sessions must never receive a push")

    assert dispatch(session_factory, should_not_send) == 1
    with session_factory() as session:
        assert session.get(Notification, setup["notification"]).dispatched_at is not None


def test_redis_outage_retains_notification_for_retry(session_factory, push_setup):
    push_setup["store"].unavailable = True

    def should_not_send(request):
        pytest.fail("An unavailable session store must fail closed")

    assert dispatch(session_factory, should_not_send) == 1
    with session_factory() as session:
        row = session.get(Notification, push_setup["notification"])
        assert row.dispatched_at is None
        assert row.attempts == 1
        assert row.next_attempt_at > datetime.now(UTC)


def test_inactive_account_does_not_receive_push_with_still_valid_session(
    session_factory, push_setup
):
    with session_factory() as session:
        session.get(User, push_setup["seed"]["owner"]).is_active = False
        session.commit()

    def should_not_send(request):
        pytest.fail("Inactive accounts must never receive a push")

    assert dispatch(session_factory, should_not_send) == 1
    with session_factory() as session:
        assert session.get(Device, push_setup["device"]).is_active
        assert session.get(Notification, push_setup["notification"]).dispatched_at is not None


@pytest.mark.parametrize(
    "response",
    [
        [],
        {"data": [{}]},
        {"data": [{"status": "unknown"}]},
        {"data": [{"status": "ok", "id": ""}]},
        {"data": [{"status": "error", "details": None}]},
        {"data": [{"status": "error", "details": {"error": "MessageRateExceeded"}}]},
    ],
)
def test_failed_or_malformed_provider_results_are_retried(session_factory, push_setup, response):
    assert dispatch(session_factory, lambda request: httpx.Response(200, json=response)) == 1
    with session_factory() as session:
        row = session.get(Notification, push_setup["notification"])
        assert row.dispatched_at is None
        assert row.next_attempt_at > datetime.now(UTC)


def test_invalid_device_is_disabled_without_retrying_successful_delivery(
    session_factory, push_setup
):
    response = {"data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]}
    assert dispatch(session_factory, lambda request: httpx.Response(200, json=response)) == 1
    with session_factory() as session:
        assert not session.get(Device, push_setup["device"]).is_active
        assert session.get(Notification, push_setup["notification"]).dispatched_at is not None


def test_device_account_rebind_waits_for_in_flight_dispatch(session_factory, push_setup):
    sending = Event()
    release_send = Event()
    attempting_rebind = Event()
    rebound = Event()

    def send(request):
        sending.set()
        assert release_send.wait(timeout=5)
        return httpx.Response(200, json={"data": [{"status": "ok", "id": "receipt-one"}]})

    def rebind():
        assert sending.wait(timeout=5)
        with session_factory() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            attempting_rebind.set()
            device = session.scalar(
                select(Device).where(Device.id == push_setup["device"]).with_for_update()
            )
            device.user_id = push_setup["seed"]["customer"]
            device.session_key = auth.key("user", "session", "r" * 43)
            session.commit()
            rebound.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        dispatch_future = executor.submit(dispatch, session_factory, send)
        rebind_future = executor.submit(rebind)
        try:
            assert attempting_rebind.wait(timeout=5)
            assert not rebound.wait(timeout=0.1)
        finally:
            release_send.set()
        assert dispatch_future.result(timeout=10) == 1
        rebind_future.result(timeout=10)
        assert rebound.is_set()


def test_disabled_push_preserves_notification_without_outbound_calls(
    session_factory, push_setup, monkeypatch
):
    monkeypatch.setenv("KITCHEN_PUSH_ENABLED", "false")
    get_settings.cache_clear()

    def should_not_send(request):
        pytest.fail("Push is disabled")

    assert dispatch(session_factory, should_not_send) == 0
    with session_factory() as session:
        row = session.get(Notification, push_setup["notification"])
        assert row.dispatched_at is None
        assert row.attempts == 0


def test_workers_commit_device_locks_between_opposite_recipient_notifications(
    session_factory, push_setup, monkeypatch
):
    setup = push_setup
    customer = setup["seed"]["customer"]
    customer_session = auth.key("user", "session", "c" * 43)
    setup["store"].records[customer_session] = json.dumps(
        setup["record"] | {"user_id": str(customer)}
    ).encode()
    with session_factory.begin() as session:
        original = session.get(Notification, setup["notification"])
        order_id = original.order_id
        session.execute(delete(Notification))
        session.add(
            Device(
                user_id=customer,
                session_key=customer_session,
                push_token="ExpoPushToken[worker_two]",
                platform="ios",
            )
        )
        # With the old 20-row claims, worker one holds A and next needs B;
        # worker two holds B and next needs A. With single-row claims, their
        # first sends are still A/B, but both locks are committed before reuse.
        owner = setup["seed"]["owner"]
        recipients = [owner, customer] + [owner] * 18 + [customer, owner] + [customer] * 18
        notification_ids = [UUID(int=index) for index in range(1, 41)]
        for identifier, recipient in zip(notification_ids, recipients, strict=True):
            session.add(
                Notification(
                    id=identifier,
                    user_id=recipient,
                    order_id=order_id,
                    kind="order_pending",
                    payload={},
                )
            )

    first_sends = Barrier(2)
    first_send_started = Event()
    sent = []
    sent_lock = Lock()
    real_client = httpx.Client

    def push_client(**kwargs):
        first = True

        def send(request):
            nonlocal first
            messages = json.loads(request.content)
            with sent_lock:
                sent.extend(messages)
            if first:
                first = False
                first_send_started.set()
                # Each worker already owns its recipient's real PostgreSQL
                # device row lock here; no scheduling delay is simulated.
                first_sends.wait(timeout=5)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"status": "ok", "id": "receipt-" + message["data"]["notification_id"]}
                        for message in messages
                    ]
                },
            )

        return real_client(transport=httpx.MockTransport(send), **kwargs)

    monkeypatch.setattr(worker, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(worker.httpx, "Client", push_client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_worker = executor.submit(worker.run_once)
        try:
            assert first_send_started.wait(timeout=5)
            second_worker = executor.submit(worker.run_once)
            first_worker.result(timeout=10)
            second_worker.result(timeout=10)
        finally:
            first_sends.abort()

    assert {message["to"] for message in sent[:2]} == {
        "ExpoPushToken[worker_one]",
        "ExpoPushToken[worker_two]",
    }
    assert len(sent) == 40
    assert {message["data"]["notification_id"] for message in sent} == {
        str(identifier) for identifier in notification_ids
    }
    with session_factory() as session:
        notifications = session.scalars(select(Notification)).all()
        assert len(notifications) == 40
        assert all(row.dispatched_at is not None and row.attempts == 1 for row in notifications)
