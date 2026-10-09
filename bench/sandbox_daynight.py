"""Two runs on the organisers' sandbox: the 25 Sep evening run (data/rotation) and the 26 Sep morning run
(data/rotation-day). For each camera, minutes analysed and plate sightings stored; only sightings inside that camera's
own analysis windows count. Read-only; counts only (sightings can be real registrations). How many of the stored plates
were right, run by run: the blind checks people recorded on the Plate review page (table plate_reviews; totals in
bench/results/sandbox_review.md) and, labelled as earlier and not blind, our AI assistant's labels file.

The sandbox replays fixed recorded clips: each camera's clip is from one time of day and loops, whatever our clock
says. The two runs are therefore two samples of the same footage at different points of the loop, not day against
night. (The file keeps its old name, sandbox_daynight, because other files cite it.)

    uv run --no-sync python bench/sandbox_daynight.py [--evening-dir data/rotation] [--morning-dir data/rotation-day]
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
RUNS = (("evening", "25 Sep evening run"), ("morning", "26 Sep morning run"))


def windows(folder: Path) -> dict[str, list[tuple[datetime, datetime]]]:
    out: dict[str, list] = defaultdict(list)
    for log in sorted(folder.glob("*.csv")):
        with open(log, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                a = datetime.fromisoformat(r["start_ist"]).replace(tzinfo=IST)
                b = datetime.fromisoformat(r["end_ist"]).replace(tzinfo=IST)
                for code in r["cameras"].split(","):
                    out[code].append((a, b))
    return out


async def count(win: dict[str, list]) -> tuple[dict[str, int], dict[str, int]]:
    """Plates stored, and frames the object detector analysed (per-minute count rows): the frames show how much
    of a window the camera actually streamed, so an outage does not read as 'fewer plates'."""
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        n, fr = {}, {}
        for code, spans in win.items():
            n[code] = fr[code] = 0
            for a, b in spans:
                n[code] += await conn.fetchval(
                    """SELECT count(*) FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
                       WHERE c.camera_code = $1 AND s.event_ts >= $2 AND s.event_ts < $3""", code, a, b)
                fr[code] += int(await conn.fetchval(
                    """SELECT coalesce(sum(e.value), 0) FROM detection_events e JOIN cameras c ON c.id = e.camera_id
                       WHERE e.event_type = 'object_counts' AND c.camera_code = $1
                         AND e.event_ts >= $2 AND e.event_ts < $3""", code, a, b))
        return n, fr
    finally:
        await conn.close()


async def blind_reviews() -> list:
    """Verdicts from blind checks on the Plate review page (the reviewer saw only the crop), one row per review.
    The review keeps a copy of the sighting's time, so it still counts if the sighting has aged out. The second
    reader's reviews and sightings after v1's window are left out: sandbox-blind-v2 and sandbox-fresh-v1 are scored
    only from their frozen files (bench/sandbox_fresh.py), never pooled with v1."""
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        return await conn.fetch(
            """SELECT c.camera_code, coalesce(s.event_ts, r.sighting_ts) AS event_ts, r.verdict
               FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
               LEFT JOIN vehicle_sightings s ON s.id = r.sighting_id AND s.event_ts = r.sighting_ts
               WHERE r.mode = 'blind' AND c.camera_code ~ '^CAM[0-9]{2}$'
                 AND r.sighting_ts <= '2026-09-26 07:56:00+05:30' AND u.username <> 'auditor'""")
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evening-dir", "--night-dir", dest="evening_dir", default=str(ROOT / "data" / "rotation"))
    ap.add_argument("--morning-dir", "--day-dir", dest="morning_dir", default=str(ROOT / "data" / "rotation-day"))
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "sandbox_daynight.md"))
    a = ap.parse_args()
    ew, mw = windows(Path(a.evening_dir)), windows(Path(a.morning_dir))
    (ec, ef), (mc, mf) = asyncio.run(count(ew)), asyncio.run(count(mw))
    mins = lambda w, c: sum((b - a_).total_seconds() for a_, b in w.get(c, [])) / 60
    span = lambda w: (min(x for s in w.values() for x, _ in s), max(y for s in w.values() for _, y in s)) if w else None
    cams = sorted(mw) if mw else sorted(ew)
    rows = []
    for c in cams:
        em, mm = mins(ew, c), mins(mw, c)
        rows.append({"camera": c, "evening_min": round(em, 1), "evening_plates": ec.get(c, 0),
                     "morning_min": round(mm, 1), "morning_plates": mc.get(c, 0),
                     "evening_frames": ef.get(c, 0), "morning_frames": mf.get(c, 0),
                     "evening_per_kf": round(1000 * ec.get(c, 0) / ef[c], 1) if ef.get(c) else None,
                     "morning_per_kf": round(1000 * mc.get(c, 0) / mf[c], 1) if mf.get(c) else None,
                     "evening_per_h": round(60 * ec.get(c, 0) / em, 1) if em else None,
                     "morning_per_h": round(60 * mc.get(c, 0) / mm, 1) if mm else None})
    es, ms = span(ew), span(mw)
    L = ["# Sandbox cameras in two runs, 25 Sep evening and 26 Sep morning: plate sightings stored", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_daynight.py` (read-only). The 25 Sep "
         f"evening run: the rotation {es[0]:%d %b %H:%M}–{es[1]:%H:%M} IST ({a.evening_dir}); the 26 Sep morning run: "
         + (f"{ms[0]:%d %b %H:%M}–{ms[1]:%H:%M} IST ({a.morning_dir})" if ms else "none yet") + ". "
         "The times are our clock. The sandbox replays fixed recorded clips: each camera's picture carries its own "
         "recording date and time, from one time of day (one camera always shows the same June 2026 evening, "
         "whatever our clock says), and the footage repeats (identical readings of the same plates recurred between runs hours apart; "
         "bench/results/sandbox_loop.md). So the two runs replayed the same footage at different points of each loop: they are two samples "
         "of the same clips, not day against night, and what a camera shows (traffic, light) depends on its clip "
         "and where the loop is. A sighting is one stored plate (a vehicle's pass, voted across its reads), counted "
         "only inside that camera's analysis windows. Whether it is right: the tables at the end (blind check on the "
         "plate review page, `sandbox_review.md`). CAM05's sightings are mostly a hoarding's phone number (filtered "
         "since 21:12 on 25 Sep).", "",
         "Frames analysed are the frames the object detector ran on in those windows: they show how much of a "
         "window the camera actually streamed (an outage leaves minutes but no frames), so plates per 1,000 frames is "
         "the fairer comparison.", "",
         "| Camera | Evening: minutes | Evening: frames | Evening: plates | Evening: per 1,000 frames | "
         "Morning: minutes | Morning: frames | Morning: plates | Morning: per 1,000 frames |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        f = lambda v: "—" if v is None else v
        L.append(f"| {r['camera']} | {r['evening_min']:.0f} | {r['evening_frames']:,} | {r['evening_plates']} | "
                 f"{f(r['evening_per_kf'])} | {r['morning_min']:.0f} | {r['morning_frames']:,} | "
                 f"{r['morning_plates']} | {f(r['morning_per_kf'])} |")
    te = sum(r["evening_plates"] for r in rows)
    tm = sum(r["morning_plates"] for r in rows)
    L += ["", f"Same cameras, totals: 25 Sep evening run {te} plates in {sum(r['evening_frames'] for r in rows):,} "
              f"frames ({sum(r['evening_min'] for r in rows):.0f} camera-minutes); 26 Sep morning run {tm} plates in "
              f"{sum(r['morning_frames'] for r in rows):,} frames ({sum(r['morning_min'] for r in rows):.0f} "
              "camera-minutes). Both runs replayed the same looping footage, so a difference between them is where "
              "each camera's loop was, not the time of day."]
    # How many stored plates were right, run by run. Two sources, never pooled: blind checks by a person on the
    # Plate review page (the headline), and the earlier labels file from our AI assistant, which saw the stored read
    # (not blind). Both hold real registrations and stay put; only counts leave them.
    def side(code, t_):
        if any(x <= t_ < y for x, y in ew.get(code, [])):
            return "evening"
        if any(x <= t_ < y for x, y in mw.get(code, [])):
            return "morning"
        return None

    def table(acc):
        out = ["| Run | Plates judged | Exact | Within one character | Wrong | Unreadable (left out) | Not a plate |",
               "|---|---|---|---|---|---|---|"]
        for s, label in RUNS:
            v = acc[s]
            judged = v["exact"] + v["one_off"] + v["wrong"]
            share = lambda n: f"{n} ({100 * n / judged:.1f}%)" if judged else "—"  # noqa: E731
            out.append(f"| {label} | {judged} | {share(v['exact'])} | {share(v['exact'] + v['one_off'])} | "
                       f"{v['wrong']} | {v['unreadable']} | {v['not_a_plate']} |")
        return out

    blind = {s: defaultdict(int) for s, _ in RUNS}
    outside = 0
    for r in asyncio.run(blind_reviews()):
        s = side(r["camera_code"], r["event_ts"])
        if s:
            blind[s][r["verdict"]] += 1
        else:
            outside += 1
    if any(blind[s] for s in blind):
        L += ["", "**Were they right? Blind check by a person** on the Plate review page: the reviewer saw only the "
                  "crop, typed the plate, and the server compared that reading with the stored read "
                  "(`sandbox_review.md`):", ""] + table(blind)
        if outside:
            L += ["", f"{outside} blind review(s) fall outside both runs' windows and are left out of this table."]
    labels = ROOT / "data" / "gov-sandbox" / "eye" / "labels.csv"
    acc = {}
    if labels.exists():
        acc = {s: defaultdict(int) for s, _ in RUNS}
        with open(labels, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                s = side(r["camera"], datetime.fromisoformat(r["event_ist"]).replace(tzinfo=IST))
                if s and r["verdict"]:
                    acc[s][r["verdict"]] += 1
        L += ["", "Earlier, not blind: each stored plate checked against its own crop by our AI coding assistant, "
                  "with the stored read in view (`sandbox_eye.md`). It left unreadable crops out"
                  + (" and came out more optimistic than the blind check above" if any(blind.values()) else "")
                  + ":", ""] + table(acc)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(
        {"runs": {s: label for s, label in RUNS},
         "note": "Both runs replayed the same looping sandbox footage: two samples of the same clips, not day and night.",
         "cameras": rows, "blind": {k: dict(v) for k, v in blind.items()},
         "accuracy": {k: dict(v) for k, v in acc.items()}}, indent=1), encoding="utf-8")
    print("\n".join(L[5:]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
