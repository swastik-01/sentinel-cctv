"""Plate-reading quality by camera: each capture graded (capture_quality.py), rolled up per camera into a
tier and recommendations (camera_quality.py).

Grades are made after ingest, in a background task that reads the evidence crop from the crop store (the
same file routers/evidence.py serves), and by scripts/quality_backfill.py for sightings stored before.
The report holds counts, medians and rates only: no plate text, no crop.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import capture_quality as cq
from ..auth import User, require
from ..camera_quality import graded, recommendations, tier
from ..cameras_repo import scope_clause
from ..db import get_conn, pool
from .evidence import crop_file

log = logging.getLogger("sentinel.quality")
router = APIRouter(tags=["reports"])

INSERT = """INSERT INTO sighting_quality (sighting_id, sighting_ts, camera_id, plate_w, plate_h, char_h, layout,
                                          sharpness, brightness, contrast, clipped, oblique, quality, reasons)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (sighting_id, sighting_ts) DO NOTHING"""


def grade(sightings: list[dict]) -> list[tuple]:
    """Rows for INSERT, one per sighting whose crop is in the store and readable. CPU work: call it off the
    event loop. Each sighting: id, event_ts, camera_id, crop_path, bbox, ocr_conf."""
    rows = []
    for s in sightings:
        path = crop_file(s.get("crop_path"))
        g = cq.grade_file(path, s.get("bbox"), s.get("ocr_conf")) if path else None
        if g is not None:
            rows.append((s["id"], s["event_ts"], s["camera_id"], g["plate_w"], g["plate_h"], g["char_h"],
                         g["layout"], g["sharpness"], g["brightness"], g["contrast"], g["clipped"], g["oblique"],
                         g["quality"], g["reasons"]))
    return rows


async def grade_new(sightings: list[dict]) -> None:
    """Background task after an ingest batch commits. A failure here never touches the stored sightings:
    the backfill script grades whatever was missed."""
    if not cq.AVAILABLE or not sightings:
        return
    try:
        rows = await asyncio.to_thread(grade, sightings)
        if rows:
            async with pool().acquire() as conn:
                await conn.executemany(INSERT, rows)
    except Exception:  # noqa: BLE001
        log.exception("grading %d captures failed", len(sightings))


# Everything per camera in one pass; $1/$2 are the window, then the camera filter's parameters.
REPORT = """
WITH g AS (
    SELECT q.camera_id, count(*) AS captures,
           count(*) FILTER (WHERE q.quality = 'good') AS good,
           count(*) FILTER (WHERE q.quality = 'marginal') AS marginal,
           count(*) FILTER (WHERE q.quality = 'poor') AS poor,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY q.plate_w) AS median_plate_w,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY q.char_h) AS median_char_h,
           count(*) FILTER (WHERE q.layout = 'two-line') AS two_line,
           count(*) FILTER (WHERE q.layout = 'two-line' AND 'low_confidence' = ANY(q.reasons)) AS two_line_low_conf
    FROM sighting_quality q WHERE q.sighting_ts >= $1 AND q.sighting_ts <= $2 AND NOT EXISTS (
        SELECT 1 FROM plate_reviews x WHERE x.sighting_id = q.sighting_id AND x.sighting_ts = q.sighting_ts
                                        AND x.verdict = 'not_a_plate')
    GROUP BY q.camera_id
), n AS (   -- captures a reviewer marked as not a plate (either review mode): left out of g and the reasons
    SELECT x.camera_id, count(DISTINCT x.sighting_id) AS not_plates FROM plate_reviews x
    WHERE x.verdict = 'not_a_plate' AND x.sighting_ts >= $1 AND x.sighting_ts <= $2 GROUP BY x.camera_id
), f AS (
    SELECT e.camera_id, sum(e.value)::bigint AS frames FROM detection_events e
    WHERE e.event_type = 'object_counts' AND e.event_ts >= $1 AND e.event_ts <= $2 GROUP BY e.camera_id
), s AS (
    SELECT s.camera_id, count(*) AS sightings FROM vehicle_sightings s
    WHERE s.event_ts >= $1 AND s.event_ts <= $2 GROUP BY s.camera_id
), r AS (   -- blind reviews of vehicle plates: a crop with no plate, or none a person can read, says nothing
    SELECT r.camera_id, count(*) AS reviewed_blind,
           count(*) FILTER (WHERE r.verdict = 'exact') AS blind_exact,
           count(*) FILTER (WHERE q.quality = 'good') AS good_reviewed,
           count(*) FILTER (WHERE q.quality = 'good' AND r.verdict = 'exact') AS good_exact,
           count(*) FILTER (WHERE q.layout = 'two-line') AS two_line_reviewed,
           count(*) FILTER (WHERE q.layout = 'two-line' AND r.verdict = 'exact') AS two_line_exact
    FROM plate_reviews r
    LEFT JOIN sighting_quality q ON q.sighting_id = r.sighting_id AND q.sighting_ts = r.sighting_ts
    WHERE r.mode = 'blind' AND r.verdict NOT IN ('not_a_plate', 'unreadable')
      AND r.sighting_ts >= $1 AND r.sighting_ts <= $2
    GROUP BY r.camera_id
)
SELECT c.id AS camera_id, c.camera_code, c.name AS camera_name, dp.code AS department, c.anpr_viable,
       c.analytics_enabled, coalesce(g.captures, 0) AS captures, coalesce(g.good, 0) AS good,
       coalesce(g.marginal, 0) AS marginal, coalesce(g.poor, 0) AS poor,
       round(g.median_plate_w)::int AS median_plate_w, round(g.median_char_h)::int AS median_char_h,
       coalesce(g.two_line, 0) AS two_line, coalesce(g.two_line_low_conf, 0) AS two_line_low_conf,
       coalesce(s.sightings, 0) AS sightings, coalesce(n.not_plates, 0) AS not_plates,
       coalesce(f.frames, 0) AS frames_analysed,
       coalesce(r.reviewed_blind, 0) AS reviewed_blind, coalesce(r.blind_exact, 0) AS blind_exact,
       coalesce(r.good_reviewed, 0) AS good_reviewed, coalesce(r.good_exact, 0) AS good_exact,
       coalesce(r.two_line_reviewed, 0) AS two_line_reviewed, coalesce(r.two_line_exact, 0) AS two_line_exact
FROM cameras c
JOIN departments dp ON dp.id = c.department_id
LEFT JOIN g ON g.camera_id = c.id
LEFT JOIN f ON f.camera_id = c.id
LEFT JOIN s ON s.camera_id = c.id
LEFT JOIN r ON r.camera_id = c.id
LEFT JOIN n ON n.camera_id = c.id
WHERE {where} AND (c.analytics_enabled OR g.captures IS NOT NULL OR f.frames IS NOT NULL OR s.sightings IS NOT NULL)
"""
REASONS = """
SELECT q.camera_id, x.reason, count(*) AS n
FROM sighting_quality q JOIN cameras c ON c.id = q.camera_id, unnest(q.reasons) AS x(reason)
WHERE q.sighting_ts >= $1 AND q.sighting_ts <= $2 AND {where} AND NOT EXISTS (
    SELECT 1 FROM plate_reviews p WHERE p.sighting_id = q.sighting_id AND p.sighting_ts = q.sighting_ts
                                    AND p.verdict = 'not_a_plate')
GROUP BY q.camera_id, x.reason
"""
TIER_ORDER = {"A": 0, "B": 1, "C": 2}


def _aware(t: datetime) -> datetime:
    """A time without a zone is local, as the database reads it; made explicit so the two can be compared. One
    the platform cannot convert (before 1970 on Windows) is a 422, not a 500."""
    if t.tzinfo is not None:
        return t
    try:
        return t.astimezone()
    except (OSError, OverflowError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"time {t.isoformat()} is out of range") from None


@router.get("/reports/camera-quality")
async def camera_quality(since: datetime | None = None, until: datetime | None = None,
                         hours: int = Query(168, ge=1, le=2160),
                         prefix: str | None = Query(None, max_length=20),
                         user: User = Depends(require("reports.read")),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """Plate-reading quality per camera in the user's scope: how its captures grade, why, a tier (A reads
    plates, B marginal, C counts only) and what would improve it. Window: `since`/`until` when given, else
    the last `hours` (default 7 days); `prefix` narrows to camera codes that start with it.

    `frames_analysed` are the object detector's frames (the plate detector's are not counted), so
    `plates_per_1000_frames` compares cameras analysed the same way; `blind_exact` counts the blind reviews
    of vehicle plates whose reviewer read the plate exactly as Sentinel stored it. Captures a reviewer marked
    as not a plate are counted apart (`not_plates`) and left out of the grades, tier and plate rate."""
    until = _aware(until) if until else datetime.now(timezone.utc)
    since = _aware(since) if since else until - timedelta(hours=hours)
    if since > until:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "since is after until")
    where, params = scope_clause(user, alias="c", start_idx=3)
    if prefix and prefix.strip():
        esc = prefix.strip().upper().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(esc + "%")
        where += f" AND c.camera_code LIKE ${len(params) + 2}"
    rows = await conn.fetch(REPORT.format(where=where), since, until, *params)
    reasons: dict = {}
    for r in await conn.fetch(REASONS.format(where=where), since, until, *params):
        reasons.setdefault(r["camera_id"], {})[r["reason"]] = r["n"]

    out = []
    for r in rows:
        row = dict(r)
        cid = row.pop("camera_id")
        row["reasons"] = dict(sorted(reasons.get(cid, {}).items(), key=lambda kv: -kv[1]))
        plates = max(0, row["sightings"] - row["not_plates"])     # a read reviewed as not a plate is no plate
        row["plates_per_1000_frames"] = (round(1000 * plates / row["frames_analysed"], 1)
                                         if row["frames_analysed"] else None)
        row["blind_exact_pct"] = (round(100 * row["blind_exact"] / row["reviewed_blind"], 1)
                                  if row["reviewed_blind"] else None)
        row["tier"], row["tier_reason"] = tier(row)
        row["graded"] = graded(row)       # False: C only by default (not analysed, or no crop to grade)
        row["recommendations"] = recommendations(row, row["tier"])
        out.append(row)
    out.sort(key=lambda x: (not x["graded"], TIER_ORDER[x["tier"]], -x["captures"], x["camera_code"]))
    return out
