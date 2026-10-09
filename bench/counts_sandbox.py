"""The counts-only worker on the organisers' sandbox cameras: how far apart each camera's keyframes are, and how many
frames each camera was counted on in a counts-worker run.

`probe` reads the cameras keyframes-only through the local relay (one session each, at once) for a while and times the
keyframes. `report` summarises the `object_counts` rows a counts-worker run stored (frames per minute and the profile:
keyframes, or every frame for a camera whose keyframes were too far apart) and writes both into one results file.
Read-only towards the database; counts only.

    uv run --no-sync python bench/counts_sandbox.py probe --cams CAM01,CAM02 --seconds 60
    uv run --no-sync python bench/counts_sandbox.py report --since 2026-10-07T21:13 --until 2026-10-07T21:17
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import av

from sentinel_analytics.counts import LONG_GOP_S
from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
PROBE = ROOT / "bench" / "results" / "counts_sandbox_probe.json"
OUT = ROOT / "bench" / "results" / "counts_sandbox.md"


def probe_one(code: str, seconds: float, out: dict) -> None:
    """Keyframes-only sessions for `seconds` in all, reconnecting after each drop (the sandbox drops sessions every
    15-60 s); keyframe gaps are measured within a session only."""
    gaps: list[float] = []
    sessions = drops = keyframes = 0
    opens: list[float] = []
    codec = size = None
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        t_open = time.monotonic()
        try:
            c = av.open(f"rtsp://localhost:8554/{code}", options={"rtsp_transport": "tcp"}, timeout=(15.0, 15.0))
        except Exception:  # noqa: BLE001
            drops += 1
            time.sleep(3)
            continue
        sessions += 1
        s = c.streams.video[0]
        s.codec_context.skip_frame = "NONKEY"
        codec, size = s.codec_context.name, f"{s.codec_context.width}x{s.codec_context.height}"
        opens.append(time.monotonic() - t_open)
        last = None
        try:
            for _ in c.decode(s):
                now = time.monotonic()
                keyframes += 1
                if last is not None:
                    gaps.append(now - last)
                last = now
                if now >= t_end:
                    break
            else:
                drops += 1
        except Exception:  # noqa: BLE001
            drops += 1
        finally:
            c.close()
        time.sleep(2)
    out[code] = {"codec": codec, "size": size, "sessions": sessions, "drops": drops, "keyframes": keyframes,
                 "open_s_median": round(statistics.median(opens), 1) if opens else None,
                 "interval_median_s": round(statistics.median(gaps), 2) if gaps else None,
                 "interval_max_s": round(max(gaps), 1) if gaps else None, "gaps": len(gaps)}


def probe(a) -> None:
    out: dict = {}
    threads = [threading.Thread(target=probe_one, args=(c, a.seconds, out)) for c in a.cams.split(",")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(a.seconds + 60)
    PROBE.write_text(json.dumps({"generated": datetime.now(IST).isoformat(timespec="minutes"), "seconds": a.seconds,
                                 "cameras": out}, indent=2), encoding="utf-8")
    for code, r in out.items():
        print(code, r)


async def rows(since: datetime, until: datetime) -> list:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        return await conn.fetch(
            """SELECT c.camera_code, count(*) AS windows, sum(e.value)::int AS frames,
                      sum((e.detail->>'window_s')::float) AS seconds,
                      string_agg(DISTINCT e.detail->>'profile', ', ') AS profiles
               FROM detection_events e JOIN cameras c ON c.id = e.camera_id
               WHERE e.event_type = 'object_counts' AND e.detail ? 'profile' AND e.event_ts >= $1 AND e.event_ts < $2
               GROUP BY 1 ORDER BY 1""", since, until)
    finally:
        await conn.close()


def report(a) -> None:
    since = datetime.fromisoformat(a.since).replace(tzinfo=IST)
    until = datetime.fromisoformat(a.until).replace(tzinfo=IST)
    pr = json.loads(PROBE.read_text(encoding="utf-8")) if PROBE.exists() else {"cameras": {}}
    rs = asyncio.run(rows(since, until))
    now = datetime.now(IST)
    L = ["# Counts-only worker on the sandbox cameras", "",
         f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/counts_sandbox.py`. The organisers' sandbox cameras, read through "
         "the local relay from one laptop on its home internet connection. Counts only.", "",
         f"## Keyframe intervals (probe of {pr.get('generated', '?')}, {pr.get('seconds', '?')} s, all cameras at once)",
         "", "Each camera is read in sessions that reconnect after a drop; gaps are timed within a session.", "",
         "| Camera | Codec | Size | Keyframes (gaps) | Interval median (s) | Max (s) | Sessions / drops | Profile it gets |",
         "|---|---|---|---:|---:|---:|---|---|"]
    for code, r in sorted(pr["cameras"].items()):
        med = r["interval_median_s"]
        prof = "every frame" if med and med > LONG_GOP_S else ("keyframes" if med else "too few keyframes to tell")
        L.append(f"| {code} | {r['codec']} | {r['size']} | {r['keyframes']} ({r['gaps']} gaps) | {med} | "
                 f"{r['interval_max_s']} | {r['sessions']} / {r['drops']} | {prof} |")
    L += ["", f"A camera whose keyframes are more than {LONG_GOP_S:g} s apart is switched to decoding every frame "
          "(still counted at most about once a second), or it would be counted every 10-40 s and its zones would miss "
          "short presences.", "",
          f"## Frames counted per camera ({since:%d %b %H:%M}–{until:%H:%M} IST)", "",
          "| Camera | Windows | Frames | Frames per minute | Profile |", "|---|---:|---:|---:|---|"]
    for r in rs:
        fpm = r["frames"] / (r["seconds"] / 60) if r["seconds"] else 0
        L.append(f"| {r['camera_code']} | {r['windows']} | {r['frames']} | {fpm:.0f} | {r['profiles']} |")
    if a.note:
        L += ["", a.note]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--cams", required=True)
    p.add_argument("--seconds", type=float, default=60)
    r = sub.add_parser("report")
    r.add_argument("--since", required=True)
    r.add_argument("--until", required=True)
    r.add_argument("--note", default="")
    a = ap.parse_args()
    probe(a) if a.cmd == "probe" else report(a)


if __name__ == "__main__":
    main()
