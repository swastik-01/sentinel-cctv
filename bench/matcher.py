"""Watchlist matching cost per plate read, at a statewide-sized watchlist.

Runs the API's own matcher (routers/ingest.py `_match`) against the live database inside
a transaction that is rolled back: N synthetic entries are inserted (the mask trigger
fills watchlist_masks as in production), probes are timed, nothing is kept.

    uv run --no-sync python bench/matcher.py --entries 100000
Writes bench/results/matcher.md.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

from sentinel_api.config import get_settings
from sentinel_api.routers.ingest import _match

ROOT = Path(__file__).resolve().parents[1]
OLD = """SELECT id FROM watchlist_entries
         WHERE active AND plate_norm IS NOT NULL
           AND (plate_norm = $1 OR (length(plate_norm) = length($1) AND levenshtein(plate_norm, $1) <= 1))
           AND (valid_until IS NULL OR valid_until > now())
         ORDER BY (plate_norm = $1) DESC LIMIT 1"""


def synthetic(i: int) -> str:
    return (f"GJ{1 + i % 38:02d}{chr(65 + (i * 7) % 26)}{chr(65 + (i * 13) % 26)}"
            f"{(i * 7919) % 10000:04d}")


async def timed(fn, probes) -> tuple[list[float], int]:
    ms, hits = [], 0
    for p in probes:
        t0 = time.perf_counter()
        hits += (await fn(p)) is not None
        ms.append((time.perf_counter() - t0) * 1000)
    return ms, hits


def row(name, ms, hits, n):
    q = statistics.quantiles(ms, n=100)
    return f"| {name} | {n} | {hits} | {statistics.median(ms):.2f} | {q[94]:.2f} |"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", type=int, default=100_000)
    ap.add_argument("--probes", type=int, default=1000)
    a = ap.parse_args()
    s = get_settings()
    conn = await asyncpg.connect(s.pg_dsn)
    tr = conn.transaction()
    await tr.start()
    try:
        t0 = time.perf_counter()
        await conn.execute(
            """INSERT INTO watchlist_entries (kind, plate_norm, severity, source, reason)
               SELECT 'stolen_vehicle', p, 'high', 'bench', 'matcher benchmark (rolled back)'
               FROM unnest($1::text[]) AS p""", [synthetic(i) for i in range(a.entries)])
        load_s = time.perf_counter() - t0
        await conn.execute("ANALYZE watchlist_entries; ANALYZE watchlist_masks")
        total = await conn.fetchval("SELECT count(*) FROM watchlist_entries WHERE active")

        step = max(1, a.entries // a.probes)
        near = [synthetic(i)[:6] + "X" + synthetic(i)[7:] for i in range(0, a.entries, step)][: a.probes]
        miss = [f"MH12QQ{i:04d}" for i in range(a.probes)]          # not on the list: the common case
        new = lambda p: _match(conn, p, 1)                             # noqa: E731
        old = lambda p: conn.fetchrow(OLD, p)                          # noqa: E731
        await timed(new, near[:20]); await timed(old, near[:5])        # warm caches
        r = [("masks (current), one character off", *await timed(new, near), len(near)),
             ("masks (current), plate not listed", *await timed(new, miss), len(miss)),
             ("levenshtein scan (before), one character off", *await timed(old, near[:100]), 100),
             ("levenshtein scan (before), plate not listed", *await timed(old, miss[:100]), 100)]
    finally:
        await tr.rollback()
        await conn.close()

    out = ROOT / "bench" / "results" / "matcher.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Watchlist matching cost per plate read",
        "",
        f"Measured {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')} on {platform.node()} "
        f"({platform.processor() or platform.machine()}), PostgreSQL in Docker Desktop, by `bench/matcher.py`.",
        f"Watchlist: {total:,} active entries ({a.entries:,} synthetic, inserted in {load_s:.1f} s with the mask "
        "trigger, then rolled back). Times are one query per plate read, round trip from Python, single connection.",
        "",
        "| Matcher | Probes | Matched | Median ms | p95 ms |",
        "|---|---|---|---|---|",
        *(row(*x) for x in r),
        "",
        "One character off = a real watchlist plate with one character replaced, i.e. a single OCR slip.",
        "Every one of them must match; a plate not on the list must not.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    asyncio.run(main())
