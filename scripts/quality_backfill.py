"""Grade the stored sightings that have no capture-quality row yet (services/api/sentinel_api/capture_quality.py).

New sightings are graded by the API after ingest; this catches up on everything stored before that existed,
or missed while the crop store was out of reach. Idempotent: a sighting already graded is left alone.
Run from the repo root (crop paths resolve against data/crops); the API must have started once since the
sighting_quality table was added, because it creates the table.

    PYTHONUTF8=1 uv run --no-sync python scripts/quality_backfill.py [--camera AMD-TRAF-001 ...] [--since 2026-09-25]

Prints counts only: no plate text, no crop file name (the names carry the plate).
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

import asyncpg

from sentinel_api import capture_quality as cq
from sentinel_api.config import get_settings
from sentinel_api.routers.quality import INSERT, grade

IST = timezone(timedelta(hours=5, minutes=30))
PAGE = 500
SQL = """SELECT s.id, s.event_ts, s.camera_id, s.crop_path, s.bbox, s.ocr_conf, c.camera_code
         FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
         WHERE s.crop_path IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sighting_quality q WHERE q.sighting_id = s.id AND q.sighting_ts = s.event_ts)
           AND ($1::text[] IS NULL OR c.camera_code = ANY($1::text[]))
           AND ($2::timestamptz IS NULL OR s.event_ts >= $2)
           AND (s.event_ts, s.id) > ($3, $4)
         ORDER BY s.event_ts, s.id LIMIT $5"""


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


async def run(cameras: list[str] | None, since: datetime | None) -> int:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        if await conn.fetchval("SELECT to_regclass('sighting_quality')") is None:
            print("sighting_quality does not exist yet: start the API once (it adds the table), then re-run")
            return 1
        seen, graded, quality, per_cam = 0, 0, Counter(), Counter()
        after = (datetime(1970, 1, 1, tzinfo=timezone.utc), 0)
        while True:
            page = await conn.fetch(SQL, cameras, since, *after, PAGE)
            if not page:
                break
            after = (page[-1]["event_ts"], page[-1]["id"])
            rows = await asyncio.to_thread(grade, [dict(r) for r in page])
            if rows:
                await conn.executemany(INSERT, rows)
            code = {r["id"]: r["camera_code"] for r in page}
            for row in rows:
                quality[row[12]] += 1
                per_cam[code[row[0]], row[12]] += 1
            seen += len(page)
            graded += len(rows)
            print(f"  {seen} sightings looked at, {graded} graded", flush=True)
    finally:
        await conn.close()

    print(f"\n{seen} ungraded sightings with a crop; {graded} graded; {seen - graded} skipped "
          "(crop missing from the store or unreadable)")
    print("  " + ", ".join(f"{q} {quality[q]}" for q in ("good", "marginal", "poor")))
    for cam in sorted({c for c, _ in per_cam}):
        n = sum(per_cam[cam, q] for q in ("good", "marginal", "poor"))
        print(f"  {cam:<16} {n:>6}  " + "  ".join(f"{q} {per_cam[cam, q]}" for q in ("good", "marginal", "poor")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--camera", nargs="*", help="camera codes (default: all)")
    ap.add_argument("--since", type=parse_ts, help="only sightings from this time (ISO; IST if no zone)")
    a = ap.parse_args()
    if not cq.AVAILABLE:
        print("OpenCV is not installed in this environment: nothing can be graded")
        return 1
    return asyncio.run(run([c.upper() for c in a.camera] if a.camera else None, a.since))


if __name__ == "__main__":
    raise SystemExit(main())
