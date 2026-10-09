"""Intrusion zones per camera: drawn polygons, the classes that trigger them, armed hours.

Stored in the camera's tags (no schema change), read by the analytics worker with its
camera list. Zones only describe where to look; presence is detected by the worker and
arrives as an `intrusion` event (routers/ingest.py), which becomes an alert.
"""
from __future__ import annotations

import re

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..audit import audit
from ..auth import User, require
from ..cameras_repo import scope_clause
from ..db import get_conn

router = APIRouter(prefix="/cameras", tags=["zones"])
CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}   # what the worker's detector reports
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Armed(BaseModel):
    start: str = Field(alias="from")
    to: str

    @field_validator("start", "to")
    @classmethod
    def hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM (IST)")
        return v


class ZoneIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    name: str = Field(min_length=1, max_length=80)
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=32)
    classes: list[str] = Field(default_factory=lambda: ["person"], min_length=1)
    min_dwell_s: float = Field(3.0, ge=1, le=600)
    armed: Armed | None = None
    severity: str = Field("high", pattern=r"^(low|medium|high|critical)$")

    @field_validator("polygon")
    @classmethod
    def normalised(cls, v):
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in v):
            raise ValueError("polygon points are fractions of the frame, 0 to 1")
        return v

    @field_validator("classes")
    @classmethod
    def known(cls, v):
        bad = set(v) - CLASSES
        if bad:
            raise ValueError(f"unknown classes {sorted(bad)}; the detector reports {sorted(CLASSES)}")
        return v


async def _camera(conn: asyncpg.Connection, code: str, user: User) -> asyncpg.Record:
    where, params = scope_clause(user, alias="c", start_idx=2)
    row = await conn.fetchrow(f"SELECT c.id, c.tags FROM cameras c WHERE c.camera_code = $1 AND {where}",
                              code.upper(), *params)
    if row is None:
        raise HTTPException(404, "camera not found")
    return row


@router.get("/{code}/zones")
async def get_zones(code: str, user: User = Depends(require("cameras.read")),
                    conn: asyncpg.Connection = Depends(get_conn)):
    return (await _camera(conn, code, user))["tags"].get("zones", [])


@router.put("/{code}/zones")
async def put_zones(code: str, zones: list[ZoneIn], request: Request,
                    user: User = Depends(require("cameras.write")),
                    conn: asyncpg.Connection = Depends(get_conn)):
    if len({z.id for z in zones}) != len(zones):
        raise HTTPException(422, "zone ids must be unique per camera")
    cam = await _camera(conn, code, user)
    body = [z.model_dump(by_alias=True, exclude_none=True) for z in zones]
    await conn.execute("UPDATE cameras SET tags = jsonb_set(tags, '{zones}', $2::jsonb) WHERE id = $1",
                       cam["id"], body)
    await audit(conn, request, user, "camera.zones", "camera", code.upper(), zones=[z.id for z in zones])
    return body
