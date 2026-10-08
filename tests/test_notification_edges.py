"""Device rebinding, notification privacy and invalid push-provider acknowledgements."""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from kitchen_core import db, settings
from kitchen_core.models import Device, Notification
from kitchen_http.auth import require_resident_session
from test_catalog import as_user
from test_catalog import market as market
from test_orders import order_seed as order_seed
from test_worker import dispatch
from test_worker import push_setup as push_setup


def test_devices_rebind_to_current_user_and_reactivate(client, session, market):
    client.app.dependency_overrides[require_resident_session] = lambda: SimpleNamespace(
        session_key="session-one"
    )
    as_user(client, market["customer"])
    body = {"push_token": "ExpoPushToken[rebind]", "platform": "android"}
    first = client.post("/api/v1/devices", json=body)
    assert first.status_code == 200, first.text
    device_id = first.json()["id"]
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 204
    client.app.dependency_overrides[require_resident_session] = lambda: SimpleNamespace(
        session_key="session-two"
    )
    as_user(client, market["owner"])
    rebound = client.post("/api/v1/devices", json={**body, "platform": "ios"})
    assert rebound.json() == {"id": device_id, "platform": "ios", "is_active": True}
    session.expire_all()
    device = session.get(Device, UUID(device_id))
    assert device.user_id == market["owner"].id and device.session_key == "session-two"
    as_user(client, market["customer"])
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 404
    assert client.delete(f"/api/v1/devices/{uuid4()}").status_code == 404
    assert client.post(f"/api/v1/notifications/{uuid4()}/read").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"data": [{"status": "ok", "id": ""}]},
        {"data": [{"status": "error", "details": "invalid"}]},
        {"data": [None]},
        {"data": []},
        {"data": {}},
    ],
)
def test_invalid_push_tickets_retry_without_disabling_device(session_factory, push_setup, body):
    sent = []

    def send(request):
        sent.append(request)
        return httpx.Response(200, json=body)

    assert dispatch(session_factory, send) == 1
    assert len(sent) == 1

    with session_factory() as session:
        row = session.get(Notification, push_setup["notification"])
        assert row.dispatched_at is None and row.attempts == 1
        assert session.get(Device, push_setup["device"]).is_active


def test_worker_module_entrypoint_runs_a_cycle_and_polls(monkeypatch):
    class StopWorker(BaseException):
        pass

    factory = MagicMock()
    factory.begin.return_value.__enter__.return_value.scalars.return_value.all.return_value = []
    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        settings, "get_settings", lambda: SimpleNamespace(push_enabled=False, worker_poll_seconds=1)
    )
    import time

    sleep = MagicMock(side_effect=StopWorker)
    monkeypatch.setattr(time, "sleep", sleep)
    path = Path(__file__).parents[1] / "apps/worker/src/main.py"
    with pytest.raises(StopWorker):
        run_path(str(path), run_name="__main__")
    assert factory.begin.call_count == 2
    sleep.assert_called_once_with(1)
