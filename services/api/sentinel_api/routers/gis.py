"""Model 1: GIS layer. GeoJSON for the map, district coverage, proximity search.

At statewide size the map cannot take every camera in one response (80,000 cameras are a
45 MB GeoJSON and 6 s: bench/results/core_scale.md). So the map asks for clusters (counts
per grid cell, cell size from the zoom level) until it is zoomed in, then for the cameras
inside the visible box only. A small fleet still loads whole.
"""
from __future__ import annotations

import math

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, require
from ..cameras_repo import scope_clause
from ..db import get_conn, rows_to_dicts
from ..schemas import CameraClass, HealthState, Maintenance

router = APIRouter(prefix="/gis", tags=["gis"])


def _bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        w, s, e, n = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox is minLon,minLat,maxLon,maxLat")
    if not all(math.isfinite(v) for v in (w, s, e, n)) or not (-180 <= w <= 180 and -180 <= e <= 180
                                                               and -90 <= s <= 90 and -90 <= n <= 90):
        raise HTTPException(422, "bbox: longitudes within -180..180, latitudes within -90..90")
    return w, s, e, n


def _filters(user, department, health, anpr, bbox, camera_class=None, maintenance=None):
    where, params = scope_clause(user)
    filters = [where, "c.location IS NOT NULL"]
    if camera_class:
        params.append(camera_class)
        filters.append(f"c.camera_class = ${len(params)}::camera_class")
    if maintenance:
        params.append(maintenance)
        filters.append(f"c.maintenance = ${len(params)}")
    if department:
        params.append(department.upper())
        filters.append(f"dept.code = ${len(params)}")
    if health:
        params.append(health)
        filters.append(f"c.health = ${len(params)}::health_state")
    if anpr is not None:
        params.append(anpr)
        filters.append(f"c.anpr_viable = ${len(params)}")
    if bbox:
        params += list(bbox)
        i = len(params) - 3
        filters.append(f"c.location && ST_MakeEnvelope(${i}, ${i + 1}, ${i + 2}, ${i + 3}, 4326)::geography")
    return filters, params


@router.get("/clusters")
async def clusters(zoom: int = Query(7, ge=0, le=20), bbox: str | None = None,
                   department: str | None = None, health: HealthState | None = None, anpr: bool | None = None,
                   camera_class: CameraClass | None = None, maintenance: Maintenance | None = None,
                   user: User = Depends(require("cameras.read")),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Cameras counted per grid cell (about four cells per map tile), with health totals."""
    filters, params = _filters(user, department, health, anpr, _bbox(bbox), camera_class, maintenance)
    params.append(360.0 / (2 ** zoom) / 4)
    rows = await conn.fetch(
        f"""SELECT count(*) AS cameras,
                   count(*) FILTER (WHERE c.health = 'online') AS online,
                   count(*) FILTER (WHERE c.health = 'offline') AS offline,
                   count(*) FILTER (WHERE c.anpr_viable) AS anpr,
                   avg(ST_Y(c.location::geometry)) AS lat, avg(ST_X(c.location::geometry)) AS lon
            FROM cameras c JOIN departments dept ON dept.id = c.department_id
            WHERE {' AND '.join(filters)}
            GROUP BY ST_SnapToGrid(c.location::geometry, ${len(params)})""", *params)
    cells = rows_to_dicts(rows)
    return {"zoom": zoom, "total": sum(c["cameras"] for c in cells), "clusters": cells}


@router.get("/cameras.geojson")
async def cameras_geojson(department: str | None = None, health: HealthState | None = None,
                          anpr: bool | None = None, bbox: str | None = None,
                          camera_class: CameraClass | None = None, maintenance: Maintenance | None = None,
                          limit: int = Query(20000, ge=1, le=100000),
                          user: User = Depends(require("cameras.read")),
                          conn: asyncpg.Connection = Depends(get_conn)):
    """Cameras as GeoJSON; `bbox` (minLon,minLat,maxLon,maxLat) restricts to the visible map."""
    filters, params = _filters(user, department, health, anpr, _bbox(bbox), camera_class, maintenance)
    params.append(limit + 1)
    rows = await conn.fetch(
        f"""SELECT c.id, c.camera_code, c.name, dept.code AS department_code, dept.name AS department,
                   d.name AS district, c.camera_class::text, c.mode::text, c.codec, c.resolution,
                   c.health::text, c.anpr_viable, c.analytics_enabled, c.bearing_deg,
                   c.whep_url, c.hls_url, c.last_seen_at, c.vendor, c.retention_days,
                   c.maintenance, c.install_year, c.amc_expiry,
                   ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon
            FROM cameras c JOIN departments dept ON dept.id = c.department_id
            LEFT JOIN districts d ON d.id = c.district_id
            WHERE {' AND '.join(filters)}
            ORDER BY c.camera_code LIMIT ${len(params)}""", *params)
    truncated = len(rows) > limit
    features = []
    for r in rows[:limit]:
        props = dict(r)
        lat, lon = props.pop("lat"), props.pop("lon")
        props["id"] = str(props["id"])
        for k in ("last_seen_at", "amc_expiry"):
            if props[k]:
                props[k] = props[k].isoformat()
        features.append({"type": "Feature", "id": props["camera_code"],
                         "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": props})
    return {"type": "FeatureCollection", "features": features, "truncated": truncated}


@router.get("/districts")
async def district_coverage(user: User = Depends(require("cameras.read")),
                            conn: asyncpg.Connection = Depends(get_conn)):
    rows = await conn.fetch("SELECT * FROM v_coverage_gaps ORDER BY district")
    return rows_to_dicts(rows)


@router.get("/nearby")
async def nearby(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                 radius_m: int = Query(1000, ge=50, le=50000), limit: int = Query(50, ge=0, le=500),
                 user: User = Depends(require("cameras.read")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    """Cameras within a radius, nearest first. This is the 'what saw this spot' query."""
    where, params = scope_clause(user, start_idx=5)
    rows = await conn.fetch(
        f"""SELECT c.camera_code, c.name, dept.code AS department_code, c.health::text,
                   c.anpr_viable, c.whep_url, c.hls_url,
                   ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon,
                   round(ST_Distance(c.location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography))
                     AS distance_m
            FROM cameras c JOIN departments dept ON dept.id = c.department_id
            WHERE c.location IS NOT NULL
              AND ST_DWithin(c.location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3)
              AND {where}
            ORDER BY distance_m LIMIT $4""",
        lat, lon, radius_m, limit, *params)
    return rows_to_dicts(rows)
