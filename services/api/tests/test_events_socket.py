"""The live event socket end to end, in process: the token comes in the first message and never in the URL, and a
user scoped to a department receives only the events about that department's cameras. The bus and the database
are fakes; tokens are made and checked by the real auth code."""
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sentinel_api import bus
from sentinel_api.auth import User, create_token
from sentinel_api.routers import alerts

EVENTS = [{"type": "sighting.new", "sighting": {"camera_code": "AMD-AMC-001"}},
          {"type": "sighting.new", "sighting": {"camera_code": "GNR-GSRTC-001"}},
          {"type": "camera.health", "camera_code": "GNR-GSRTC-002", "to": "offline"}]   # the last event, for everyone


def user(name, permissions, department_id=None):
    return User(id=uuid4(), username=name, full_name=name, role="test", permissions=permissions,
                department_id=department_id)


@pytest.fixture
def socket(monkeypatch):
    users = {}

    async def load_user(conn, sub):
        return users.get(sub)

    class Conn:
        async def fetch(self, sql, *params):        # the scope query: the department's cameras
            return [{"camera_code": "GNR-GSRTC-001"}, {"camera_code": "GNR-GSRTC-002"}]

    class Acquire:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *exc):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    async def subscribe():
        for e in EVENTS:
            yield json.dumps(e)

    monkeypatch.setattr(alerts, "load_user", load_user)
    monkeypatch.setattr(alerts, "pool", lambda: Pool())
    monkeypatch.setattr(alerts, "AUTH_WAIT_S", 0.5)
    monkeypatch.setattr(bus, "subscribe", subscribe)
    app = FastAPI()
    app.include_router(alerts.router)

    def token_for(u: User) -> str:
        users[str(u.id)] = u
        return create_token(u)
    return TestClient(app), token_for


def closed_with(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as e:
        ws.receive_text()
    return e.value.code


def test_a_token_in_the_url_is_not_accepted(socket):
    client, token_for = socket
    with client.websocket_connect(f"/ws/events?token={token_for(user('admin', ['*']))}") as ws:
        assert closed_with(ws) == 4401


def test_a_bad_token_or_a_missing_permission_is_refused(socket):
    client, token_for = socket
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": "not-a-token"}))
        assert closed_with(ws) == 4401
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token_for(user("nodal", ["cameras.read"]))}))
        assert closed_with(ws) == 4403


def test_a_statewide_user_receives_every_event(socket):
    client, token_for = socket
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token_for(user("admin", ["*"]))}))
        got = [json.loads(ws.receive_text()) for _ in EVENTS]
    assert got == EVENTS


def test_a_department_user_receives_only_its_cameras_events(socket):
    client, token_for = socket
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token_for(user("gsrtc", ["alerts.read"], department_id=7))}))
        got = [json.loads(ws.receive_text()) for _ in range(2)]
    assert got == EVENTS[1:]          # the Municipal camera's sighting never arrived
