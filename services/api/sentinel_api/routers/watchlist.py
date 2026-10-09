"""Watchlist: stolen / blacklisted vehicles, wanted and missing persons.

Entries come from manual entry, CSV, or a government-database adapter
(VAHAN, eGujCop, ...). Adapters are pluggable; in this build they run against
local mock services with realistic contracts and zero real PII.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sentinel_common import normalise_plate

from .. import bus
from ..adapters import get_adapter, list_adapters
from ..audit import audit
from ..auth import User, require
from ..db import get_conn, like_escape, rows_to_dicts
from ..schemas import WatchKind, WatchlistCreated, WatchlistIn, WatchlistOut

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

WL_SELECT = """SELECT id, kind::text, plate_norm, subject_name, severity::text, source, source_ref,
                      reason, active, valid_from, valid_until, created_at FROM watchlist_entries"""


async def _insert(conn: asyncpg.Connection, e: WatchlistIn, user: User | None) -> UUID:
    norm = normalise_plate(e.plate) if e.plate else None
    if e.kind in ("stolen_vehicle", "blacklisted_vehicle", "bolo") and not norm:
        raise HTTPException(422, f"{e.kind} requires a plate")
    # De-duplicate on (kind, plate/subject, source): re-syncs must not pile up entries.
    existing = await conn.fetchval(
        """SELECT id FROM watchlist_entries WHERE kind = $1::watch_kind AND source = $2
           AND plate_norm IS NOT DISTINCT FROM $3 AND subject_name IS NOT DISTINCT FROM $4""",
        e.kind, e.source, norm, e.subject_name)
    if existing:
        await conn.execute(
            """UPDATE watchlist_entries SET active = true, severity = $2::severity_level,
               reason = COALESCE($3, reason), source_ref = COALESCE($4, source_ref),
               valid_until = $5 WHERE id = $1""",
            existing, e.severity, e.reason, e.source_ref, e.valid_until)
        return existing
    return await conn.fetchval(
        """INSERT INTO watchlist_entries (kind, plate_norm, subject_name, severity, source,
                                         source_ref, reason, valid_until, created_by)
           VALUES ($1::watch_kind, $2, $3, $4::severity_level, $5, $6, $7, $8, $9) RETURNING id""",
        e.kind, norm, e.subject_name, e.severity, e.source, e.source_ref, e.reason,
        e.valid_until, user.id if user else None)


RETRO_HOURS = 24


async def _raise_retro(conn: asyncpg.Connection, wid: UUID, hit: asyncpg.Record) -> str | None:
    """One alert per entry for a sighting made before the plate was listed, carrying the time
    the vehicle was actually seen. Adding the same plate again does not raise another."""
    if await conn.fetchval("SELECT 1 FROM alerts WHERE watchlist_id = $1 AND retrospective", wid):
        return None
    w = await conn.fetchrow("SELECT kind::text AS kind, severity::text AS severity, subject_name, reason, plate_norm "
                            "FROM watchlist_entries WHERE id = $1", wid)
    aid = await conn.fetchval(
        """INSERT INTO alerts (watchlist_id, camera_id, sighting_id, sighting_ts, plate_norm, match_score,
                               exact_match, severity, retrospective)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::severity_level, true) RETURNING id""",
        wid, hit["camera_id"], hit["id"], hit["event_ts"], hit["plate_norm"], float(hit["score"]),
        bool(hit["exact"]), w["severity"])
    await bus.publish("alert.new", {"alert": {
        "id": str(aid), "watchlist_id": str(wid), "kind": w["kind"], "severity": w["severity"],
        "subject_name": w["subject_name"], "reason": w["reason"], "watch_plate": w["plate_norm"],
        "plate_norm": hit["plate_norm"], "match_score": float(hit["score"]), "exact_match": bool(hit["exact"]),
        "camera_code": hit["camera_code"], "camera_name": hit["camera_name"], "lat": hit["lat"], "lon": hit["lon"],
        "sighting_id": hit["id"], "sighting_ts": hit["event_ts"], "crop_path": hit["crop_path"],
        "status": "new", "triggered_at": datetime.now(timezone.utc), "retrospective": True,
        "alert_type": "watchlist"}})
    return str(aid)


async def retro_hunt(conn: asyncpg.Connection, wid: UUID, plate: str, fuzzy: bool = True) -> dict:
    """Has this plate been seen in the last 24 h? A plate given at evaluation time, or listed
    after the vehicle passed, gets an answer at once instead of waiting for the next pass.
    Exact reads first; `fuzzy` adds reads one character off (same length), flagged as such."""
    rows = await conn.fetch(
        """SELECT s.id, s.event_ts, s.plate_norm, s.crop_path, c.id AS camera_id, c.camera_code,
                  c.name AS camera_name, ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon,
                  (s.plate_norm = $1) AS exact,
                  1.0 - levenshtein(s.plate_norm, $1)::float / GREATEST(length($1), 1) AS score
           FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
           WHERE s.event_ts > now() - make_interval(hours => $2)
             AND (s.plate_norm = $1 OR ($3 AND s.plate_norm % $1 AND length(s.plate_norm) = length($1)
                                        AND levenshtein(s.plate_norm, $1) <= 1))
           ORDER BY (s.plate_norm = $1) DESC, s.event_ts DESC""", plate, RETRO_HOURS, fuzzy)
    if not rows:
        return {"seen": 0, "hours": RETRO_HOURS}
    last = rows[0]
    return {"seen": len(rows), "exact": sum(r["exact"] for r in rows), "hours": RETRO_HOURS,
            "cameras": len({r["camera_code"] for r in rows}),
            "last": {"camera_code": last["camera_code"], "camera_name": last["camera_name"],
                     "event_ts": last["event_ts"], "plate_norm": last["plate_norm"], "exact": last["exact"]},
            "alert_id": await _raise_retro(conn, wid, last)}


@router.get("", response_model=list[WatchlistOut])
async def list_entries(active: bool | None = True, kind: str | None = None, q: str | None = None,
                       limit: int = Query(500, ge=0, le=5000),
                       _: User = Depends(require("watchlist.read")),
                       conn: asyncpg.Connection = Depends(get_conn)):
    filters, params = ["TRUE"], []
    if active is not None:
        params.append(active)
        filters.append(f"active = ${len(params)}")
    if kind:
        if kind not in WatchKind.__args__:
            raise HTTPException(422, f"kind must be one of {', '.join(WatchKind.__args__)}")
        params.append(kind)
        filters.append(f"kind = ${len(params)}::watch_kind")
    if q:
        params.append(f"%{like_escape(q.upper())}%")
        filters.append(f"(plate_norm LIKE ${len(params)} OR upper(subject_name) LIKE ${len(params)})")
    params.append(limit)
    rows = await conn.fetch(f"{WL_SELECT} WHERE {' AND '.join(filters)} "
                            f"ORDER BY created_at DESC LIMIT ${len(params)}", *params)
    return rows_to_dicts(rows)


@router.get("/sources")
async def sources(_: User = Depends(require("watchlist.read"))):
    return list_adapters()


@router.get("/check/{plate}")
async def check(plate: str, request: Request, user: User = Depends(require("watchlist.read")),
                conn: asyncpg.Connection = Depends(get_conn)):
    """Is this plate on any active list? Exact and fuzzy. A plate lookup, so audited like a search."""
    norm = normalise_plate(plate)
    await audit(conn, request, user, "watchlist.check", "plate", norm)
    rows = await conn.fetch(
        f"""{WL_SELECT.replace('FROM', ', 1.0 - levenshtein(plate_norm, $1)::float / GREATEST(length($1),1) AS score FROM')}
            WHERE active AND plate_norm IS NOT NULL
              AND (plate_norm = $1 OR (length(plate_norm) = length($1) AND levenshtein(plate_norm, $1) <= 2))
              AND (valid_until IS NULL OR valid_until > now())
            ORDER BY score DESC LIMIT 10""", norm)
    return {"plate_norm": norm, "matches": rows_to_dicts(rows)}


@router.post("", response_model=WatchlistCreated, status_code=201)
async def create(body: WatchlistIn, request: Request,
                 user: User = Depends(require("watchlist.write")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    wid = await _insert(conn, body, user)
    row = dict(await conn.fetchrow(f"{WL_SELECT} WHERE id = $1", wid))
    retro = await retro_hunt(conn, wid, row["plate_norm"]) if row["plate_norm"] else None
    await audit(conn, request, user, "watchlist.create", "watchlist", wid, kind=body.kind,
                plate=body.plate, retro_seen=(retro or {}).get("seen"))
    return {**row, "retro": retro}


@router.delete("/{entry_id}", status_code=204)
async def deactivate(entry_id: UUID, request: Request,
                     user: User = Depends(require("watchlist.write")),
                     conn: asyncpg.Connection = Depends(get_conn)):
    n = await conn.execute("UPDATE watchlist_entries SET active = false WHERE id = $1", entry_id)
    if n.endswith("0"):
        raise HTTPException(404, "entry not found")
    await audit(conn, request, user, "watchlist.deactivate", "watchlist", entry_id)


@router.post("/import")
async def import_csv(request: Request, file: UploadFile,
                     user: User = Depends(require("watchlist.write")),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """CSV columns: kind, plate, subject_name, severity, source, source_ref, reason"""
    text = (await file.read()).decode("utf-8-sig")
    ok, errors, ids = 0, [], []
    for i, raw in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            e = WatchlistIn(**{k: (v or None) for k, v in raw.items() if k})
            ids.append(await _insert(conn, e, user))
            ok += 1
        except Exception as ex:  # noqa: BLE001 - report per-row
            errors.append({"line": i, "error": str(ex)})
    seen = await _retro_bulk(conn, ids)
    await audit(conn, request, user, "watchlist.bulk_import", "csv", file.filename, ok=ok,
                errors=len(errors), retro_seen=seen)
    return {"imported": ok, "errors": errors, "already_seen": seen}


async def _retro_bulk(conn: asyncpg.Connection, ids: list[UUID]) -> int:
    """Bulk paths check exact reads only: one indexed lookup per plate. A plate added by hand
    also gets one-character near misses (retro_hunt)."""
    seen = 0
    for wid in ids:
        plate = await conn.fetchval("SELECT plate_norm FROM watchlist_entries WHERE id = $1", wid)
        if plate and (await retro_hunt(conn, wid, plate, fuzzy=False))["seen"]:
            seen += 1
    return seen


@router.post("/sync/{source}")
async def sync_source(source: str, request: Request,
                      user: User = Depends(require("watchlist.write")),
                      conn: asyncpg.Connection = Depends(get_conn)):
    """Pull the current list from a government-database adapter (VAHAN, eGujCop, ...)."""
    adapter = get_adapter(source)
    if adapter is None:
        raise HTTPException(404, f"no adapter for {source}; available: {[a['name'] for a in list_adapters()]}")
    entries = await adapter.fetch()
    ids = [await _insert(conn, e, user) for e in entries]
    seen = await _retro_bulk(conn, ids)
    await audit(conn, request, user, "watchlist.sync", "adapter", source, entries=len(ids), retro_seen=seen)
    return {"source": source, "synced": len(ids), "already_seen": seen, "adapter": adapter.describe()}
