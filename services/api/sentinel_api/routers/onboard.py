"""Onboard a camera from nothing but its stream URL — the flow for an unfamiliar feed.

POST /onboard/probe    check a URL is reachable and see what it carries (no registry write)
POST /onboard/stream   probe + relay through MediaMTX + register in one step

Once relayed, the camera has RTSP (inference), WHEP (browser) and HLS (dashboards)
endpoints; H.265 sources get an on-demand H.264 preview. The department's camera or
VMS sees exactly one upstream session however many people watch, and a view-only
camera connects upstream only while someone is watching.
"""
from __future__ import annotations

import re

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..audit import audit
from ..auth import User, require
from ..cameras_repo import CAMERA_SELECT, NotYourCamera, assert_can_write, upsert_camera
from ..db import get_conn
from ..mediamtx import MediaMTX, mask_url, relay_urls
from ..schemas import CameraClass, IntegrationMode

router = APIRouter(prefix="/onboard", tags=["onboarding"])

_SAFE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_SOURCE = re.compile(r"^(rtsps?|rtmp|http|https|srt|udp)://", re.I)


class ProbeIn(BaseModel):
    source_url: str


class OnboardIn(BaseModel):
    camera_code: str
    name: str
    department_code: str
    district: str | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    address: str | None = None
    source_url: str
    camera_class: CameraClass = "fixed"
    mode: IntegrationMode = "ip_rtsp"
    vendor: str | None = None
    retention_days: int | None = Field(None, ge=0, le=3650)
    anpr_viable: bool = False
    analytics_enabled: bool | None = None
    on_demand: bool | None = None   # default: on demand unless analytics needs the stream continuously


def _check_source(url: str) -> None:
    if not _SOURCE.match(url):
        raise HTTPException(422, "source_url must be rtsp://, rtsps://, rtmp://, srt://, udp:// or http(s)://")


@router.post("/probe")
async def probe(body: ProbeIn, request: Request, user: User = Depends(require("cameras.write")),
                conn: asyncpg.Connection = Depends(get_conn)):
    _check_source(body.source_url)
    mtx, name = MediaMTX(), f"probe_{user.username}"
    try:
        result = await mtx.probe(name, body.source_url)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"media server unavailable: {e}")
    finally:
        try:
            await mtx.delete_path(name)
        except httpx.HTTPError:
            pass
    await audit(conn, request, user, "camera.probe", "stream", mask_url(body.source_url),
                ready=result["ready"], codec=result.get("codec"))
    return {"source": mask_url(body.source_url), **result}


@router.post("/stream")
async def onboard_stream(body: OnboardIn, request: Request, user: User = Depends(require("cameras.write")),
                         conn: asyncpg.Connection = Depends(get_conn)):
    code = body.camera_code.strip().upper()
    if not _SAFE_CODE.match(code) or code.endswith("_SUB"):
        raise HTTPException(422, "camera_code: 3-64 chars, A-Z 0-9 _ -, must not end in _SUB")
    _check_source(body.source_url)
    if not user.statewide:
        dept = await conn.fetchval("SELECT code FROM departments WHERE id = $1", user.department_id)
        if body.department_code.upper() != dept:
            raise HTTPException(403, "cannot onboard cameras for another department")
    try:            # before the probe: probing creates a relay path under this code
        await assert_can_write(conn, user, code)
    except NotYourCamera as e:
        raise HTTPException(403, str(e))

    mtx = MediaMTX()
    try:
        probe = await mtx.probe(code, body.source_url)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"media server unavailable: {e}")
    if not probe["ready"]:
        await mtx.delete_path(code)
        await audit(conn, request, user, "camera.onboard_failed", "camera", code,
                    source=mask_url(body.source_url), error=probe.get("error"))
        raise HTTPException(422, {"message": probe["error"], "probe": probe})

    analytics = body.analytics_enabled if body.analytics_enabled is not None else body.anpr_viable
    on_demand = body.on_demand if body.on_demand is not None else not analytics
    if on_demand:
        await mtx.put_relay(code, body.source_url, on_demand=True)

    urls = relay_urls(code, probe["codec"])
    row = body.model_dump(exclude={"source_url", "on_demand"})
    row.update(camera_code=code, codec=probe["codec"], analytics_enabled=analytics,
               resolution=f"{probe['width']}x{probe['height']}" if probe.get("width") else None,
               tags={"source": "onboard", "relay": "mediamtx", "on_demand": on_demand}, **urls)
    async with conn.transaction():
        try:
            outcome = await upsert_camera(conn, row, user)
        except ValueError as e:
            await mtx.delete_path(code)
            raise HTTPException(422, str(e))
        await conn.execute(
            """INSERT INTO camera_sources (camera_id, source_url, on_demand, probed_codec, probed_width,
                                           probed_height, probed_at)
               SELECT id, $2, $3, $4, $5, $6, now() FROM cameras WHERE camera_code = $1
               ON CONFLICT (camera_id) DO UPDATE SET source_url = EXCLUDED.source_url,
                 on_demand = EXCLUDED.on_demand, probed_codec = EXCLUDED.probed_codec,
                 probed_width = EXCLUDED.probed_width, probed_height = EXCLUDED.probed_height,
                 probed_at = now(), updated_at = now()""",
            code, body.source_url, on_demand, probe["codec"], probe.get("width"), probe.get("height"))
    await audit(conn, request, user, f"camera.onboarded_{outcome}", "camera", code,
                source=mask_url(body.source_url), codec=probe["codec"], on_demand=on_demand,
                seconds=probe["seconds"])
    camera = dict(await conn.fetchrow(CAMERA_SELECT + " WHERE c.camera_code = $1", code))
    return {"outcome": outcome, "probe": probe, "on_demand": on_demand, "camera": camera}


@router.delete("/stream/{code}", status_code=204)
async def remove_relay(code: str, request: Request, user: User = Depends(require("cameras.write")),
                       conn: asyncpg.Connection = Depends(get_conn)):
    code = code.upper()
    try:
        await assert_can_write(conn, user, code)
    except NotYourCamera as e:
        raise HTTPException(403, str(e))
    n = await conn.execute(
        "DELETE FROM camera_sources USING cameras c WHERE camera_sources.camera_id = c.id AND c.camera_code = $1",
        code)
    try:
        await MediaMTX().delete_path(code)
    except httpx.HTTPError:
        pass
    if n.endswith(" 0"):
        raise HTTPException(404, "no relayed source for this camera")
    await audit(conn, request, user, "camera.relay_removed", "camera", code)
