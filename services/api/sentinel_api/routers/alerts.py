"""Alerts: watchlist hits raised by the ingest path, acknowledged/closed by operators,
and pushed live to the control room over a WebSocket."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from .. import bus
from ..audit import audit
from ..auth import User, decode_token, load_user, require
from ..cameras_repo import scope_clause
from ..config import get_settings
from ..db import get_conn, pool, rows_to_dicts
from ..marking import needs_review
from ..schemas import AlertClose, AlertOut, AlertTags

router = APIRouter(tags=["alerts"])

ALERT_SELECT = """
SELECT a.id, a.watchlist_id, w.kind::text AS kind, w.subject_name, w.reason,
       a.camera_id, c.camera_code, c.name AS camera_name,
       ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon,
       a.sighting_id, a.sighting_ts, a.plate_norm, a.match_score, a.exact_match,
       a.severity::text, a.status::text, a.triggered_at, a.acknowledged_at, a.closed_at,
       a.disposition, w.plate_norm AS watch_plate, u.full_name AS acknowledged_by_name,
       a.retrospective, a.alert_type, a.detail, a.tags,
       (SELECT s.crop_path FROM vehicle_sightings s
         WHERE s.id = a.sighting_id AND s.event_ts = a.sighting_ts LIMIT 1) AS crop_path,
       (SELECT s.ocr_conf FROM vehicle_sightings s
         WHERE s.id = a.sighting_id AND s.event_ts = a.sighting_ts LIMIT 1) AS ocr_conf
FROM alerts a
JOIN cameras c ON c.id = a.camera_id
LEFT JOIN watchlist_entries w ON w.id = a.watchlist_id
LEFT JOIN users u ON u.id = a.acknowledged_by
"""
# Open alerts are worked in priority order; history reads newest first.
PRIORITY = "CASE a.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(status: Literal["new", "acknowledged", "closed", "false_positive", "all"] | None = Query("new"),
                      severity: Literal["low", "medium", "high", "critical"] | None = None,
                      tag: str | None = Query(None, max_length=32, description="only alerts carrying this tag"),
                      limit: int = Query(100, ge=0, le=1000),
                      user: User = Depends(require("alerts.read")),
                      conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    filters = [where]
    if status and status != "all":
        params.append(status)
        filters.append(f"a.status = ${len(params)}::alert_status")
    if severity:
        params.append(severity)
        filters.append(f"a.severity = ${len(params)}::severity_level")
    if tag:                      # tags compare ignoring case, as AlertTags de-duplicates them
        params.append(tag.strip().lower())
        filters.append(f"EXISTS (SELECT 1 FROM unnest(a.tags) t WHERE lower(t) = ${len(params)})")
    params.append(limit)
    order = f"{PRIORITY}, a.triggered_at DESC" if status == "new" else "a.triggered_at DESC"
    rows = await conn.fetch(f"{ALERT_SELECT} WHERE {' AND '.join(filters)} "
                            f"ORDER BY {order} LIMIT ${len(params)}", *params)
    return marked(rows_to_dicts(rows))


def marked(alerts: list[dict]) -> list[dict]:
    """The G3 mark on watchlist alerts (marking.py): a read below 0.9 or a one-character match. An intrusion alert
    has no read and is never marked. None throughout when marking is off (the shipped behaviour)."""
    on = get_settings().confidence_marking
    for a in alerts:
        a["needs_review"] = (needs_review(a.get("ocr_conf"), bool(a.get("exact_match", True)))
                             if on and a.get("alert_type") == "watchlist" else None)
    return alerts


@router.get("/alerts/summary")
async def summary(user: User = Depends(require("alerts.read")),
                  conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    row = await conn.fetchrow(
        f"""SELECT count(*) FILTER (WHERE a.status = 'new') AS new,
                   count(*) FILTER (WHERE a.status = 'acknowledged') AS acknowledged,
                   count(*) FILTER (WHERE a.triggered_at > now() - interval '24 hours') AS last_24h,
                   count(*) FILTER (WHERE a.severity IN ('high','critical') AND a.status = 'new')
                     AS open_high
            FROM alerts a JOIN cameras c ON c.id = a.camera_id WHERE {where}""", *params)
    return dict(row)


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def acknowledge(alert_id: UUID, request: Request,
                      user: User = Depends(require("alerts.ack")),
                      conn: asyncpg.Connection = Depends(get_conn)):
    await _in_scope(conn, user, alert_id)
    n = await conn.execute(
        """UPDATE alerts SET status = 'acknowledged', acknowledged_by = $2, acknowledged_at = now()
           WHERE id = $1 AND status = 'new'""", alert_id, user.id)
    if n.endswith(" 0"):
        raise HTTPException(409, "alert not in 'new' state")
    await audit(conn, request, user, "alert.ack", "alert", alert_id)
    row = marked([dict(await conn.fetchrow(f"{ALERT_SELECT} WHERE a.id = $1", alert_id))])[0]
    await bus.publish("alert.updated", {"alert": row})
    return row


@router.post("/alerts/{alert_id}/close", response_model=AlertOut)
async def close(alert_id: UUID, body: AlertClose, request: Request,
                user: User = Depends(require("alerts.ack")),
                conn: asyncpg.Connection = Depends(get_conn)):
    await _in_scope(conn, user, alert_id)
    n = await conn.execute(
        """UPDATE alerts SET status = $2::alert_status, closed_at = now(), disposition = $3
           WHERE id = $1 AND status IN ('new','acknowledged')""",
        alert_id, body.status, body.disposition)
    if n.endswith(" 0"):
        raise HTTPException(409, "alert already closed")
    await audit(conn, request, user, "alert.close", "alert", alert_id, status=body.status,
                disposition=body.disposition)
    row = marked([dict(await conn.fetchrow(f"{ALERT_SELECT} WHERE a.id = $1", alert_id))])[0]
    await bus.publish("alert.updated", {"alert": row})
    return row


AUTH_WAIT_S = 10.0        # a socket that has not sent its token within this is closed
SCOPE_REFRESH_S = 60.0    # how often a scoped user's camera list is re-read (cameras are added while they watch)


def scoped_event(msg: str, cameras: set[str] | None) -> str | None:
    """The event as a user may see it. `cameras` = the camera codes in their scope; None for a statewide user, who
    sees everything. An event about one camera passes only for a camera in scope; counts and heartbeats are cut down
    to those cameras; any other event, or one that cannot be read, is dropped for a scoped user."""
    if cameras is None:
        return msg
    try:
        e = json.loads(msg)
    except ValueError:
        return None
    kind = e.get("type")
    if kind in ("alert.new", "alert.updated"):
        code = (e.get("alert") or {}).get("camera_code")
    elif kind == "sighting.new":
        code = (e.get("sighting") or {}).get("camera_code")
    elif kind == "camera.health":
        code = e.get("camera_code")
    elif kind == "detection.counts":
        rows = [r for r in e.get("cameras") or [] if str(r.get("camera_code", "")).upper() in cameras]
        return json.dumps({**e, "cameras": rows}) if rows else None
    elif kind == "worker.heartbeat":
        mine = [c for c in e.get("cameras") or [] if str(c).upper() in cameras]
        if not mine:
            return None
        return json.dumps({**e, "cameras": mine,
                           "fps": {c: v for c, v in (e.get("fps") or {}).items() if str(c).upper() in cameras}})
    else:
        return None
    return msg if code and str(code).upper() in cameras else None


async def _in_scope(conn: asyncpg.Connection, user: User, alert_id: UUID) -> None:
    """404 unless the alert exists and its camera is in the user's department or district: a scoped user acts
    only on their own alerts, and learns nothing about any other."""
    where, params = scope_clause(user, alias="c", start_idx=2)
    if not await conn.fetchval(f"SELECT 1 FROM alerts a JOIN cameras c ON c.id = a.camera_id "
                               f"WHERE a.id = $1 AND {where}", alert_id, *params):
        raise HTTPException(404, "alert not found")


@router.put("/alerts/{alert_id}/tags", response_model=AlertOut)
async def set_tags(alert_id: UUID, body: AlertTags, request: Request,
                   user: User = Depends(require("alerts.ack")),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Event tagging (Model 2): the alert's whole set of tags, replacing the old one; any status, in scope only."""
    where, params = scope_clause(user, alias="c", start_idx=3)
    n = await conn.execute(
        f"""UPDATE alerts a SET tags = $2 FROM cameras c
            WHERE a.id = $1 AND c.id = a.camera_id AND {where}""", alert_id, body.tags, *params)
    if n.endswith(" 0"):
        raise HTTPException(404, "alert not found")
    await audit(conn, request, user, "alert.tagged", "alert", alert_id, tags=body.tags)
    row = marked([dict(await conn.fetchrow(f"{ALERT_SELECT} WHERE a.id = $1", alert_id))])[0]
    await bus.publish("alert.updated", {"alert": row})
    return row


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket):
    """Live feed of alert.new / alert.updated / camera.health / sighting.new / detection.counts / worker.heartbeat
    events. The client's first message carries its token, {"type": "auth", "token": "..."}, never the URL, which
    proxy logs, browser history and screenshots keep. A user scoped to a department or district receives only the
    events about cameras in that scope."""
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_WAIT_S))
        claims = decode_token(str(first.get("token", "")))
        async with pool().acquire() as conn:
            user = await load_user(conn, claims["sub"])
    except Exception:  # noqa: BLE001 - late, malformed or invalid: the socket closes either way
        await ws.close(code=4401)
        return
    if user is None or not user.can("alerts.read"):
        await ws.close(code=4403)
        return

    scope: dict = {"cameras": None, "at": float("-inf")}

    async def cameras_in_scope() -> set[str] | None:
        if user.statewide:
            return None
        if time.monotonic() - scope["at"] > SCOPE_REFRESH_S:
            where, params = scope_clause(user, alias="c")
            async with pool().acquire() as conn:
                rows = await conn.fetch(f"SELECT c.camera_code FROM cameras c WHERE {where}", *params)
            scope["cameras"], scope["at"] = {r["camera_code"].upper() for r in rows}, time.monotonic()
        return scope["cameras"]

    async def pump():
        async for msg in bus.subscribe():
            out = scoped_event(msg, await cameras_in_scope())
            if out is not None:
                await ws.send_text(out)

    task = asyncio.create_task(pump())
    try:
        while True:
            await ws.receive_text()  # keep-alive / client pings
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
