"""Reports: fleet summary, coverage gaps, uptime, department breakdown, audit, object counts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..auth import User, require
from ..cameras_repo import scope_clause
from ..config import get_settings
from ..db import get_conn, like_escape, rows_to_dicts

router = APIRouter(tags=["reports"])


@router.get("/reports/fleet")
async def fleet(user: User = Depends(require("reports.read")),
                conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    row = await conn.fetchrow(
        f"""SELECT count(*) AS cameras,
                   count(*) FILTER (WHERE c.health = 'online')   AS online,
                   count(*) FILTER (WHERE c.health = 'degraded') AS degraded,
                   count(*) FILTER (WHERE c.health = 'offline')  AS offline,
                   count(*) FILTER (WHERE c.health = 'unknown')  AS unknown,
                   count(*) FILTER (WHERE c.anpr_viable)         AS anpr_viable,
                   count(*) FILTER (WHERE c.analytics_enabled)   AS analytics_on,
                   count(DISTINCT c.department_id)               AS departments,
                   count(DISTINCT c.district_id)                 AS districts,
                   count(*) FILTER (WHERE c.location IS NULL)    AS ungeocoded,
                   count(*) FILTER (WHERE c.maintenance = 'under_maintenance') AS under_maintenance,
                   count(*) FILTER (WHERE c.maintenance = 'faulty')            AS faulty,
                   count(*) FILTER (WHERE c.maintenance = 'decommissioned')    AS decommissioned,
                   count(*) FILTER (WHERE c.amc_expiry < current_date
                                      AND c.maintenance <> 'decommissioned')   AS amc_expired,
                   count(*) FILTER (WHERE c.install_year <= extract(year FROM now())::int - {get_settings().ageing_years}
                                      AND c.maintenance <> 'decommissioned')   AS ageing,
                   count(*) FILTER (WHERE c.install_year IS NULL)              AS install_year_unknown
            FROM cameras c WHERE {where}""", *params)
    by_mode = await conn.fetch(
        f"SELECT c.mode::text AS mode, count(*) FROM cameras c WHERE {where} GROUP BY 1 ORDER BY 2 DESC",
        *params)
    by_codec = await conn.fetch(
        f"SELECT coalesce(c.codec,'unknown') AS codec, count(*) FROM cameras c WHERE {where} "
        f"GROUP BY 1 ORDER BY 2 DESC", *params)
    by_storage = await conn.fetch(
        f"SELECT c.storage::text AS storage, count(*), round(avg(c.retention_days),1) AS avg_retention "
        f"FROM cameras c WHERE {where} GROUP BY 1 ORDER BY 2 DESC", *params)
    return {**dict(row), "by_mode": rows_to_dicts(by_mode), "by_codec": rows_to_dicts(by_codec),
            "by_storage": rows_to_dicts(by_storage)}


@router.get("/reports/departments")
async def departments(user: User = Depends(require("reports.read")),
                      conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c")
    rows = await conn.fetch(
        f"""SELECT d.code, d.name,
                   count(c.id) AS cameras,
                   count(c.id) FILTER (WHERE c.health = 'online') AS online,
                   count(c.id) FILTER (WHERE c.anpr_viable) AS anpr_viable,
                   count(DISTINCT c.district_id) AS districts,
                   count(DISTINCT c.vendor) AS vendors,
                   min(c.retention_days) AS min_retention, max(c.retention_days) AS max_retention
            FROM departments d LEFT JOIN cameras c ON c.department_id = d.id AND {where}
            GROUP BY d.id ORDER BY cameras DESC, d.name""", *params)
    return rows_to_dicts(rows)


VEHICLE_CLASSES = ("bicycle", "car", "motorcycle", "bus", "truck")


@router.get("/reports/objects")
async def objects(hours: int = Query(24, ge=1, le=720), since: datetime | None = None,
                  until: datetime | None = None, user: User = Depends(require("reports.read")),
                  conn: asyncpg.Connection = Depends(get_conn)):
    """Vehicle and person counts from the analytics workers.

    Each stored row is one camera x one window: frames analysed plus detections per class.
    A detection is a box in one frame, not a unique vehicle or person, so the figures that
    mean something are per analysed frame: `in_view` (average number in frame) and `peak`
    (most in any single frame). Both are independent of the sampling rate. Raw `detections`
    are returned for completeness and are frame-detections, not a count of vehicles.
    Aggregates only: no per-detection listing exists, and none is exposed.
    Window: `since`/`until` when given, else the last `hours`.
    """
    until = until or datetime.now(timezone.utc)
    since = since or until - timedelta(hours=hours)
    where, params = scope_clause(user, alias="c", start_idx=3)
    window = f"e.event_ts > $1 AND e.event_ts <= $2 AND e.event_type = 'object_counts' AND {where}"
    cams = await conn.fetch(
        f"""SELECT c.camera_code, c.name, dp.code AS department, count(*) AS windows,
                   sum(e.value)::bigint AS frames, max(e.event_ts) AS last_window,
                   max((e.detail->>'peak_vehicles')::int) AS vehicle_peak
            FROM detection_events e JOIN cameras c ON c.id = e.camera_id
            LEFT JOIN departments dp ON dp.id = c.department_id
            WHERE {window} GROUP BY c.camera_code, c.name, dp.code ORDER BY c.camera_code""",
        since, until, *params)
    per_class = await conn.fetch(
        f"""SELECT c.camera_code, d.key AS label, sum(d.value::int)::bigint AS detections,
                   max((e.detail->'peak'->>d.key)::int) AS peak
            FROM detection_events e JOIN cameras c ON c.id = e.camera_id,
                 jsonb_each_text(e.detail->'detections') AS d(key, value)
            WHERE {window} GROUP BY c.camera_code, d.key""",
        since, until, *params)

    by_cam: dict[str, dict] = {}
    for r in cams:
        by_cam[r["camera_code"]] = {**dict(r), "in_view": {}, "peak": {}, "detections": {},
                                    "vehicles_in_view": 0.0}
    for r in per_class:
        cam = by_cam[r["camera_code"]]
        frames = cam["frames"] or 0
        cam["detections"][r["label"]] = r["detections"]
        cam["peak"][r["label"]] = r["peak"]
        cam["in_view"][r["label"]] = round(r["detections"] / frames, 2) if frames else None
    for cam in by_cam.values():
        cam["vehicles_in_view"] = round(sum(v or 0 for k, v in cam["in_view"].items()
                                            if k in VEHICLE_CLASSES), 2)

    def total(label_ok) -> dict:
        """Across cameras: `in_view` is the sum of each camera's average, i.e. how many are in
        view across the network at a typical moment; `peak` is the busiest single frame."""
        rows = [(cam, k) for cam in by_cam.values() for k in cam["in_view"] if label_ok(k)]
        return {"detections": sum(cam["detections"][k] for cam, k in rows),
                "in_view": round(sum(cam["in_view"][k] or 0 for cam, k in rows), 1),
                "peak": max((cam["peak"][k] or 0 for cam, k in rows), default=0)}

    labels = sorted({k for cam in by_cam.values() for k in cam["in_view"]})
    frames = sum(cam["frames"] or 0 for cam in by_cam.values())
    return {
        "since": since, "until": until,
        "status": "reporting" if frames else "no data",
        "frames": frames,
        "cameras_reporting": sum(1 for cam in by_cam.values() if cam["frames"]),
        "classes": {k: total(lambda x, k=k: x == k) for k in labels},
        "people": total(lambda x: x == "person"),
        "vehicles": {**total(lambda x: x in VEHICLE_CLASSES),
                     "peak": max((cam["vehicle_peak"] or 0 for cam in by_cam.values()), default=0)},
        "per_camera": list(by_cam.values()),
    }


@router.get("/reports/gaps")
async def gaps(_: User = Depends(require("reports.read")),
               conn: asyncpg.Connection = Depends(get_conn)):
    """Gap analysis (Model 1): uncovered zones, where the network is thin, blind or offline, and ageing
    infrastructure: cameras past the replacement age, AMCs or warranties expired or ending, cameras under
    maintenance or faulty. Decommissioned cameras are left out of the ageing findings."""
    rows = await conn.fetch("SELECT * FROM v_coverage_gaps ORDER BY total_cameras DESC, district")
    items = rows_to_dicts(rows)
    findings = []
    for r in items:
        if r["total_cameras"] == 0:
            findings.append({"district": r["district"], "severity": "high",
                             "finding": "no cameras registered"})
        elif r["anpr_cameras"] == 0:
            findings.append({"district": r["district"], "severity": "medium",
                             "finding": f"{r['total_cameras']} cameras, none ANPR-viable"})
        # Uptime counts only cameras whose health is known: a district of never-probed cameras is not "0% up".
        if r["offline_cameras"] and (r["uptime_pct"] or 0) < 70:
            findings.append({"district": r["district"], "severity": "high",
                             "finding": f"uptime {r['uptime_pct']}% ({r['offline_cameras']} offline)"})
    age = get_settings().ageing_years
    ageing = await conn.fetch(
        """SELECT COALESCE(d.name, 'No district') AS district,
                  count(*) FILTER (WHERE c.install_year <= extract(year FROM now())::int - $1) AS old,
                  min(c.install_year) AS oldest,
                  count(*) FILTER (WHERE c.amc_expiry < current_date) AS amc_expired,
                  count(*) FILTER (WHERE c.amc_expiry >= current_date
                                     AND c.amc_expiry < current_date + 90) AS amc_ending,
                  count(*) FILTER (WHERE c.maintenance IN ('under_maintenance', 'faulty')) AS maintenance
           FROM cameras c LEFT JOIN districts d ON d.id = c.district_id
           WHERE c.maintenance <> 'decommissioned'
           GROUP BY 1 ORDER BY 1""", age)
    for r in ageing:
        if r["amc_expired"]:
            findings.append({"district": r["district"], "severity": "high",
                             "finding": f"{r['amc_expired']} camera(s) with the AMC or warranty expired"})
        if r["old"]:
            findings.append({"district": r["district"], "severity": "medium",
                             "finding": f"{r['old']} camera(s) installed {age}+ years ago (oldest {r['oldest']}): "
                                        "plan replacement"})
        if r["amc_ending"]:
            findings.append({"district": r["district"], "severity": "medium",
                             "finding": f"{r['amc_ending']} AMC or warranty ending within 90 days"})
        if r["maintenance"]:
            findings.append({"district": r["district"], "severity": "medium",
                             "finding": f"{r['maintenance']} camera(s) under maintenance or faulty"})
    unknown = await conn.fetchval("SELECT count(*) FROM cameras WHERE install_year IS NULL "
                                  "AND maintenance <> 'decommissioned'")
    if unknown:
        findings.append({"district": "Statewide", "severity": "low",
                         "finding": f"installation year not recorded for {unknown} camera(s): ageing cannot be "
                                    "assessed for them (collect it on the department sheet)"})
    return {"districts": items, "findings": findings, "ageing_years": age}


@router.get("/reports/uptime")
async def uptime(hours: int = Query(24, ge=1, le=720), user: User = Depends(require("reports.read")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, alias="c", start_idx=2)
    rows = await conn.fetch(
        f"""SELECT c.camera_code, c.name, dept.code AS department_code,
                   count(h.id) AS checks,
                   round(100.0 * count(h.id) FILTER (WHERE h.reachable) / NULLIF(count(h.id),0), 1)
                     AS uptime_pct,
                   round(avg(h.latency_ms)) AS avg_latency_ms,
                   max(h.checked_at) FILTER (WHERE h.reachable) AS last_reachable
            FROM cameras c JOIN departments dept ON dept.id = c.department_id
            LEFT JOIN camera_health_checks h ON h.camera_id = c.id
                 AND h.checked_at > now() - ($1 || ' hours')::interval
            WHERE {where}
            GROUP BY c.camera_code, c.name, dept.code ORDER BY uptime_pct NULLS LAST, c.camera_code""",
        str(hours), *params)
    return rows_to_dicts(rows)


@router.get("/audit")
async def audit_log(actor: str | None = None, action: str | None = None,
                    since: datetime | None = None, until: datetime | None = None,
                    limit: int = Query(200, ge=0, le=5000),
                    _: User = Depends(require("audit.read")),
                    conn: asyncpg.Connection = Depends(get_conn)):
    filters, params = ["TRUE"], []
    if actor:
        params.append(actor)
        filters.append(f"actor_name = ${len(params)}")
    if action:
        params.append(f"{like_escape(action)}%")
        filters.append(f"action LIKE ${len(params)}")
    if since:
        params.append(since)
        filters.append(f"at >= ${len(params)}")
    if until:
        params.append(until)
        filters.append(f"at <= ${len(params)}")
    params.append(limit)
    rows = await conn.fetch(
        f"""SELECT id, at, actor_name, action, object_type, object_id, purpose, ip::text, detail
            FROM audit_log WHERE {' AND '.join(filters)} ORDER BY at DESC LIMIT ${len(params)}""",
        *params)
    return rows_to_dicts(rows)
