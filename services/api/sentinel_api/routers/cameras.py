"""Model 1: camera registry. CRUD, bulk CSV import, API onboarding from a
catalogue endpoint, CSV export, and per-camera health history."""
from __future__ import annotations

import csv
import io
import math
from typing import Any, Literal
from urllib.parse import urlsplit

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from ..audit import audit
from ..auth import User, require
from ..cameras_repo import CAMERA_SELECT, NotYourCamera, scope_clause, upsert_camera
from ..catalogue import fetch_catalogue, map_item
from ..config import get_settings
from ..db import get_conn, like_escape, rows_to_dicts
from ..mediamtx import mask_url
from ..schemas import (CameraClass, CameraIn, CameraOut, CameraPatch, HealthCheckOut, HealthState, ImportResult,
                       IntegrationMode, Maintenance)

router = APIRouter(prefix="/cameras", tags=["cameras"])

CSV_COLUMNS = ["camera_code", "name", "department_code", "district", "lat", "lon", "address",
               "taluka", "landmark", "bearing_deg", "camera_class", "mode", "ownership", "vendor",
               "model", "codec", "resolution", "fps", "retention_days", "storage", "rtsp_url",
               "whep_url", "hls_url", "onvif_url", "anpr_viable", "analytics_enabled",
               "maintenance", "maintenance_note", "install_year", "amc_expiry"]

_BOOL = {"1", "true", "yes", "y", "t"}
MAX_IMPORT_BYTES = 10 * 2**20   # 10 MB: about 50,000 cameras; a bigger file is a mistake or an attack


def _coerce_csv_row(raw: dict[str, str]) -> dict[str, Any]:
    row: dict[str, Any] = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
    for k in ("lat", "lon", "fps", "retention_days", "bearing_deg", "install_year"):
        if not row.get(k):
            row[k] = None
            continue
        v = float(row[k])
        if not math.isfinite(v):         # "nan", "inf", "1e400": int() would raise OverflowError, not ValueError
            raise ValueError(f"{k} {row[k]!r} is not a number")
        row[k] = v if k in ("lat", "lon") else int(v)
    if row.get("maintenance"):           # "Under maintenance" as a person types it
        row["maintenance"] = "_".join(row["maintenance"].lower().split())
    # the same bounds the API applies (schemas.CameraIn): the database would refuse the row less clearly
    for k, lo, hi in (("fps", 0, 240), ("retention_days", 0, 3650), ("bearing_deg", 0, 359), ("lat", -90, 90),
                      ("lon", -180, 180)):
        if row.get(k) is not None and not lo <= row[k] <= hi:
            raise ValueError(f"{k} {row[k]} is outside {lo} to {hi}")
    for k in ("anpr_viable",):
        row[k] = str(row.get(k, "")).lower() in _BOOL
    ae = str(row.get("analytics_enabled", "")).strip().lower()
    row["analytics_enabled"] = (ae in _BOOL) if ae else None
    for k in list(row):
        if row[k] == "":
            row[k] = None
    return row


@router.get("", response_model=dict)
async def list_cameras(
    request: Request,
    department: str | None = None, district: str | None = None,
    health: HealthState | None = None, anpr: bool | None = None, mode: IntegrationMode | None = None,
    camera_class: CameraClass | None = None, maintenance: Maintenance | None = None,
    q: str | None = Query(None, description="search code / name / address"),
    limit: int = Query(200, ge=0, le=2000), offset: int = Query(0, ge=0, le=10_000_000),
    user: User = Depends(require("cameras.read")), conn: asyncpg.Connection = Depends(get_conn),
):
    where, params = scope_clause(user)
    filters = [where]

    def add(cond: str, val: Any):
        params.append(val)
        filters.append(cond.replace("?", f"${len(params)}"))

    if department:
        add("dept.code = upper(?)", department)
    if district:
        add("lower(d.name) = lower(?)", district)
    if health:
        add("c.health = ?::health_state", health)
    if anpr is not None:
        add("c.anpr_viable = ?", anpr)
    if mode:
        add("c.mode = ?::integration_mode", mode)
    if camera_class:
        add("c.camera_class = ?::camera_class", camera_class)
    if maintenance:
        add("c.maintenance = ?", maintenance)
    if q:  # all three placeholders bind the same parameter
        add("(c.camera_code ILIKE ? OR c.name ILIKE ? OR c.address ILIKE ?)", f"%{like_escape(q)}%")
    sql = CAMERA_SELECT + " WHERE " + " AND ".join(filters)
    total = await conn.fetchval(f"SELECT count(*) FROM ({sql}) t", *params)
    params += [limit, offset]
    rows = await conn.fetch(sql + f" ORDER BY c.camera_code LIMIT ${len(params)-1} OFFSET ${len(params)}",
                            *params)
    return {"total": total, "items": [masked(d) for d in rows_to_dicts(rows)]}


def masked(cam: dict) -> dict:
    """A camera as readers see it: a stream address that carries credentials (one registered through the API or a
    CSV rather than onboarded through the relay) shows them as ***. Workers get the real address from
    /ingest/cameras; relay addresses have no credentials and are unchanged."""
    for k in ("rtsp_url", "onvif_url", "hls_url", "whep_url"):
        if cam.get(k):
            cam[k] = mask_url(cam[k])
    return cam


@router.get("/export.csv")
async def export_csv(request: Request, user: User = Depends(require("cameras.read")),
                     conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user)
    rows = await conn.fetch(CAMERA_SELECT + f" WHERE {where} ORDER BY c.camera_code", *params)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(masked(dict(r)))
    buf.seek(0)
    await audit(conn, request, user, "camera.export", "csv", "cameras.csv", rows=len(rows))
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=cameras.csv"})


@router.get("/template.csv")
async def template_csv(_: User = Depends(require("cameras.read"))):
    sample = ("GNR-POL-099,Sample Junction Camera,HOME,Gandhinagar,23.2233,72.6503,"
              "Sector 21 Circle,Gandhinagar,,90,anpr,ip_rtsp,government,Hikvision,DS-2CD,H.264,"
              "1920x1080,25,15,local,rtsp://10.0.0.5:554/stream1,,,,true,true,in_service,,2021,2027-03-31\n")
    return StreamingResponse(iter([",".join(CSV_COLUMNS) + "\n" + sample]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=cameras_template.csv"})


@router.get("/{code}", response_model=CameraOut)
async def get_camera(code: str, user: User = Depends(require("cameras.read")),
                     conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, start_idx=2)
    row = await conn.fetchrow(CAMERA_SELECT + f" WHERE c.camera_code = $1 AND {where}",
                              code.upper(), *params)
    if row is None:
        raise HTTPException(404, "camera not found")
    return masked(dict(row))


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def create_camera(body: CameraIn, request: Request,
                        user: User = Depends(require("cameras.write")),
                        conn: asyncpg.Connection = Depends(get_conn)):
    if not user.statewide:
        dept = await conn.fetchval("SELECT code FROM departments WHERE id = $1", user.department_id)
        if body.department_code.upper() != dept:
            raise HTTPException(403, "cannot onboard cameras for another department")
    try:
        outcome = await upsert_camera(conn, body.model_dump(), user)
    except NotYourCamera as e:
        raise HTTPException(403, str(e))
    except ValueError as e:                 # unknown department or district, a bad code or stream address
        raise HTTPException(422, str(e))
    await audit(conn, request, user, f"camera.{outcome}", "camera", body.camera_code)
    row = await conn.fetchrow(CAMERA_SELECT + " WHERE c.camera_code = $1", body.camera_code.upper())
    return dict(row)


# Fields an edit may not empty: the registry needs them on every camera.
REQUIRED_ON_EDIT = ("name", "camera_class", "mode", "storage", "anpr_viable", "analytics_enabled", "maintenance")
# Fields an edit may clear (a fixed list: the names go into the SQL).
CLEARABLE = ("address", "taluka", "landmark", "bearing_deg", "vendor", "model", "codec", "resolution", "fps",
             "retention_days", "maintenance_note", "install_year", "amc_expiry", "district")
CLEAR_COLUMN = {"district": "district_id"}      # a field whose column has another name


@router.patch("/{code}", response_model=CameraOut)
async def patch_camera(code: str, body: CameraPatch, request: Request,
                       user: User = Depends(require("cameras.write")),
                       conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, start_idx=2)
    existing = await conn.fetchrow(CAMERA_SELECT + f" WHERE c.camera_code = $1 AND {where}",
                                   code.upper(), *params)
    if existing is None:
        raise HTTPException(404, "camera not found")
    sent = body.model_dump(exclude_unset=True)
    required = [k for k in REQUIRED_ON_EDIT if k in sent and sent[k] is None]
    if required:
        raise HTTPException(422, f"{', '.join(required)} cannot be cleared")
    if ("lat" in sent and sent["lat"] is None) != ("lon" in sent and sent["lon"] is None):
        raise HTTPException(422, "clear latitude and longitude together, or neither")
    merged = dict(existing)
    merged.update(sent)
    if not user.statewide and (merged.get("department_code") or "").upper() != existing["department_code"]:
        raise HTTPException(403, "a department-scoped user cannot move a camera to another department")
    try:
        async with conn.transaction():
            await upsert_camera(conn, merged, user)
            # upsert keeps a stored value when none is given (bulk paths send partial rows); an edit that clears a
            # field sends null on purpose, so clear it here.
            cleared = [k for k, v in sent.items() if v is None and k in CLEARABLE]
            if "lat" in sent and "lon" in sent and sent["lat"] is None and sent["lon"] is None:
                cleared.append("location")
            if cleared:
                sets = ", ".join(f"{CLEAR_COLUMN.get(k, k)} = NULL" for k in cleared)
                await conn.execute(f"UPDATE cameras SET {sets} WHERE camera_code = $1", code.upper())
    except NotYourCamera as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    await audit(conn, request, user, "camera.updated", "camera", code.upper(),
                fields=list(body.model_dump(exclude_unset=True)))
    return dict(await conn.fetchrow(CAMERA_SELECT + " WHERE c.camera_code = $1", code.upper()))


@router.delete("/{code}", status_code=204)
async def delete_camera(code: str, request: Request, user: User = Depends(require("*")),
                        conn: asyncpg.Connection = Depends(get_conn)):
    n = await conn.execute("DELETE FROM cameras WHERE camera_code = $1", code.upper())
    if n.endswith("0"):
        raise HTTPException(404, "camera not found")
    await audit(conn, request, user, "camera.deleted", "camera", code.upper())


@router.post("/import", response_model=ImportResult)
async def import_csv(request: Request, file: UploadFile,
                     user: User = Depends(require("cameras.write")),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """Bulk onboarding. Upserts by camera_code; bad rows are reported, not fatal."""
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, f"at most {MAX_IMPORT_BYTES // 2**20} MB per import")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:                # Excel on Windows saves "CSV" in the ANSI code page
        text = data.decode("cp1252", errors="replace")
    # newline="": a lone carriage return (old Excel for Mac) is a line break, not a broken field
    reader = csv.DictReader(io.StringIO(text, newline=""))
    result = ImportResult()
    try:
        fields = reader.fieldnames
    except csv.Error as e:
        raise HTTPException(422, f"not a readable CSV file: {e}") from None
    if not text.strip() or fields is None:
        raise HTTPException(422, "the file is empty")
    missing = [c for c in ("camera_code", "name", "department_code") if c not in fields]
    if missing:
        raise HTTPException(422, f"missing column(s): {', '.join(missing)} (download the template)")
    rows = iter(enumerate(reader, start=2))
    async with conn.transaction():
        while True:
            try:
                i, raw = next(rows)
            except StopIteration:
                break
            except csv.Error as e:            # the file breaks off mid-way: nothing from it is kept
                raise HTTPException(422, f"not a readable CSV file at line {reader.line_num}: {e}") from None
            try:
                # Each row in its own savepoint: a row the database refuses rolls back alone, instead of
                # aborting the transaction and with it every row before and after.
                async with conn.transaction():
                    row = _coerce_csv_row(raw)
                    if not user.statewide:
                        dept = await conn.fetchval("SELECT code FROM departments WHERE id = $1",
                                                   user.department_id)
                        if (row.get("department_code") or "").upper() != dept:
                            raise ValueError("row belongs to another department")
                    outcome = await upsert_camera(conn, row, user)
                setattr(result, outcome, getattr(result, outcome) + 1)
            except (ValueError, KeyError, TypeError, NotYourCamera, asyncpg.PostgresError) as e:
                result.errors.append({"line": i, "camera_code": raw.get("camera_code"), "error": str(e)[:300]})
    await audit(conn, request, user, "camera.bulk_import", "csv", file.filename,
                inserted=result.inserted, updated=result.updated, errors=len(result.errors))
    return result


@router.post("/sync-catalogue", response_model=ImportResult)
async def sync_catalogue(request: Request, url: str | None = Query(None, max_length=2048),
                         default_department: str = Query("HOME", max_length=16),
                         analytics: Literal["anpr", "all", "none"] = "anpr",
                         dry_run: bool = False,
                         user: User = Depends(require("cameras.write")),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """API onboarding: read someone else's camera catalogue and register every camera.

    `url` may be the catalogue endpoint itself or just the host — the documented sandbox
    path (`/api/ingest`) and the other usual ones are tried in turn. Field names are mapped
    tolerantly (see catalogue.py): departments by code, seeded name or hint, coordinates in
    most shapes (checked against a Gujarat box), districts by name or spelling variant or
    from the coordinates. A record we cannot map is reported instead of failing the batch, and
    every guess is kept as a warning in the camera's tags.

    analytics: anpr (default) runs the analytics worker where the catalogue marks the camera
    ANPR-viable or explicitly asks for analytics (e.g. counts on a wide camera) · all runs it
    everywhere · none registers cameras for viewing only.
    dry_run: write nothing; the response adds `rows`, each camera as it would be registered
    (department, district, lat/lon, where the coordinates came from, warnings), so the
    mapping can be checked first.
    """
    if not user.statewide:     # a catalogue spans departments: syncing it is a statewide decision
        raise HTTPException(403, "catalogue sync is for statewide administrators")
    base = (url or get_settings().catalogue_url).strip().rstrip("/")
    try:
        parts = urlsplit(base)
        ok = parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:                        # "http://[::1": an unclosed address
        ok = False
    if not ok:
        raise HTTPException(422, "the catalogue URL must be http:// or https:// with a host")
    try:
        items, used = await fetch_catalogue(base)
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        raise HTTPException(502, f"catalogue unreachable: {e}")

    known_departments = {r["code"]: r["name"]
                         for r in await conn.fetch("SELECT code, name FROM departments")}
    if default_department.upper() not in known_departments:
        raise HTTPException(422, f"unknown default_department {default_department!r}")
    districts = await conn.fetch("""SELECT name, ST_Y(centroid::geometry) AS lat,
                                           ST_X(centroid::geometry) AS lon FROM districts""")
    known_districts = {r["name"].lower(): r["name"] for r in districts}
    centroids = {r["name"]: (r["lat"], r["lon"]) for r in districts if r["lat"] is not None}

    mapped = [(it, *map_item(it, known_departments=known_departments,
                             known_districts=known_districts,
                             default_department=default_department.upper(),
                             district_centroids=centroids)) for it in items]
    # Two records with one code (e.g. per-department numbering) would upsert into one camera.
    seen: dict[str, int] = {}
    for _, row, _ in mapped:
        if row is not None:
            seen[row["camera_code"]] = seen.get(row["camera_code"], 0) + 1

    result = ImportResult()
    preview: list[dict[str, Any]] = []
    for it, row, err in mapped:
        if row is None:
            result.errors.append({"camera_code": None, "error": err, "record": str(it)[:200]})
            continue
        if seen[row["camera_code"]] > 1:
            row["tags"]["catalogue_warnings"].append(
                f"camera code {row['camera_code']} appears {seen[row['camera_code']]} times in "
                "the catalogue; the records are merged into one camera")
        requested = row.pop("analytics_requested", False)
        row["analytics_enabled"] = analytics == "all" or (
            analytics == "anpr" and (row["anpr_viable"] or requested))
        row["tags"]["catalogue_url"] = used
        if dry_run:
            result.updated += 1
            preview.append({k: row[k] for k in ("camera_code", "name", "department_code", "district",
                                                "lat", "lon")}
                           | {"coord_source": row["tags"]["coord_source"],
                              "analytics_enabled": row["analytics_enabled"],
                              "warnings": row["tags"]["catalogue_warnings"]})
            continue
        try:
            outcome = await upsert_camera(conn, row)
            setattr(result, outcome, getattr(result, outcome) + 1)
        except (ValueError, asyncpg.PostgresError) as e:
            result.errors.append({"camera_code": row["camera_code"], "error": str(e)})
    if dry_run:
        # Returned as-is: the ImportResult response model would drop the preview rows.
        from fastapi.responses import JSONResponse
        return JSONResponse({**result.model_dump(), "dry_run": True, "catalogue_url": used,
                             "rows": preview})
    await audit(conn, request, user, "camera.catalogue_sync", "catalogue", used,
                inserted=result.inserted, updated=result.updated, errors=len(result.errors))
    return result


@router.get("/{code}/health", response_model=list[HealthCheckOut])
async def camera_health(code: str, hours: int = Query(24, ge=1, le=720),
                        user: User = Depends(require("cameras.read")),
                        conn: asyncpg.Connection = Depends(get_conn)):
    where, params = scope_clause(user, start_idx=3)
    rows = await conn.fetch(
        f"""SELECT h.checked_at, h.reachable, h.latency_ms, h.fps_observed, h.state::text, h.error
            FROM camera_health_checks h JOIN cameras c ON c.id = h.camera_id
            WHERE c.camera_code = $1 AND h.checked_at > now() - ($2 || ' hours')::interval AND {where}
            ORDER BY h.checked_at DESC LIMIT 2000""",
        code.upper(), str(hours), *params)
    return rows_to_dicts(rows)
