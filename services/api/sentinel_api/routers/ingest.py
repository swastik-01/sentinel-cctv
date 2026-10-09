"""Internal ingest path used by analytics workers.

A sighting batch is persisted, then each plate is checked against the active
watchlist — exact first, then OCR near-misses within FUZZY_MAX_EDITS — and any
hit raises an alert and a real-time event. Cooldown prevents the same
watchlist entry on the same camera from paging the control room every frame.

Near misses at one edit (the default) are found through one-character masks
(upgrades.py): an indexed lookup, not levenshtein() over the whole watchlist.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sentinel_common import normalise_plate

from .. import bus
from ..auth import require_ingest_key
from ..config import get_settings
from ..db import get_conn
from ..marking import needs_review
from ..schemas import DetectionEventIn, SightingIn
from ..upgrades import plate_masks
from .quality import grade_new

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_ingest_key)])

_camera_cache: dict[str, tuple[str, float]] = {}
CAMERA_CACHE_S = 60.0   # a camera deleted and re-created gets a new id: a stale entry would fail every insert
MAX_BATCH = 5000        # a worker's batch is about a second of reads; anything larger is a mistake or an attack


async def _camera_id(conn: asyncpg.Connection, code: str) -> str | None:
    code = code.upper()
    hit = _camera_cache.get(code)
    if hit is None or time.monotonic() - hit[1] > CAMERA_CACHE_S:
        cid = await conn.fetchval("SELECT id FROM cameras WHERE camera_code = $1", code)
        if cid is None:
            _camera_cache.pop(code, None)
            return None
        _camera_cache[code] = (cid, time.monotonic())
        return cid
    return hit[0]


MATCH_SELECT = """SELECT id, kind::text, severity::text, subject_name, reason, plate_norm,
                  (plate_norm = $1) AS exact,
                  1.0 - levenshtein(plate_norm, $1)::float / GREATEST(length($1), 1) AS score
           FROM watchlist_entries
           WHERE active AND plate_norm IS NOT NULL AND (valid_until IS NULL OR valid_until > now())"""


async def _match(conn: asyncpg.Connection, plate: str, max_edits: int):
    if max_edits == 1:      # exact or one substitution: both share a mask with the watchlist plate
        return await conn.fetchrow(
            f"""{MATCH_SELECT}
                AND id IN (SELECT watchlist_id FROM watchlist_masks WHERE mask = ANY($2::text[]))
                ORDER BY exact DESC, score DESC LIMIT 1""", plate, plate_masks(plate))
    if max_edits == 0:
        return await conn.fetchrow(f"{MATCH_SELECT} AND plate_norm = $1 LIMIT 1", plate)
    return await conn.fetchrow(
        f"""{MATCH_SELECT}
            AND (plate_norm = $1 OR (length(plate_norm) = length($1) AND levenshtein(plate_norm, $1) <= $2))
            ORDER BY exact DESC, score DESC LIMIT 1""", plate, max_edits)


async def _match_and_alert(conn: asyncpg.Connection, sighting: dict) -> dict | None:
    s = get_settings()
    hit = await _match(conn, sighting["plate_norm"], s.fuzzy_max_edits)
    if hit is None:
        return None
    if not hit["exact"] and sighting.get("reads") == 1:
        return None     # one read on a slow camera plus one OCR slip is too thin to page anyone

    # One alert per pass. A retrospective alert, raised when the plate was listed, reports an earlier pass: it must
    # not hold back the alert that says the vehicle is at this camera now.
    recent = await conn.fetchval(
        """SELECT id FROM alerts WHERE watchlist_id = $1 AND camera_id = $2 AND NOT retrospective
           AND triggered_at > now() - ($3 || ' seconds')::interval LIMIT 1""",
        hit["id"], sighting["camera_id"], str(s.alert_cooldown_s))
    if recent:
        return None

    # Latency on one clock: the worker's first valid read to the moment the alert exists here.
    # Worker and API share a host (or NTP) for this to mean anything; a replayed (spooled)
    # sighting is marked, because its delay is the outage, not the pipeline.
    now = datetime.now(timezone.utc)
    detail = {}
    if sighting.get("first_read_at") is not None:
        detail = {"latency_s": round((now - sighting["first_read_at"]).total_seconds(), 3),
                  "first_read_at": sighting["first_read_at"].isoformat(), "replayed": bool(sighting.get("replayed"))}
    alert_id = await conn.fetchval(
        """INSERT INTO alerts (watchlist_id, camera_id, sighting_id, sighting_ts, plate_norm,
                               match_score, exact_match, severity, detail)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::severity_level, $9::jsonb) RETURNING id""",
        hit["id"], sighting["camera_id"], sighting["id"], sighting["event_ts"],
        sighting["plate_norm"], float(hit["score"]), bool(hit["exact"]), hit["severity"], detail)
    return {
        "id": str(alert_id), "watchlist_id": str(hit["id"]), "kind": hit["kind"],
        "severity": hit["severity"], "subject_name": hit["subject_name"], "reason": hit["reason"],
        "watch_plate": hit["plate_norm"], "plate_norm": sighting["plate_norm"],
        "match_score": float(hit["score"]), "exact_match": bool(hit["exact"]),
        "camera_code": sighting["camera_code"], "camera_name": sighting["camera_name"],
        "lat": sighting["lat"], "lon": sighting["lon"],
        "sighting_id": sighting["id"], "sighting_ts": sighting["event_ts"],
        "crop_path": sighting.get("crop_path"), "status": "new",
        "triggered_at": now, "retrospective": False, "alert_type": "watchlist", "detail": detail,
        "needs_review": needs_review(sighting.get("ocr_conf"), bool(hit["exact"])) if s.confidence_marking else None,
    }


async def _first_time(conn: asyncpg.Connection, batch_id: str | None, kind: str, rows: int) -> bool:
    """False if this batch was stored before: a worker replaying a batch whose reply it never got."""
    if batch_id is None:
        return True
    return await conn.fetchval(
        """INSERT INTO ingest_batches (batch_id, kind, rows) VALUES ($1, $2, $3)
           ON CONFLICT (batch_id) DO NOTHING RETURNING true""", batch_id, kind, rows) is not None


@router.post("/sightings")
async def ingest_sightings(batch: list[SightingIn], background: BackgroundTasks,
                           batch_id: str | None = Query(None, max_length=64),
                           replayed: bool = Query(False, description="sent from the worker's outage spool"),
                           conn: asyncpg.Connection = Depends(get_conn)):
    if not batch:
        return {"stored": 0, "alerts": 0}
    if len(batch) > MAX_BATCH:
        raise HTTPException(413, f"at most {MAX_BATCH} sightings per batch")
    async with conn.transaction():      # the batch id and its rows commit together, or neither does
        if not await _first_time(conn, batch_id, "sightings", len(batch)):
            return {"stored": 0, "alerts": 0, "duplicate_batch": True}
        stored, alerts, unknown, events, crops = await _store_sightings(conn, batch, replayed)
    for event_type, payload in events:  # only once committed
        await bus.publish(event_type, payload)
    if crops:                           # graded after the reply: the worker never waits on it
        background.add_task(grade_new, crops)
    return {"stored": stored, "alerts": len(alerts), "unknown_cameras": sorted(unknown)}


async def _store_sightings(conn: asyncpg.Connection, batch: list[SightingIn], replayed: bool = False):
    stored, alerts, unknown, events, crops = 0, [], set(), [], []
    for s in batch:
        cid = await _camera_id(conn, s.camera_code)
        if cid is None:
            unknown.add(s.camera_code)
            continue
        norm = normalise_plate(s.plate_text)
        if not norm:
            continue
        row = await conn.fetchrow(
            """INSERT INTO vehicle_sightings (camera_id, event_ts, plate_text, plate_norm, ocr_conf,
                   det_conf, vehicle_type, vehicle_color, bbox, track_id, crop_path, frame_uri, reads, agreement)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING id, event_ts""",
            cid, s.event_ts, s.plate_text, norm, s.ocr_conf, s.det_conf, s.vehicle_type,
            s.vehicle_color, s.bbox, s.track_id, s.crop_path, s.frame_uri, s.reads, s.agreement)
        stored += 1
        if s.crop_path:
            crops.append({"id": row["id"], "event_ts": row["event_ts"], "camera_id": cid, "crop_path": s.crop_path,
                          "bbox": s.bbox, "ocr_conf": s.ocr_conf})
        cam = await conn.fetchrow(
            """SELECT name, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon
               FROM cameras WHERE id = $1""", cid)
        sighting = {"id": row["id"], "event_ts": row["event_ts"], "plate_norm": norm,
                    "plate_text": s.plate_text, "camera_id": cid, "camera_code": s.camera_code.upper(),
                    "camera_name": cam["name"], "lat": cam["lat"], "lon": cam["lon"],
                    "ocr_conf": s.ocr_conf, "crop_path": s.crop_path,
                    "vehicle_type": s.vehicle_type, "vehicle_color": s.vehicle_color}
        events.append(("sighting.new", {"sighting": sighting}))
        alert = await _match_and_alert(conn, {**sighting, "reads": s.reads, "first_read_at": s.first_read_at,
                                               "replayed": replayed})
        if alert:
            alerts.append(alert)
            events.append(("alert.new", {"alert": alert}))
    return stored, alerts, unknown, events, crops


@router.post("/events")
async def ingest_events(batch: list[DetectionEventIn], batch_id: str | None = Query(None, max_length=64),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Non-plate detections. Workers send `object_counts`: one row per camera per window,
    value = frames analysed, detail = detections and peak per class. Other event types
    (crowd density, loitering, ...) use the same path."""
    async with conn.transaction():
        if not await _first_time(conn, batch_id, "events", len(batch)):
            return {"stored": 0, "duplicate_batch": True}
        n, counts, alerts = await _store_events(conn, batch)
    if counts:   # camera codes and class totals only: never a box, crop or track id
        await bus.publish("detection.counts", {"cameras": counts})
    for a in alerts:
        await bus.publish("alert.new", {"alert": a})
    return {"stored": n, "alerts": len(alerts)}


async def _intrusion_alert(conn: asyncpg.Connection, camera_id: str, e: DetectionEventIn) -> dict | None:
    """An intrusion event becomes an alert, once per zone per camera per cooldown. It carries the
    zone, the classes and counts, the dwell: never an image of the person."""
    s = get_settings()
    zone = e.detail.get("zone") or e.label
    if await conn.fetchval(
            """SELECT 1 FROM alerts WHERE camera_id = $1 AND alert_type = 'intrusion' AND detail->>'zone' = $2
               AND triggered_at > now() - ($3 || ' seconds')::interval""", camera_id, zone, str(s.alert_cooldown_s)):
        return None
    severity = e.detail.get("severity") if e.detail.get("severity") in ("low", "medium", "high", "critical") else "high"
    row = await conn.fetchrow(
        """INSERT INTO alerts (camera_id, sighting_ts, severity, alert_type, detail)
           VALUES ($1, $2, $3::severity_level, 'intrusion', $4::jsonb) RETURNING id, triggered_at""",
        camera_id, e.event_ts, severity, e.detail)
    cam = await conn.fetchrow(
        """SELECT camera_code, name, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon
           FROM cameras WHERE id = $1""", camera_id)
    return {"id": str(row["id"]), "alert_type": "intrusion", "severity": severity, "kind": None,
            "camera_code": cam["camera_code"], "camera_name": cam["name"], "lat": cam["lat"], "lon": cam["lon"],
            "sighting_ts": e.event_ts, "plate_norm": None, "match_score": 1.0, "exact_match": True,
            "status": "new", "triggered_at": row["triggered_at"], "detail": e.detail, "retrospective": False}


async def _store_events(conn: asyncpg.Connection, batch: list[DetectionEventIn]):
    n, counts, alerts = 0, [], []
    for e in batch:
        cid = await _camera_id(conn, e.camera_code)
        if cid is None:
            continue
        await conn.execute(
            """INSERT INTO detection_events (camera_id, event_ts, event_type, label, confidence,
                                             value, bbox, track_id, detail)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)""",
            cid, e.event_ts, e.event_type, e.label, e.confidence, e.value, e.bbox, e.track_id,
            e.detail)
        n += 1
        if e.event_type == "object_counts":
            counts.append({"camera_code": e.camera_code.upper(), "frames": e.value,
                           "detections": e.detail.get("detections", {})})
        elif e.event_type == "intrusion":
            if (a := await _intrusion_alert(conn, cid, e)) is not None:
                alerts.append(a)
    return n, counts, alerts


@router.get("/cameras")
async def worker_cameras(conn: asyncpg.Connection = Depends(get_conn)):
    """Cameras an analytics worker may consume: analytics enabled and a stream URL present.
    RTSP is preferred; a camera a catalogue lists with HLS only is read over HLS instead."""
    rows = await conn.fetch(
        """SELECT camera_code, name, COALESCE(rtsp_url, hls_url) AS rtsp_url, codec, resolution, fps,
                  anpr_viable, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,
                  tags->'zones' AS zones
           FROM cameras WHERE analytics_enabled AND COALESCE(rtsp_url, hls_url) IS NOT NULL
           ORDER BY camera_code""")
    return [dict(r) for r in rows]


@router.get("/watchlist")
async def worker_watchlist(conn: asyncpg.Connection = Depends(get_conn)):
    """The edge copy of the active vehicle watchlist, so a worker cut off from the API can
    still flag a hit locally. Only what matching needs: no names, reasons or case refs."""
    rows = await conn.fetch(
        """SELECT plate_norm, kind::text AS kind, severity::text AS severity
           FROM watchlist_entries
           WHERE active AND plate_norm IS NOT NULL AND (valid_until IS NULL OR valid_until > now())""")
    s = get_settings()
    return {"max_edits": s.fuzzy_max_edits, "cooldown_s": s.alert_cooldown_s, "entries": [dict(r) for r in rows]}


@router.post("/heartbeat")
async def heartbeat(worker_id: str, cameras: list[str], fps: dict[str, float] | None = None,
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Worker liveness: marks its cameras as seen and reports observed analytics fps."""
    if not cameras:
        raise HTTPException(422, "no cameras")
    await conn.execute(
        "UPDATE cameras SET last_seen_at = now() WHERE camera_code = ANY($1::text[])",
        [c.upper() for c in cameras])
    await bus.publish("worker.heartbeat", {"worker_id": worker_id, "cameras": cameras, "fps": fps or {}})
    return {"ok": True}
