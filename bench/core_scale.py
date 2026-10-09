"""The core at statewide size: registry, map, reports, movement search and ingest with
80,000 cameras, a 100,000-entry watchlist and millions of sightings.

Builds a separate database (sentinel_scale) in the running Postgres from the same init SQL
and upgrades, seeds it, starts a second API on :8001 against it (own bus channel, no health
probing, so nothing reaches the live control room), measures, and drops the database.

    uv run --no-sync python bench/core_scale.py [--sightings 3000000] [--keep]
Writes bench/results/core_scale.md.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import platform
import random
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = "sentinel_scale"
PORT = 8001
API = f"http://localhost:{PORT}"
TRACKED = "GJ01TR0001"


def psql(sql: str, db: str = "sentinel") -> str:
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "sentinel",
                        "-d", db, "-q", "-c", sql], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:500])
    return r.stdout


def psql_file(path: Path, db: str) -> None:
    with path.open("rb") as f:
        r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U",
                            "sentinel", "-d", db, "-q", "-f", "-"], cwd=ROOT, stdin=f, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace")[:500])


def dsn(db: str) -> str:
    from sentinel_api.config import get_settings
    base = get_settings().pg_dsn
    return base.rsplit("/", 1)[0] + "/" + db


SEED = """
WITH dep AS (SELECT array_agg(id ORDER BY id) a FROM departments),
     dis AS (SELECT array_agg(id ORDER BY id) ids, array_agg(ST_X(centroid::geometry) ORDER BY id) xs,
                    array_agg(ST_Y(centroid::geometry) ORDER BY id) ys FROM districts)
INSERT INTO cameras (camera_code, name, department_id, district_id, location, camera_class, mode, rtsp_url,
                     anpr_viable, analytics_enabled, health, retention_days, storage, codec, resolution, fps)
SELECT 'S-' || lpad(i::text, 5, '0'), 'Scale test camera ' || i,
       dep.a[1 + i % array_length(dep.a, 1)],
       dis.ids[1 + i % array_length(dis.ids, 1)],
       ST_SetSRID(ST_MakePoint(dis.xs[1 + i % array_length(dis.ids, 1)] + (random() - 0.5) * 0.25,
                               dis.ys[1 + i % array_length(dis.ids, 1)] + (random() - 0.5) * 0.25), 4326)::geography,
       (CASE WHEN i % 10 = 0 THEN 'anpr' ELSE 'fixed' END)::camera_class, 'ip_rtsp',
       'rtsp://10.0.' || (i / 250) || '.' || (i % 250) || ':554/stream', i % 10 = 0, i % 10 = 0,
       (CASE WHEN i % 20 = 0 THEN 'offline' WHEN i % 33 = 0 THEN 'degraded' ELSE 'online' END)::health_state,
       7 + (i % 3) * 4, 'local'::storage_mode, 'H.264', '1920x1080', 25
FROM generate_series(1, 80000) AS i, dep, dis;
"""

PLATE = ("'GJ' || lpad((1 + j % 38)::text, 2, '0') || chr(65 + (j / 38) % 26) || chr(65 + (j / 988) % 26) "
         "|| lpad(((j * 31) % 10000)::text, 4, '0')")


def plate_of(j: int) -> str:
    return f"GJ{1 + j % 38:02d}{chr(65 + (j // 38) % 26)}{chr(65 + (j // 988) % 26)}{(j * 31) % 10000:04d}"


async def seed(n_sightings: int, pool: int) -> dict:
    conn = await asyncpg.connect(dsn(DB))
    t = {}
    try:
        t0 = time.perf_counter(); await conn.execute(SEED); t["cameras_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        await conn.execute(f"""
            WITH anpr AS (SELECT array_agg(id ORDER BY camera_code) a FROM cameras WHERE anpr_viable)
            INSERT INTO vehicle_sightings (camera_id, event_ts, plate_text, plate_norm, ocr_conf, det_conf, bbox, track_id)
            SELECT anpr.a[1 + ((i::bigint * 7919) % array_length(anpr.a, 1))::int], now() - random() * interval '30 days',
                   p, p, 0.9, 0.9, ARRAY[0, 0, 40, 12], 'scale'
            FROM anpr, generate_series(1, {n_sightings}) AS i,
                 LATERAL (SELECT {PLATE} AS p FROM (SELECT i % {pool} AS j) s) q""")
        # A vehicle to trace: 60 sightings on 20 ANPR cameras over 30 days.
        await conn.execute(f"""
            WITH c AS (SELECT id FROM cameras WHERE anpr_viable ORDER BY camera_code LIMIT 20)
            INSERT INTO vehicle_sightings (camera_id, event_ts, plate_text, plate_norm, ocr_conf, det_conf, bbox, track_id)
            SELECT (SELECT id FROM c OFFSET (k % 20) LIMIT 1), now() - (k || ' hours')::interval,
                   '{TRACKED}', '{TRACKED}', 0.95, 0.9, ARRAY[0, 0, 40, 12], 'scale'
            FROM generate_series(1, 60) AS k""")
        t["sightings_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        await conn.execute(f"""
            INSERT INTO watchlist_entries (kind, plate_norm, severity, source, reason)
            SELECT 'stolen_vehicle', p, 'high', 'scale', 'core scale benchmark'
            FROM generate_series(1, 100000) AS i,
                 LATERAL (SELECT {PLATE} AS p FROM (SELECT {pool} + i AS j) s) q""")   # not in the pool: no alert storm
        await conn.execute(f"""INSERT INTO watchlist_entries (kind, plate_norm, severity, source, reason)
                               SELECT 'stolen_vehicle', {PLATE}, 'high', 'scale', 'hit'
                               FROM generate_series(0, 99) AS j""")       # 100 pool plates: some ingest reads alert
        t["watchlist_s"] = time.perf_counter() - t0
        await conn.execute("ANALYZE")
        t["counts"] = dict(await conn.fetchrow(
            """SELECT (SELECT count(*) FROM cameras) AS cameras,
                      (SELECT count(*) FROM cameras WHERE anpr_viable) AS anpr_cameras,
                      (SELECT count(*) FROM vehicle_sightings) AS sightings,
                      (SELECT count(*) FROM watchlist_entries) AS watchlist,
                      (SELECT pg_size_pretty(pg_database_size(current_database()))) AS db_size"""))
    finally:
        await conn.close()
    return t


async def timed_get(c: httpx.AsyncClient, path: str, h: dict, n: int) -> dict:
    ms, size = [], 0
    for _ in range(n):
        t0 = time.perf_counter()
        r = await c.get(path, headers=h)
        r.raise_for_status()
        ms.append((time.perf_counter() - t0) * 1000)
        size = len(r.content)
    return {"n": n, "median_ms": statistics.median(ms), "max_ms": max(ms), "bytes": size}


async def ingest_load(c: httpx.AsyncClient, key: str, cams: list[str], seconds: float, clients: int, batch: int,
                      pool: int) -> dict:
    stop = time.perf_counter() + seconds
    lat, stored, alerts = [], 0, 0

    async def one(k: int):
        nonlocal stored, alerts
        rng = random.Random(k)
        while time.perf_counter() < stop:
            now = datetime.now(timezone.utc).isoformat()
            body = [{"camera_code": rng.choice(cams), "event_ts": now, "plate_text": plate_of(rng.randrange(pool)),
                     "ocr_conf": 0.9, "det_conf": 0.9, "bbox": [0, 0, 40, 12], "track_id": "scale", "reads": 3}
                    for _ in range(batch)]
            t0 = time.perf_counter()
            r = await c.post("/ingest/sightings", json=body, headers={"X-Ingest-Key": key},
                             params={"batch_id": uuid.uuid4().hex})
            lat.append((time.perf_counter() - t0) * 1000)
            j = r.json()
            stored += j.get("stored", 0); alerts += j.get("alerts", 0)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(k) for k in range(clients)))
    el = time.perf_counter() - t0
    q = statistics.quantiles(lat, n=100)
    return {"clients": clients, "batch": batch, "seconds": round(el, 1), "stored": stored, "alerts": alerts,
            "per_s": stored / el, "median_ms": statistics.median(lat), "p95_ms": q[94]}


async def measure(pool: int) -> dict:
    key = os.environ.get("INGEST_KEY", "dev_ingest_key_replace_me")
    async with httpx.AsyncClient(base_url=API, timeout=300) as c:
        tok = (await c.post("/auth/login", json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        m = {
            "cameras page (100)": await timed_get(c, "/cameras?limit=100", h, 10),
            "cameras, one department": await timed_get(c, "/cameras?limit=100&department=GSRTC", h, 10),
            "map, whole registry as one GeoJSON (before)": await timed_get(c, "/gis/cameras.geojson?limit=100000", h, 3),
            "map, state view: clusters (zoom 7)": await timed_get(c, "/gis/clusters?zoom=7", h, 5),
            "map, district view: clusters (zoom 10)": await timed_get(c, "/gis/clusters?zoom=10&bbox=72.3,22.8,72.9,23.3", h, 5),
            "map, street view: cameras in view (zoom 13)": await timed_get(c, "/gis/cameras.geojson?limit=3000&bbox=72.50,22.98,72.62,23.08", h, 5),
            "gap-analysis report": await timed_get(c, "/reports/gaps", h, 3),
            "fleet report": await timed_get(c, "/reports/fleet", h, 3),
            f"movement history ({TRACKED}, 30 days, fuzzy)": await timed_get(c, f"/sightings/movement/{TRACKED}?purpose=scale", h, 10),
            "watchlist check (100k entries)": await timed_get(c, f"/watchlist/check/{TRACKED}", h, 10),
        }
        cams = [f"S-{i:05d}" for i in range(10, 80001, 10)]      # the ANPR cameras
        m["ingest"] = await ingest_load(c, key, cams, 60, 8, 50, pool)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sightings", type=int, default=3_000_000)
    ap.add_argument("--pool", type=int, default=300_000, help="distinct plates the sightings are drawn from")
    ap.add_argument("--keep", action="store_true", help="keep the sentinel_scale database afterwards")
    a = ap.parse_args()
    print("creating", DB); psql(f"DROP DATABASE IF EXISTS {DB}"); psql(f"CREATE DATABASE {DB}")
    for f in sorted((ROOT / "infra" / "postgres" / "init").glob("*.sql")):
        psql_file(f, DB)
    from sentinel_api import upgrades
    async def up():
        conn = await asyncpg.connect(dsn(DB)); await upgrades.apply_upgrades(conn); await conn.close()
    asyncio.run(up())
    print("seeding"); t = asyncio.run(seed(a.sightings, a.pool)); print(t)

    env = {**os.environ, "DATABASE_URL": dsn(DB).replace("postgresql://", "postgresql+asyncpg://"),
           "BUS_CHANNEL": "sentinel:scale-bench", "HEALTH_MONITOR": "false", "PYTHONUTF8": "1"}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "sentinel_api.main:app", "--host", "127.0.0.1",
                            "--port", str(PORT)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{API}/docs", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        m = asyncio.run(measure(a.pool))
    finally:
        api.terminate(); api.wait(timeout=20)
        if not a.keep:
            psql(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")

    c = t["counts"]
    rows = [f"| {k} | {v['n']} | {v['median_ms']:.0f} | {v['max_ms']:.0f} | {v['bytes'] / 1e6:.2f} |" for k, v in m.items() if k != "ingest"]
    g = m["ingest"]
    lines = [
        "# The core at statewide size",
        "",
        f"Measured {datetime.now().astimezone():%Y-%m-%d %H:%M %Z} on {platform.node()} by `bench/core_scale.py`: one API process",
        "(uvicorn, one worker) and PostgreSQL in Docker Desktop on the same GTX 1650 Ti laptop as everything else; a separate",
        f"database seeded with {c['cameras']:,} cameras ({c['anpr_cameras']:,} ANPR) across 33 districts, {c['sightings']:,} sightings",
        f"over 30 days drawn from {a.pool:,} plates, {c['watchlist']:,} watchlist entries ({c['db_size']}). Seeding took",
        f"{t['cameras_s']:.0f} s (cameras), {t['sightings_s']:.0f} s (sightings), {t['watchlist_s']:.0f} s (watchlist). Times are",
        "round trips from a Python client on the same machine, admin user (statewide scope).",
        "",
        "| Request | Runs | Median ms | Max ms | Response MB |",
        "|---|---|---|---|---|",
        *rows,
        "",
        f"**Ingest**: {g['clients']} concurrent clients posting batches of {g['batch']} sightings for {g['seconds']} s, each read",
        "matched against the 100,000-entry watchlist in the same request: "
        f"**{g['per_s']:.0f} sightings/s** sustained ({g['stored']:,} stored, {g['alerts']} alerts raised), request median",
        f"{g['median_ms']:.0f} ms, p95 {g['p95_ms']:.0f} ms. The capacity model's statewide average is 556 sightings/s.",
        "",
        "One laptop, one API process, database on the same disk: a floor for the core, not a sizing. Above 2,000 cameras the",
        "control-room map switches from the whole registry to clusters per grid cell, and to the cameras in view once zoomed in.",
    ]
    out = ROOT / "bench" / "results" / "core_scale.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
