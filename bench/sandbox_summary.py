"""What Sentinel did with the organisers' sandbox cameras (CAM01..CAM30), from the database and the rotation log.
Read-only. Writes bench/results/sandbox.md: onboarding (probe time, codec, resolution, placement), per camera the
minutes analysed, frames analysed for objects, vehicles and people in view (average and peak), plate reads and
intrusion alerts.

    uv run --no-sync python bench/sandbox_summary.py [--rotation-dir data/rotation]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
VEHICLES = ("car", "motorcycle", "bus", "truck", "bicycle")


async def fetch():
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        cams = await conn.fetch(
            """SELECT c.camera_code, c.name, d.code AS dept, di.name AS district, c.codec, c.resolution,
                      c.location IS NOT NULL AS placed, c.health::text AS health, c.address
               FROM cameras c JOIN departments d ON d.id = c.department_id LEFT JOIN districts di ON di.id = c.district_id
               WHERE c.camera_code ~ '^CAM[0-9]{2}$' ORDER BY c.camera_code""")
        onboard = await conn.fetch(
            """SELECT object_id, action, (detail->>'seconds')::float AS seconds, at FROM audit_log
               WHERE action LIKE 'camera.onboarded_%' AND object_id ~ '^CAM[0-9]{2}$' ORDER BY at""")
        counts = await conn.fetch(
            """SELECT c.camera_code, e.value AS frames, e.detail FROM detection_events e JOIN cameras c ON c.id = e.camera_id
               WHERE e.event_type = 'object_counts' AND c.camera_code ~ '^CAM[0-9]{2}$'""")
        sightings = await conn.fetch(
            """SELECT c.camera_code, count(*) AS n, count(DISTINCT s.plate_norm) AS plates FROM vehicle_sightings s
               JOIN cameras c ON c.id = s.camera_id WHERE c.camera_code ~ '^CAM[0-9]{2}$' GROUP BY 1""")
        intrusions = await conn.fetch(
            """SELECT c.camera_code, count(*) AS n FROM alerts a JOIN cameras c ON c.id = a.camera_id
               WHERE a.alert_type = 'intrusion' AND c.camera_code ~ '^CAM[0-9]{2}$' GROUP BY 1""")
        return cams, onboard, counts, sightings, intrusions
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotation-dir", default=str(ROOT / "data" / "rotation"), help="every *.csv run log in it is read")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "sandbox.md"))
    a = ap.parse_args()
    cams, onboard, counts, sightings, intrusions = asyncio.run(fetch())

    minutes: dict[str, float] = defaultdict(float)
    runs = []
    for log in sorted(Path(a.rotation_dir).glob("*.csv")):
        with open(log, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                runs.append(r)
                for code in r["cameras"].split(","):
                    minutes[code] += float(r["minutes"])
    runs.sort(key=lambda r: r["start_ist"])

    frames: dict[str, int] = defaultdict(int)
    boxes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    peak: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in counts:
        d = r["detail"] if isinstance(r["detail"], dict) else json.loads(r["detail"])
        frames[r["camera_code"]] += int(r["frames"] or 0)
        for k, v in (d.get("detections") or {}).items():
            boxes[r["camera_code"]][k] += int(v)
        pv = int(d.get("peak_vehicles") or 0)
        peak[r["camera_code"]]["vehicles"] = max(peak[r["camera_code"]]["vehicles"], pv)
        peak[r["camera_code"]]["person"] = max(peak[r["camera_code"]]["person"], int((d.get("peak") or {}).get("person", 0)))
    reads = {r["camera_code"]: (r["n"], r["plates"]) for r in sightings}
    intr = {r["camera_code"]: r["n"] for r in intrusions}
    secs = [r["seconds"] for r in onboard if r["seconds"] is not None]
    first = {}
    for r in onboard:
        first.setdefault(r["object_id"], r)

    now = datetime.now(IST)
    L = [f"# Sandbox cameras: onboarding and analytics on the organisers' feeds", "",
         f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/sandbox_summary.py` (read-only database access).",
         "Source: the organisers' sandbox camera grid (<sandbox-grid>): 30 cameras, recorded footage replayed as live "
         "streams on a common timeline, looping. Onboarded over RTSP (TCP) with the team's credentials by "
         "`scripts/onboard_sandbox.py`; relayed on demand by MediaMTX; analysed on the GTX 1650 Ti laptop, 4 cameras at "
         "a time, by `scripts/rotate_worker.py`.", "",
         "The sandbox catalogue (`cameras.json`) gives only an id and a name per camera. Department, district and position "
         "are our reading of the names and of the pictures (`data/gov-sandbox/locations.json`), approximate, and recorded in "
         "each camera's address field; a camera we could not place has no position. Nothing here is the organisers' data "
         "beyond the id, the name and the streams.", ""]
    if secs:
        L += [f"**Onboarding.** {len(first)} cameras onboarded by stream URL; probe time per camera "
              f"{min(secs):.1f}–{max(secs):.1f} s, median {statistics.median(secs):.1f} s (first onboarding "
              f"{min(r['at'] for r in onboard).astimezone(IST):%Y-%m-%d %H:%M} IST). "
              f"Codecs: {', '.join(sorted({c['codec'] for c in cams if c['codec']}))}; resolutions "
              f"{', '.join(sorted({c['resolution'] for c in cams if c['resolution']}, key=lambda s: int(s.split('x')[0])))}. "
              f"Placed on the map: {sum(1 for c in cams if c['placed'])} of {len(cams)}.", ""]
    if runs:
        L += [f"**Analysis.** {len(runs)} rotation runs from {runs[0]['start_ist']} to {runs[-1]['end_ist']} IST "
              f"(run logs in `data/rotation/`); each camera's minutes below.", ""]
    L += ["| Camera | Name | Dept (ours) | Codec, resolution | Placed | Minutes analysed | Frames analysed (objects) | "
          "Vehicles avg / peak in view | People avg / peak | Plate reads (distinct) | Intrusion alerts |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in cams:
        k = c["camera_code"]
        fr = frames.get(k, 0)
        veh = sum(boxes[k].get(v, 0) for v in VEHICLES)
        ppl = boxes[k].get("person", 0)
        avg_v = f"{veh / fr:.1f} / {peak[k]['vehicles']}" if fr else "—"
        avg_p = f"{ppl / fr:.1f} / {peak[k]['person']}" if fr else "—"
        n, p = reads.get(k, (0, 0))
        L.append(f"| {k} | {c['name']} | {c['dept']} | {c['codec']} {c['resolution']} | {'yes' if c['placed'] else 'no'} | "
                 f"{minutes.get(k, 0):.0f} | {fr:,} | {avg_v} | {avg_p} | {n} ({p}) | {intr.get(k, 0)} |")
    tot_frames = sum(frames.values())
    tot_reads = sum(n for n, _ in reads.values())
    L += ["", f"Totals: {tot_frames:,} frames analysed for objects; {tot_reads} plate reads on "
              f"{len(reads)} camera(s); {sum(intr.values())} intrusion alerts on {len(intr)} camera(s).", "",
          "Definitions: a frame analysed is one frame the object detector ran on (per-minute count rows). Average in view "
          "is detections per analysed frame; peak is the most in any single frame. A plate read is one stored sighting "
          "(a vehicle's pass, voted across its reads). Intrusion alerts come from two demo zones we drew (CAM17 walkway, "
          "CAM18 junction corner: simulated restricted areas), at most one per zone per 120 s."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps({
        "cameras": len(cams), "placed": sum(1 for c in cams if c["placed"]),
        "probe_s": [min(secs), statistics.median(secs), max(secs)] if secs else None,
        "codecs": sorted({c["codec"] for c in cams if c["codec"]}),
        "runs": len(runs), "first_run_ist": runs[0]["start_ist"] if runs else None,
        "last_run_ist": runs[-1]["end_ist"] if runs else None,
        "cameras_analysed": sum(1 for c in cams if frames.get(c["camera_code"])),
        "frames": tot_frames, "plate_reads": tot_reads, "cameras_with_reads": len(reads),
        "intrusion_alerts": sum(intr.values()), "cameras_with_intrusions": len(intr)}, indent=1), encoding="utf-8")
    print("\n".join(L[-4:]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
