"""Does the sandbox footage repeat, and can its loop length be read from our runs? An exact repeat of a stored reading on
one camera, well apart in time, means the same vehicle passed again. But a repeat can only be seen between two of our
analysis windows, so the gaps are bounded by the windows' own spacing: when two windows start 97 minutes apart, every
repeat between them lies near 97 minutes whatever the clip's length. The report groups the repeats by the pair of
windows they span and shows the range of gaps each pair allows next to the gaps seen. It also counts how many of the
fresh sightings (sandbox-fresh-v1) repeat a reading from the window sandbox-blind-v1 was drawn from. Read-only; counts
only (the readings can be real registrations and are never printed).

    uv run --no-sync python bench/sandbox_loop.py [--cams CAM06,CAM07] [--since 2026-09-25T20:00]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
MIN_GAP = 3.0       # minutes; closer repeats are one pass stored twice
LOGS = ("data/rotation", "data/rotation-day", "data/rotation-capture", "data/rotation-all")


def windows(cams: list[str]) -> dict[str, list[tuple[datetime, datetime]]]:
    out: dict[str, list] = defaultdict(list)
    for d in LOGS:
        for log in sorted((ROOT / d).glob("*.csv")):
            with open(log, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    a = datetime.fromisoformat(r["start_ist"]).replace(tzinfo=IST)
                    b = datetime.fromisoformat(r["end_ist"]).replace(tzinfo=IST)
                    for code in r["cameras"].split(","):
                        if code in cams and b > a:
                            out[code].append((a, b))
    return {k: sorted(v) for k, v in out.items()}


async def repeats(cams: list[str], since: datetime) -> dict[str, list[tuple[datetime, datetime]]]:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        rows = await conn.fetch(
            """SELECT c.camera_code, s.plate_norm, s.event_ts FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
               WHERE c.camera_code = ANY($1) AND s.event_ts >= $2 ORDER BY s.event_ts""", cams, since)
    finally:
        await conn.close()
    last: dict[tuple[str, str], datetime] = {}
    out: dict[str, list] = defaultdict(list)
    for code, plate, ts in rows:
        prev = last.get((code, plate))
        if prev is not None and (ts - prev).total_seconds() / 60 >= MIN_GAP:
            out[code].append((prev, ts))
        last[(code, plate)] = ts
    return out


async def overlap(cams: list[str], v1: tuple[datetime, datetime], fresh: datetime) -> tuple[int, int, int]:
    """Fresh sightings, how many repeat a reading stored in the v1 window, and distinct fresh readings."""
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        row = await conn.fetchrow(
            """WITH v1 AS (SELECT DISTINCT s.plate_norm FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
                           WHERE c.camera_code = ANY($1) AND s.event_ts >= $2 AND s.event_ts < $3),
                    fr AS (SELECT s.plate_norm FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
                           WHERE c.camera_code = ANY($1) AND s.event_ts >= $4)
               SELECT count(*), count(*) FILTER (WHERE plate_norm IN (SELECT plate_norm FROM v1)),
                      count(DISTINCT plate_norm) FROM fr""", cams, v1[0], v1[1], fresh)
    finally:
        await conn.close()
    return row[0], row[1], row[2]


def which(ts: datetime, spans: list[tuple[datetime, datetime]]) -> int | None:
    for i, (a, b) in enumerate(spans):
        if a - timedelta(minutes=1) <= ts <= b + timedelta(minutes=1):
            return i
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cams", default="CAM06,CAM07")
    ap.add_argument("--since", default="2026-09-25T20:00")
    ap.add_argument("--v1", default="2026-09-25T21:00,2026-09-26T07:55:28",
                    help="window of the sightings sandbox-blind-v1 was drawn from")
    ap.add_argument("--fresh-since", default="2026-09-26T07:55:28",
                    help="start of sandbox-fresh-v1: v1's last sighting is at 07:55:27.55 and stays v1's")
    ap.add_argument("--out", default=str(ROOT / "bench/results/sandbox_loop.md"))
    a = ap.parse_args()
    cams = a.cams.split(",")
    since = datetime.fromisoformat(a.since).replace(tzinfo=IST)
    v1 = tuple(datetime.fromisoformat(t).replace(tzinfo=IST) for t in a.v1.split(","))
    fresh = datetime.fromisoformat(a.fresh_since).replace(tzinfo=IST)
    win = windows(cams)
    rep = asyncio.run(repeats(cams, since))
    n_fresh, n_same, n_distinct = asyncio.run(overlap(cams, v1, fresh))
    now = datetime.now(IST)
    lines = [
        "# Does the sandbox footage repeat?",
        "",
        f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/sandbox_loop.py` (read-only; counts only). Sightings on "
        f"{', '.join(cams)} stored from {since:%d %b %H:%M} IST; analysis windows from the rotation logs "
        f"({', '.join(LOGS)}; a window still running has no end row yet and is left out). A repeat is the same stored "
        f"reading on the same camera at least {MIN_GAP:.0f} minutes after the last one. Misreads differ from pass to "
        "pass, so only repeats read identically both times are counted.",
        "",
        "| Camera | Windows | From window | To window | Gaps this pair allows (min) | Repeats | Gaps seen (min) |",
        "|---|---:|---|---|---|---:|---|",
    ]
    result: dict[str, list] = {}
    for code in cams:
        spans = win.get(code, [])
        pairs: dict[tuple, list[float]] = defaultdict(list)
        for p, q in rep.get(code, []):
            pairs[(which(p, spans), which(q, spans))].append((q - p).total_seconds() / 60)
        result[code] = []
        for (i, j), gs in sorted(pairs.items(), key=lambda kv: tuple(99 if k is None else k for k in kv[0])):
            fmt = lambda k: f"{spans[k][0]:%d %b %H:%M}–{spans[k][1]:%H:%M}" if k is not None else "outside the logs"
            if i is not None and j is not None:
                lo = max(0.0, (spans[j][0] - spans[i][1]).total_seconds() / 60)
                hi = (spans[j][1] - spans[i][0]).total_seconds() / 60
                allow = f"{lo:.0f} to {hi:.0f}"
            else:
                allow = "n/a"
            seen = ", ".join(f"{g:.0f}" for g in sorted(gs))
            lines.append(f"| {code} | {len(spans)} | {fmt(i)} | {fmt(j)} | {allow} | {len(gs)} | {seen} |")
            result[code].append({"from": fmt(i), "to": fmt(j), "allowed": allow, "gaps_min": sorted(round(g, 1) for g in gs)})
    lines += [
        "",
        "Reading it: identical readings of the same plate recurring between windows hours apart show that the footage "
        "repeats. The gap itself is bounded by the window pair; a loop length is only identifiable where gaps cluster "
        "much more tightly than the pair allows, or where one continuous window is longer than the loop.",
        "",
        "## The fresh sightings and the first blind set",
        "",
        f"Sightings on {', '.join(cams)} stored from {fresh:%d %b %H:%M:%S} IST (sandbox-fresh-v1's window, to the time "
        f"above): {n_fresh}, with {n_distinct} distinct readings. {n_same} of them ({100 * n_same / max(n_fresh, 1):.0f}%) "
        f"repeat exactly a reading stored in {v1[0]:%d %b %H:%M}–{v1[1]:%d %b %H:%M:%S} IST, the window sandbox-blind-v1 "
        "was drawn from. That is a lower bound on re-read vehicles, since a misread differs from pass to pass: the fresh "
        "set re-reads the same looping footage and is not an independent sample of vehicles.",
    ]
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(
        {"generated": now.isoformat(timespec="minutes"), "since": since.isoformat(), "cams": result,
         "fresh": {"since": fresh.isoformat(), "sightings": n_fresh, "repeat_v1_reading": n_same,
                   "distinct_readings": n_distinct}}, indent=2),
        encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
