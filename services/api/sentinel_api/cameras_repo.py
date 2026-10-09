"""Camera registry persistence shared by create, bulk import and catalogue sync."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import asyncpg

from .db import department_id, district_id

_SAFE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_STREAM = re.compile(r"^(rtsps?|rtmps?|https?|srt|udp)://", re.I)


def validate_fields(row: dict[str, Any]) -> None:
    """The registry's code and stream fields reach places that trust them: a worker makes a folder from the code
    and hands the address to FFmpeg, a browser fetches it. So on every write path (API, CSV import, catalogue
    sync) the code is letters, digits, - and _ only, upper-cased here, and an address is a stream scheme."""
    code = str(row.get("camera_code") or "").upper()
    if not _SAFE_CODE.match(code):
        raise ValueError(f"camera_code {code!r}: letters, digits, - and _ only, 3 to 64 characters")
    row["camera_code"] = code
    for k in ("rtsp_url", "hls_url", "whep_url", "onvif_url"):
        v = row.get(k)
        if v and not _STREAM.match(str(v)):
            raise ValueError(f"{k} must be an rtsp, rtmp, http, srt or udp address")
    if row.get("maintenance") and row["maintenance"] not in MAINTENANCE:
        raise ValueError(f"maintenance must be one of {', '.join(MAINTENANCE)}")
    if isinstance(row.get("amc_expiry"), str):
        try:
            row["amc_expiry"] = date.fromisoformat(row["amc_expiry"])
        except ValueError:
            raise ValueError("amc_expiry must be a date, YYYY-MM-DD") from None
    year = row.get("install_year")
    if year is not None and not 1990 <= int(year) <= 2100:
        raise ValueError("install_year must be between 1990 and 2100")


MAINTENANCE = ("in_service", "under_maintenance", "faulty", "decommissioned")

CAMERA_SELECT = """
SELECT c.id, c.camera_code, c.name, dept.code AS department_code, dept.name AS department,
       d.name AS district,
       ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon,
       c.address, c.taluka, c.landmark, c.bearing_deg,
       c.camera_class::text, c.mode::text, c.ownership::text,
       c.vendor, c.model, c.codec, c.resolution, c.fps, c.retention_days, c.storage::text,
       c.rtsp_url, c.whep_url, c.hls_url, c.onvif_url,
       c.anpr_viable, c.analytics_enabled, c.health::text, c.last_seen_at, c.tags,
       c.maintenance, c.maintenance_note, c.install_year, c.amc_expiry,
       c.created_at, c.updated_at
FROM cameras c
JOIN departments dept ON dept.id = c.department_id
LEFT JOIN districts d ON d.id = c.district_id
"""


async def upsert_camera(conn: asyncpg.Connection, row: dict[str, Any], user=None) -> str:
    """Insert or update by camera_code. Returns 'inserted' or 'updated'.

    Raises ValueError on an unknown department or district so callers can
    report per-row errors from a bulk import instead of aborting the batch.
    """
    validate_fields(row)
    await assert_can_write(conn, user, row["camera_code"])
    dept = await department_id(conn, row.get("department_code"))
    if dept is None:
        raise ValueError(f"unknown department code {row.get('department_code')!r}")
    dist = await district_id(conn, row.get("district"))
    if row.get("district") and dist is None:
        raise ValueError(f"unknown district {row.get('district')!r}")

    lat, lon = row.get("lat"), row.get("lon")
    analytics = row.get("analytics_enabled")
    if analytics is None:
        analytics = bool(row.get("anpr_viable"))

    result = await conn.fetchrow(
        """
        INSERT INTO cameras (camera_code, name, department_id, district_id, location,
            address, taluka, landmark, bearing_deg, camera_class, mode, ownership,
            vendor, model, codec, resolution, fps, retention_days, storage,
            rtsp_url, whep_url, hls_url, onvif_url, anpr_viable, analytics_enabled, tags,
            maintenance, maintenance_note, install_year, amc_expiry)
        VALUES ($1, $2, $3, $4,
            CASE WHEN $5::float8 IS NULL OR $6::float8 IS NULL THEN NULL
                 ELSE ST_SetSRID(ST_MakePoint($6::float8, $5::float8), 4326)::geography END,
            $7, $8, $9, $10, $11::camera_class, $12::integration_mode, $13::ownership,
            $14, $15, $16, $17, $18, $19, $20::storage_mode,
            $21, $22, $23, $24, $25, $26, $27::jsonb,
            COALESCE($28, 'in_service'), $29, $30, $31)
        ON CONFLICT (camera_code) DO UPDATE SET
            name = EXCLUDED.name, department_id = EXCLUDED.department_id,
            district_id = COALESCE(EXCLUDED.district_id, cameras.district_id),
            location = COALESCE(EXCLUDED.location, cameras.location),
            address = COALESCE(EXCLUDED.address, cameras.address),
            taluka = COALESCE(EXCLUDED.taluka, cameras.taluka),
            landmark = COALESCE(EXCLUDED.landmark, cameras.landmark),
            bearing_deg = COALESCE(EXCLUDED.bearing_deg, cameras.bearing_deg),
            camera_class = EXCLUDED.camera_class, mode = EXCLUDED.mode,
            ownership = EXCLUDED.ownership,
            vendor = COALESCE(EXCLUDED.vendor, cameras.vendor),
            model = COALESCE(EXCLUDED.model, cameras.model),
            codec = COALESCE(EXCLUDED.codec, cameras.codec),
            resolution = COALESCE(EXCLUDED.resolution, cameras.resolution),
            fps = COALESCE(EXCLUDED.fps, cameras.fps),
            retention_days = COALESCE(EXCLUDED.retention_days, cameras.retention_days),
            storage = EXCLUDED.storage,
            rtsp_url = COALESCE(EXCLUDED.rtsp_url, cameras.rtsp_url),
            whep_url = COALESCE(EXCLUDED.whep_url, cameras.whep_url),
            hls_url = COALESCE(EXCLUDED.hls_url, cameras.hls_url),
            onvif_url = COALESCE(EXCLUDED.onvif_url, cameras.onvif_url),
            anpr_viable = EXCLUDED.anpr_viable, analytics_enabled = EXCLUDED.analytics_enabled,
            tags = cameras.tags || EXCLUDED.tags,
            maintenance = COALESCE($28, cameras.maintenance),
            maintenance_note = COALESCE($29, cameras.maintenance_note),
            install_year = COALESCE($30, cameras.install_year),
            amc_expiry = COALESCE($31, cameras.amc_expiry)
        RETURNING (xmax = 0) AS inserted
        """,
        row["camera_code"].strip().upper(), row["name"], dept, dist, lat, lon,
        row.get("address"), row.get("taluka"), row.get("landmark"), row.get("bearing_deg"),
        row.get("camera_class") or "fixed", row.get("mode") or "ip_rtsp",
        row.get("ownership") or "government",
        row.get("vendor"), row.get("model"), row.get("codec"), row.get("resolution"),
        row.get("fps"), row.get("retention_days"), row.get("storage") or "unknown",
        row.get("rtsp_url"), row.get("whep_url"), row.get("hls_url"), row.get("onvif_url"),
        bool(row.get("anpr_viable")), bool(analytics), row.get("tags") or {},
        row.get("maintenance"), row.get("maintenance_note"), row.get("install_year"), row.get("amc_expiry"),
    )
    return "inserted" if result["inserted"] else "updated"


class NotYourCamera(PermissionError):
    """A department- or district-scoped user tried to write a camera owned by someone else."""


async def assert_can_write(conn: asyncpg.Connection, user, code: str) -> None:
    """Scoped users may create cameras in their own scope and change only those; a camera code
    that already belongs to another department or district is not theirs to overwrite, relay or
    delete. Statewide users (user is None or has no scope) may write anything."""
    if user is None or (user.department_id is None and user.district_id is None):
        return
    row = await conn.fetchrow("SELECT department_id, district_id FROM cameras WHERE camera_code = $1",
                              code.strip().upper())
    if row is None:
        return
    if (user.department_id is not None and row["department_id"] != user.department_id) or \
            (user.district_id is not None and row["district_id"] != user.district_id):
        raise NotYourCamera(f"camera {code.upper()} belongs to another department or district")


def scope_clause(user, alias: str = "c", start_idx: int = 1) -> tuple[str, list[Any]]:
    """Department/district scoping for non-statewide users."""
    clauses, params = [], []
    if user.department_id is not None:
        params.append(user.department_id)
        clauses.append(f"{alias}.department_id = ${start_idx + len(params) - 1}")
    if user.district_id is not None:
        params.append(user.district_id)
        clauses.append(f"{alias}.district_id = ${start_idx + len(params) - 1}")
    return (" AND ".join(clauses) if clauses else "TRUE"), params
