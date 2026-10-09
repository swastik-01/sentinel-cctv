"""Alert latency: from the worker's first valid read of a plate to the alert existing in the API.

Both ends are wall-clock times on the same host (worker and API run on one machine here;
across machines they must share NTP). Replays from the outage spool are excluded: their
delay is the outage. Retrospective alerts have no pipeline latency and are excluded too.

    uv run --no-sync python scripts/latency_report.py --since 2026-09-24T10:00 --until 2026-09-24T10:10
Writes bench/results/latency.md.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))


def when(s: str) -> datetime:
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=IST)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="IST unless an offset is given")
    ap.add_argument("--until", required=True)
    ap.add_argument("--note", default="", help="run conditions: streams, cameras, settings")
    a = ap.parse_args()
    conn = await asyncpg.connect(get_settings().pg_dsn)
    rows = await conn.fetch(
        """SELECT (a.detail->>'latency_s')::float AS latency_s, c.camera_code, a.exact_match
           FROM alerts a JOIN cameras c ON c.id = a.camera_id
           WHERE a.triggered_at BETWEEN $1 AND $2 AND NOT a.retrospective
             AND a.detail ? 'latency_s' AND NOT coalesce((a.detail->>'replayed')::boolean, false)""",
        when(a.since), when(a.until))
    skipped = await conn.fetchval(
        """SELECT count(*) FROM alerts WHERE triggered_at BETWEEN $1 AND $2
           AND (retrospective OR NOT detail ? 'latency_s' OR coalesce((detail->>'replayed')::boolean, false))""",
        when(a.since), when(a.until))
    await conn.close()
    lat = sorted(r["latency_s"] for r in rows)
    if len(lat) < 2:
        raise SystemExit(f"only {len(lat)} alert(s) with a latency in that window; nothing to report")
    q = statistics.quantiles(lat, n=100)
    lines = [
        "# Alert latency: first valid read to alert",
        "",
        f"Window {a.since} to {a.until} (IST), measured by `scripts/latency_report.py` on {datetime.now(IST):%Y-%m-%d}.",
        f"Conditions: {a.note or 'not recorded'}",
        "",
        "| Alerts | Median s | p95 s | Max s | Cameras |",
        "|---|---|---|---|---|",
        f"| {len(lat)} | {statistics.median(lat):.2f} | {q[94]:.2f} | {lat[-1]:.2f} | {len({r['camera_code'] for r in rows})} |",
        "",
        "Measured from the worker's wall clock at the first valid read of the vehicle's track to the API's clock",
        "when the alert row exists (same host). It includes the track confirmation hold (the tracker waits up to",
        "~1 s, or 3 reads, to vote across reads), the 1 s batch flush and the API's matching. It does not include",
        "camera-to-worker transport or the browser's display of the alert.",
        f"Excluded: {skipped} alert(s) that were retrospective, replayed from the outage spool, or from before latency was recorded.",
    ]
    out = ROOT / "bench" / "results" / "latency.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
