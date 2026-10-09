"""ANPR accuracy against the simulator's ground truth: precision and capture rate per camera.

Two kinds of simulated camera carry ground truth:
  - stock footage (AMD-TRAF-001/002): realclip.py painted a synthetic Gujarat registration over
    every plate it found and logged each one, with how many frames it was painted, in
    feedsim/media/<CODE>.plates.json
  - synthetic clips: synth.py draws exactly the `plates` listed in feedsim/cameras.yaml, and
    every one of them crosses the view in every loop

Compares them with the sightings the worker stored in a time window. Database access is one
read-only transaction; the only thing written is the markdown report.

    uv run --no-sync python scripts/anpr_eval.py                       # last 24 h
    uv run --no-sync python scripts/anpr_eval.py --since 2026-09-23T11:30 --until 2026-09-23T17:30
    uv run --no-sync python scripts/anpr_eval.py --camera AMD-TRAF-002 --note "2 streams, DETECT_FPS=5"

Writes bench/results/anpr_eval.md (or --out).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import yaml

from sentinel_api.config import get_settings
from sentinel_common import normalise_plate

ROOT = Path(__file__).resolve().parents[1]
FEEDSIM = ROOT / "feedsim"
MEDIA = FEEDSIM / "media"
IST = timezone(timedelta(hours=5, minutes=30))
STOCK, SYNTH = "stock footage, painted plates", "synthetic (drawn)"
VISIBLE_S = 1.0                     # realclip.py's own "visible for 1 s or more"
BANDS = [(0.0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 5.0), (5.0, None)]   # seconds painted on screen
CONF_BANDS = [0.0, 0.5, 0.7, 0.9]

SQL = """SELECT c.camera_code, s.plate_norm, s.ocr_conf, s.event_ts, s.track_id, s.bbox
         FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
         WHERE s.event_ts >= $1 AND s.event_ts < $2 AND c.camera_code = ANY($3::text[])
         ORDER BY s.event_ts"""


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def one_substitution(a: str, b: str) -> bool:
    """Same length, at most one character different: the watchlist's fuzzy rule (FUZZY_MAX_EDITS=1)."""
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 1


def edits(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def drawn_plate_px(scene: str, plate: str) -> int:
    """Plate width synth.py draws for this scene, from its own sizing rule."""
    if str(FEEDSIM) not in sys.path:
        sys.path.insert(0, str(FEEDSIM))
    from synth import SCENE, plate_box
    return plate_box(SCENE[scene][0], len(plate))[0]


def load_truth(cam: dict) -> dict | None:
    """Ground-truth plates of one camera -> seconds painted on screen (None: drawn on every pass)."""
    code = cam["code"]
    out_w = int(cam["resolution"].lower().split("x")[0])
    if cam.get("real"):
        f = MEDIA / f"{code}.plates.json"
        if not f.exists():
            return None
        d = json.loads(f.read_text(encoding="utf-8"))
        shown: dict[str, float] = {}
        for p in d["plates"]:
            norm = normalise_plate(p["plate"])
            shown[norm] = shown.get(norm, 0.0) + p["frames_painted"] / d["fps"]
        crop = cam["real"].get("crop")
        view = f"{crop[2]}x{crop[3]} of the source scaled {out_w / crop[2]:.2f}x" if crop else "full source frame"
        return {"kind": STOCK, "plates": shown, "file": f, "view": view,
                "loop_s": float(cam["real"].get("seconds", 60))}
    if cam.get("plates"):
        scene = cam.get("scene", "mid")
        return {"kind": SYNTH, "plates": {normalise_plate(p): None for p in cam["plates"]},
                "file": MEDIA / f"{code}.mp4", "loop_s": 60.0,        # synth.py CLIP_SECONDS default
                "view": f"scene {scene}, plate drawn ~{drawn_plate_px(scene, cam['plates'][0])} px wide"}
    return None


async def fetch(since: datetime, until: datetime, codes: list[str]) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        async with conn.transaction(readonly=True):
            return await conn.fetch(SQL, since, until, codes)
    finally:
        await conn.close()


def evaluate(code: str, truth: dict, rows: list) -> dict:
    # The worker's track ids are "<camera>-<plate>-<unix time>"; anything else was injected (smoke uses "smoke").
    worker = [r for r in rows if (r["track_id"] or "").startswith(code + "-")]
    gt = truth["plates"]
    visible = {p for p, s in gt.items() if s is None or s >= VISIBLE_S}
    exact = [r for r in worker if r["plate_norm"] in gt]
    near = [r for r in worker if any(one_substitution(r["plate_norm"], g) for g in gt)]
    read = {r["plate_norm"] for r in exact}
    wrong = Counter(r["plate_norm"] for r in worker if r["plate_norm"] not in gt)
    m = {"n": len(worker), "injected": len(rows) - len(worker), "exact": len(exact), "near": len(near),
         "distinct_read": len({r["plate_norm"] for r in worker}), "distinct_wrong": len(wrong),
         "gt": len(gt), "visible": len(visible), "captured": len(read), "captured_visible": len(read & visible),
         "minutes": len({r["event_ts"].replace(second=0, microsecond=0) for r in worker}),
         "plate_px": statistics.median(r["bbox"][2] for r in worker) if worker else None,
         "first": min((r["event_ts"] for r in worker), default=None),
         "last": max((r["event_ts"] for r in worker), default=None)}
    m["bands"] = []
    if all(s is not None for s in gt.values()):
        for lo, hi in BANDS:
            inband = {p for p, s in gt.items() if s >= lo and (hi is None or s < hi)}
            m["bands"].append((lo, hi, len(inband), len(inband & read)))
    m["conf"] = []
    # ocr_conf is REAL: a track stored at exactly 0.9 (three agreeing reads) comes back as 0.8999999761 and would
    # drop a band, as it did in the 24 Sep files. Rounded as the review page bands it (reviews.py).
    conf = [round(r["ocr_conf"] or 0.0, 3) for r in worker]
    for i, lo in enumerate(CONF_BANDS):
        hi = CONF_BANDS[i + 1] if i + 1 < len(CONF_BANDS) else None
        band = [r for r, c in zip(worker, conf) if c >= lo and (hi is None or c < hi)]
        m["conf"].append((lo, hi, len(band), sum(r["plate_norm"] in gt for r in band)))
    m["wrong"] = [(p, k, *min((edits(p, g), g) for g in gt)) for p, k in wrong.most_common(5)]
    made = datetime.fromtimestamp(truth["file"].stat().st_mtime, timezone.utc) if truth["file"].exists() else None
    m["stale"] = made is not None and m["first"] is not None and made > m["first"]
    return m


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}% ({a}/{b})" if b else "n/a"


def band_label(lo: float, hi: float | None, unit: str = "") -> str:
    return f">= {lo:g}{unit}" if hi is None else f"{lo:g}-{hi:g}{unit}"


def pooled(kind: str, cams: list[dict], results: dict) -> str | None:
    ms = [m for c in cams for t, m in [results[c["code"]]] if t["kind"] == kind and m["n"]]
    if len(ms) < 2:
        return None
    s = {k: sum(m[k] for m in ms) for k in ("n", "exact", "near", "captured_visible", "visible", "captured", "gt")}
    return (f"| **All {len(ms)} {kind.split(',')[0].split(' (')[0]} cameras, pooled** | | | | | {s['n']} | "
            f"{pct(s['exact'], s['n'])} | {pct(s['near'], s['n'])} | {pct(s['captured_visible'], s['visible'])} | "
            f"{pct(s['captured'], s['gt'])} | | |")


def report(cams: list[dict], results: dict, since: datetime, until: datetime, notes: list[str],
           only: list[str] | None) -> str:
    args = (f"--since {since.astimezone(IST).isoformat(timespec='seconds')} "
            f"--until {until.astimezone(IST).isoformat(timespec='seconds')}"
            + "".join(f" --camera {c}" for c in only or []))
    L = [
        "# ANPR accuracy against simulator ground truth",
        "",
        f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `scripts/anpr_eval.py` (read-only database access).",
        f"Window: {since.astimezone(IST):%Y-%m-%d %H:%M} to {until.astimezone(IST):%Y-%m-%d %H:%M} IST, "
        "sightings by frame time.",
        f"Reproduce: `uv run --no-sync python scripts/anpr_eval.py {args}` (while those sightings are kept: "
        "`demo_prep.py` without `--keep-sightings` deletes them).",
        *(f"Conditions: {n}" for n in notes),
        "",
        "**These plates are synthetic registrations, not real Gujarat plates.** On the two stock-footage "
        "cameras the vehicles and scenes are real (Pexels stock footage, not Gujarat CCTV; the Ahmedabad "
        "locations are simulated) but every "
        "plate the painter found carries a synthetic registration in a clean font on a white plate; the "
        "other cameras show drawn rectangles. Precision on real plates is unmeasured.",
        "",
        "| Camera | Footage | Class, view | anpr_viable | Stream | Sightings | Precision (exact) "
        f"| Within one character | Capture rate, plates shown >= {VISIBLE_S:g} s | Capture rate, every plate "
        "| Median plate box width (px) | Active minutes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    missing = []
    for cam in cams:
        t, m = results[cam["code"]]
        if not m["n"]:
            missing.append(cam["code"])
            continue
        shown = pct(m["captured_visible"], m["visible"])
        L.append(
            f"| {cam['code']} | {t['kind']} | {cam.get('camera_class')}, {t['view']} | "
            f"{'yes' if cam.get('anpr_viable') else 'no'} | {cam['resolution']} {cam.get('codec')} {cam.get('fps')} fps | "
            f"{m['n']} | {pct(m['exact'], m['n'])} | {pct(m['near'], m['n'])} | {shown} | "
            f"{pct(m['captured'], m['gt'])} | {m['plate_px']:.0f} | {m['minutes']} |")
    L += [row for row in (pooled(STOCK, cams, results), pooled(SYNTH, cams, results)) if row]
    L.append("")
    if missing:
        L += [f"No worker sightings in this window for: {', '.join(missing)} (not analysed in this window, "
              "or nothing read). They have ground truth and can be measured the same way.", ""]
    loops = sorted({f"{t['loop_s']:g}" for t, _ in results.values()})
    L += definitions(" or ".join(loops))
    L += detail(cams, results)
    return "\n".join(L) + "\n"


def definitions(loop: str) -> list[str]:
    return [
        "## Definitions",
        "",
        "- **Sighting**: one row the worker stored in `vehicle_sightings`, i.e. one confirmed plate track "
        "(several OCR reads of one vehicle), not one OCR read. A plate seen again on a later pass (the "
        "clips loop) is a new sighting. Rows the worker did not write (track id not starting with "
        "`<camera>-`, e.g. the smoke test's `smoke`) are left out and counted in the detail below.",
        "- **Precision (exact)**: sightings whose stored `plate_norm` equals one of that camera's "
        "ground-truth plates, over all of that camera's sightings in the window.",
        "- **Within one character**: same length and at most one character different from one of that "
        "camera's ground-truth plates (exact reads included). This is the watchlist's fuzzy rule "
        "(`FUZZY_MAX_EDITS=1`), so such a read would still raise the alert for its true plate (subject to "
        "the alert cooldown; the current API skips a one-character match on a sighting built from a "
        "single read).",
        f"- **Capture rate, plates shown >= {VISIBLE_S:g} s**: distinct ground-truth plates read exactly at "
        "least once in the window, over distinct ground-truth plates the clip shows. The clips loop (every "
        f"{loop} s), so a plate counts as captured if it was read in any loop. For stock footage, \"shows\" "
        f"means painted on screen for at least {VISIBLE_S:g} s in total (`frames_painted` in "
        "`<CODE>.plates.json`). That ground truth does not record plate size or legibility, and a plate on "
        "screen can be far away, tiny, blurred or half-hidden, so the rate is a floor for legible plates, "
        "not the rate for legible plates. For synthetic clips every listed plate crosses the view several "
        "times a loop, so over a window of many loops their capture is all but certain and says little.",
        "- **Capture rate, every plate**: the same over every plate the painter logged, including plates "
        "painted for a few frames only.",
        "- **Ground-truth plate** (stock footage): a registration the painter assigned, not a vehicle. "
        "Its tracker gives a new registration to a plate it lost for more than 25 frames or that jumped "
        "past its gate, so one vehicle can carry two; a read of the second leaves the first uncaptured.",
        "- **Median plate box width**: median width in stream pixels (the camera's resolution) of the "
        "detector's plate box on the sightings, i.e. of plates that were read, not of all plates shown.",
        "- **Active minutes**: distinct clock minutes with at least one sighting on that camera; a rough "
        "proxy for how many loops the worker analysed, not a measurement of it.",
        "- **Pooled**: sums over the cameras of that kind with sightings in the window, so busier cameras "
        "weigh more.",
        "",
    ]


def detail(cams: list[dict], results: dict) -> list[str]:
    L = ["## Detail per camera", ""]
    for cam in cams:
        t, m = results[cam["code"]]
        if not m["n"]:
            continue
        L += [f"### {cam['code']} ({cam['name']})", "",
              f"{m['n']} sightings from {m['first'].astimezone(IST):%Y-%m-%d %H:%M} to "
              f"{m['last'].astimezone(IST):%Y-%m-%d %H:%M} IST; {m['distinct_read']} distinct plates read, "
              f"{m['distinct_wrong']} of them not ground truth; {m['gt']} ground-truth plates; "
              f"{m['injected']} injected (non-worker) rows left out."]
        if m["stale"]:
            L.append(f"**Warning:** `{t['file'].name}` is newer than the first sighting in the window, so some "
                     "sightings may come from an earlier version of the clip.")
        L.append("")
        if m["bands"]:
            L += ["| Time painted on screen | Plates | Captured exactly |", "|---|---|---|",
                  *(f"| {band_label(lo, hi, ' s')} | {n} | {pct(k, n)} |" for lo, hi, n, k in m["bands"]), ""]
        L += ["| OCR confidence | Sightings | Exact |", "|---|---|---|",
              *(f"| {band_label(lo, hi)} | {n} | {pct(k, n)} |" for lo, hi, n, k in m["conf"]), ""]
        if m["wrong"]:
            L += ["Most frequent wrong reads (nearest ground-truth plate, edit distance):", "",
                  *(f"- `{p}` x{k}: nearest `{g}`, {d} edit{'s' if d != 1 else ''}" for p, k, d, g in m["wrong"]), ""]
    L += [
        "## Caveats",
        "",
        "- Plates are synthetic registrations painted onto stock footage (or drawn); not real Gujarat plates. "
        "Real plates vary in font, layout (two-row, high-security, hand-painted), dirt, glare and IR at "
        "night. Precision on real plates is unmeasured.",
        "- The stock clips are 60 s of Pexels footage re-encoded at up to 4 Mbps (`realclip.py`), replayed "
        "in a loop: the same vehicles pass again every loop, so precision is over repeated passes of the "
        "same painted plates (the detail gives how many distinct plates were read), not over as many "
        "different vehicles as there are sightings.",
        "- The painter (`feedsim/realclip.py`) replaces only the plates its detector finds. A plate it "
        "missed keeps its original characters, and a read of it counts here as a wrong read. Such reads "
        "would fall outside the \"within one character\" share: a real registration is very unlikely to be "
        "one character from a painted one.",
        "- The worker's settings (streams per machine, achieved analysis rate, code version) are not stored "
        "with the sightings; they are only what the Conditions lines above say.",
    ]
    return L


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--hours", type=float, default=24.0, help="window ending now (ignored with --since)")
    ap.add_argument("--camera", action="append", help="repeatable; default every camera with ground truth")
    ap.add_argument("--note", action="append", default=[], help="conditions to print with the results")
    ap.add_argument("--out", default=str(ROOT / "bench/results/anpr_eval.md"))
    a = ap.parse_args()
    until = parse_ts(a.until) if a.until else datetime.now(timezone.utc)
    since = parse_ts(a.since) if a.since else until - timedelta(hours=a.hours)

    fleet = yaml.safe_load((FEEDSIM / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]
    cams = [c for c in fleet if not a.camera or c["code"] in a.camera]
    truths = {c["code"]: t for c in cams if (t := load_truth(c))}
    cams = sorted((c for c in cams if c["code"] in truths), key=lambda c: (not c.get("real"), c["code"]))
    rows = await fetch(since, until, [c["code"] for c in cams])
    results = {c["code"]: (truths[c["code"]], evaluate(c["code"], truths[c["code"]],
                                                       [r for r in rows if r["camera_code"] == c["code"]]))
               for c in cams}
    text = report(cams, results, since, until, a.note, a.camera)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(asyncio.run(main()))
