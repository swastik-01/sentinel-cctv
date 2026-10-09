"""Model 2: searchable vehicle movement records. The live-test-case query lives here:
given a registration number, return the timestamped, location-wise movement history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query, Request
from sentinel_common import normalise_plate

from .. import journey
from ..audit import audit
from ..auth import User, require
from ..cameras_repo import scope_clause
from ..config import get_settings
from ..db import get_conn, rows_to_dicts
from ..marking import needs_review
from ..schemas import MovementOut, SightingOut

router = APIRouter(prefix="/sightings", tags=["sightings"])

# Each sighting carries its capture grade (routers/quality.py) when it has one: a primary-key lookup per row.
MOVEMENT_SELECT = """SELECT m.*, q.quality AS q_quality, q.reasons AS q_reasons FROM v_vehicle_movement m
                     LEFT JOIN sighting_quality q ON q.sighting_id = m.id AND q.sighting_ts = m.event_ts"""


def with_quality(rows) -> list[dict]:
    """Rows as dicts, the grade nested as quality: {quality, reasons} (None when not graded), and the G3 mark
    ("check the crop", marking.py) when confidence marking is on."""
    marking = get_settings().confidence_marking
    out = []
    for d in rows_to_dicts(rows):
        grade, reasons = d.pop("q_quality"), d.pop("q_reasons")
        d["quality"] = {"quality": grade, "reasons": list(reasons or [])} if grade else None
        d["needs_review"] = needs_review(d.get("ocr_conf")) if marking else None
        out.append(d)
    return out


@router.get("/recent", response_model=list[SightingOut])
async def recent(request: Request, limit: int = Query(50, ge=0, le=500), camera: str | None = None,
                 user: User = Depends(require("sightings.search")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    extra = ""
    if camera:
        params.append(camera.upper())
        extra = f" AND m.camera_code = ${len(params)}"
    params.append(limit)
    rows = await conn.fetch(
        f"""{MOVEMENT_SELECT} JOIN cameras c ON c.id = m.camera_id
            WHERE {where}{extra} ORDER BY m.event_ts DESC LIMIT ${len(params)}""", *params)
    # A listing of plates is a plate lookup too: audited like a search, without the plates themselves.
    await audit(conn, request, user, "sightings.recent", "camera", camera.upper() if camera else "all",
                results=len(rows))
    return with_quality(rows)


@router.get("", response_model=list[SightingOut])
async def search(request: Request, plate: str | None = None, camera: str | None = None,
                 since: datetime | None = None, until: datetime | None = None,
                 min_conf: float = Query(0.0, ge=0, le=1), limit: int = Query(200, ge=0, le=2000),
                 user: User = Depends(require("sightings.search")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    filters = [where]

    def add(cond: str, val):
        params.append(val)
        filters.append(cond.replace("?", f"${len(params)}"))

    if plate:
        add("m.plate_norm LIKE ?", f"%{normalise_plate(plate)}%")
    if camera:
        add("m.camera_code = ?", camera.upper())
    if since:
        add("m.event_ts >= ?", since)
    if until:
        add("m.event_ts <= ?", until)
    if min_conf:
        add("m.ocr_conf >= ?", min_conf)
    params.append(limit)
    rows = await conn.fetch(
        f"""{MOVEMENT_SELECT} JOIN cameras c ON c.id = m.camera_id
            WHERE {' AND '.join(filters)} ORDER BY m.event_ts DESC LIMIT ${len(params)}""", *params)
    if plate:
        await audit(conn, request, user, "plate.search", "plate", normalise_plate(plate),
                    results=len(rows))
    return with_quality(rows)


@router.get("/movement/{plate}", response_model=MovementOut)
async def movement(plate: str, request: Request,
                   since: datetime | None = None, until: datetime | None = None,
                   fuzzy: bool = Query(True, description="include near-miss OCR reads"),
                   purpose: str | None = Query(None, description="investigative purpose, audited"),
                   user: User = Depends(require("sightings.search")),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Full timestamped, location-wise movement history for a registration number."""
    norm = normalise_plate(plate)
    since = since or datetime.now(timezone.utc) - timedelta(days=30)
    until = until or datetime.now(timezone.utc)
    max_edits = get_settings().fuzzy_max_edits
    where, params = scope_clause(user, alias="c", start_idx=5)

    if fuzzy:
        # `%` uses the trigram GIN index as a prefilter; levenshtein makes the final call.
        match = ("(m.plate_norm = $1 OR (m.plate_norm % $1 AND length(m.plate_norm) = length($1) "
                 "AND levenshtein(m.plate_norm, $1) <= $4))")
    else:
        match = "(m.plate_norm = $1 AND $4 >= 0)"
    rows = await conn.fetch(
        f"""{MOVEMENT_SELECT} JOIN cameras c ON c.id = m.camera_id
            WHERE {match} AND m.event_ts BETWEEN $2 AND $3 AND {where}
            ORDER BY m.event_ts ASC LIMIT 5000""",
        norm, since, until, max_edits, *params)

    timeline = with_quality(rows)
    # Route: consecutive distinct camera positions, in time order.
    coords, last_code = [], None
    for s in timeline:
        if s["lat"] is None or s["camera_code"] == last_code:
            continue
        coords.append([s["lon"], s["lat"]])
        last_code = s["camera_code"]
    route = {"type": "Feature", "properties": {"plate": norm, "points": len(coords)},
             "geometry": {"type": "LineString", "coordinates": coords} if len(coords) > 1
             else {"type": "MultiPoint", "coordinates": coords}}

    await audit(conn, request, user, "plate.movement", "plate", norm, purpose=purpose,
                fuzzy=fuzzy, results=len(timeline),
                window=[since.isoformat(), until.isoformat()])
    return MovementOut(
        plate=plate, plate_norm=norm, fuzzy=fuzzy,
        matched_plates=sorted({s["plate_norm"] for s in timeline}),
        first_seen=timeline[0]["event_ts"] if timeline else None,
        last_seen=timeline[-1]["event_ts"] if timeline else None,
        distinct_cameras=len({s["camera_code"] for s in timeline}),
        total_sightings=len(timeline), timeline=timeline, route=route,
        visits=journey.visits(timeline, norm),
    )


@router.get("/stats")
async def stats(hours: int = Query(24, ge=1, le=720), user: User = Depends(require("sightings.search")),
                conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c", start_idx=2)
    row = await conn.fetchrow(
        f"""SELECT count(*) AS sightings, count(DISTINCT s.plate_norm) AS distinct_plates,
                   count(DISTINCT s.camera_id) AS cameras_reporting,
                   round(avg(s.ocr_conf)::numeric, 3) AS avg_ocr_conf
            FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
            WHERE s.event_ts > now() - ($1 || ' hours')::interval AND {where}""",
        str(hours), *params)
    per_cam = await conn.fetch(
        f"""SELECT c.camera_code, c.name, count(*) AS sightings
            FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
            WHERE s.event_ts > now() - ($1 || ' hours')::interval AND {where}
            GROUP BY c.camera_code, c.name ORDER BY sightings DESC LIMIT 20""",
        str(hours), *params)
    return {**dict(row), "per_camera": rows_to_dicts(per_cam)}
