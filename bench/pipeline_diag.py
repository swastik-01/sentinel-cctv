"""Where do stored plates go wrong? Counts behind bench/results/pipeline_review.md, from data already collected.

Nothing here runs the worker, touches the GPU or reads a camera. Three read-only views:

1. The team's blind review of stored sandbox sightings (plate_reviews, mode 'blind', reviewer 'admin'), joined to
   the stored sighting (box, confidences) and to the worker logs that stored it (reads per track). The reviewer's
   reading is the answer (right 222/226 on our own plates, review_truth.md). Descriptive only: nothing is re-read
   and nothing is tuned on these crops.
2. Our own feeds: the sightings of the 26 Sep 11:05-11:15 worker run (data/plate-gate-confirm/worker.log) against
   the plates realclip.py painted, with reads per track from that run's log.
3. Our own feeds, per read: the frozen ownfeed-v1 crops and the stored baseline OCR run over them
   (data/ocr-eval/runs), with each crop's size and sharpness, to ask whether size or sharpness says anything about a
   read beyond its OCR confidence (the case for weighting votes or choosing the evidence crop by them).

Plate text stays in memory; the report holds counts and rates only.

    PYTHONUTF8=1 uv run --no-sync python bench/pipeline_diag.py [--out bench/results/pipeline_diag.md]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import cv2
import numpy as np
import yaml

from sentinel_api.config import get_settings
from sentinel_common import normalise_plate
from sentinel_common.plates import _BH, _LOOKALIKES, _STD, _TO_ALPHA, _TO_DIGIT

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
_spec = importlib.util.spec_from_file_location("anpr_eval", ROOT / "scripts" / "anpr_eval.py")
anpr_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anpr_eval)

LOG_LINE = re.compile(r"sentinel\.worker: (\S+): (\S+) \(ocr ([0-9.]+), (\d+) reads\).*@ (\d\d:\d\d:\d\d)\s*$")
OWN_RUN = ROOT / "data" / "plate-gate-confirm"
OWN_START, OWN_STOP = datetime(2026, 9, 26, 11, 5, 22, tzinfo=IST), datetime(2026, 9, 26, 11, 15, 44, tzinfo=IST)
OWNFEED = ROOT / "data" / "ocr-eval" / "ownfeed-v1"
OWNFEED_RUN = ROOT / "data" / "ocr-eval" / "runs" / "ocr_baseline__ownfeed-v1__cct-xs-v2-global-model.csv"

# v1's window only: later sandbox sightings are sandbox-fresh-v1, scored only from its frozen files by
# bench/sandbox_fresh.py and never pooled with v1 (bench/pipeline_gates.md, "Real labelled data").
REVIEWS_SQL = """
SELECT c.camera_code, r.verdict, r.seen, s.plate_norm, round(s.ocr_conf::numeric, 3)::float8 AS ocr_conf,
       round(s.det_conf::numeric, 3)::float8 AS det_conf, s.bbox, s.event_ts
FROM plate_reviews r JOIN users u ON u.id = r.reviewer_id JOIN cameras c ON c.id = r.camera_id
JOIN vehicle_sightings s ON s.id = r.sighting_id AND s.event_ts = r.sighting_ts
WHERE r.mode = 'blind' AND u.username = 'admin' AND c.camera_code ~ '^CAM[0-9]{2}$'
  AND r.sighting_ts <= '2026-09-26 07:56:00+05:30'"""
OWN_SQL = """
SELECT c.camera_code, s.plate_norm, round(s.ocr_conf::numeric, 3)::float8 AS ocr_conf, s.bbox, s.event_ts, s.track_id
FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
WHERE s.event_ts >= $1 AND s.event_ts < $2 AND c.camera_code = ANY($3::text[])"""
SANDBOX_SQL = """
SELECT c.camera_code, s.plate_norm, s.event_ts, s.track_id
FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
WHERE c.camera_code = ANY($1::text[]) AND s.event_ts >= $2 AND s.event_ts < $3"""
TWIN_S = 10.0       # two stored plates this close on one camera and 1-2 edits apart: almost always one vehicle


def twins(rows: list) -> list[tuple]:
    """Pairs of worker-stored sightings on one camera within TWIN_S whose plates differ by 1 or 2 edits: one vehicle
    stored twice with two different reads. The repeat filter (tracker.py) already folds a same-length,
    one-substitution variant into the plate emitted before it, so what is left is a dropped or added character, or
    two edits."""
    by_cam: dict[str, list] = defaultdict(list)
    for r in rows:
        if (r["track_id"] or "").startswith(r["camera_code"] + "-"):
            by_cam[r["camera_code"]].append(r)
    out = []
    for rs in by_cam.values():
        rs.sort(key=lambda r: r["event_ts"])
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                if (b["event_ts"] - a["event_ts"]).total_seconds() > TWIN_S:
                    break
                if 1 <= anpr_eval.edits(a["plate_norm"], b["plate_norm"]) <= 2:
                    out.append((a, b))
    return out


# ------------------------------------------------------------------ helpers
def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "n/a"


def band(x: float, edges: list[float], unit: str = "") -> str:
    lo = None
    for e in edges:
        if x < e:
            return f"< {e:g}{unit}" if lo is None else f"{lo:g}-{e:g}{unit}"
        lo = e
    return f">= {lo:g}{unit}"


def band_order(edges: list[float], unit: str = "") -> list[str]:
    out, lo = [], None
    for e in edges:
        out.append(f"< {e:g}{unit}" if lo is None else f"{lo:g}-{e:g}{unit}")
        lo = e
    return out + [f">= {lo:g}{unit}"]


def reading(seen: str) -> str:
    """The review page's own cleaning of what the reviewer typed (services/api/sentinel_api/review.py)."""
    return "".join(ch for ch in (seen or "").upper() if ch.isascii() and ch.isalnum())


def ops(truth: str, read: str) -> list[tuple[str, int, str, str]]:
    """Levenshtein alignment: (op, truth position, truth char, read char), op in sub | miss (read dropped a truth
    character) | extra (read added one)."""
    n, m = len(truth), len(read)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (truth[i - 1] != read[j - 1]))
    out, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (truth[i - 1] != read[j - 1]):
            if truth[i - 1] != read[j - 1]:
                out.append(("sub", i - 1, truth[i - 1], read[j - 1]))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            out.append(("miss", i - 1, truth[i - 1], ""))
            i -= 1
        else:
            out.append(("extra", i, "", read[j - 1]))
            j -= 1
    return out[::-1]


def role(truth: str, pos: int) -> str:
    """Which part of the registration a truth position is: state, RTO, series, number (BH: year, BH, number, tail)."""
    m = _STD.match(truth)
    if m:
        ends = np.cumsum([len(g) for g in m.groups()])
        return ("state", "RTO", "series", "number")[int(np.searchsorted(ends, pos, side="right"))] if pos < len(truth) \
            else "end"
    if _BH.match(truth):
        return "BH"
    return "unparsed"


def lookalike(a: str, b: str) -> bool:
    """A confusion the normaliser already knows: digit/letter pairs it repairs by position, or letter look-alikes."""
    pairs = {(chr(k), v if isinstance(v, str) else chr(v)) for table in (_TO_DIGIT, _TO_ALPHA) for k, v in table.items()}
    return (a, b) in pairs or (b, a) in pairs or b in _LOOKALIKES.get(a, "") or a in _LOOKALIKES.get(b, "")


STANDARD = "standard or BH layout"


def truth_form(t: str) -> str:
    if _STD.match(t) or _BH.match(t):
        return STANDARD
    n = normalise_plate(t)
    if len(n) == len(t) and (_STD.match(n) or _BH.match(n)):
        return "standard once a look-alike is read by position (a digit typed for a letter, or back)"
    if re.fullmatch(r"[A-Z]{2}\d[A-Z]{1,3}\d{4}", t):
        return "one-digit RTO code"
    if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z]{1,3}\d{1,3}", t):
        return "number part shorter than 4 digits"
    return "other (extra or missing characters)"


def load_logs(paths: list[Path]) -> dict[tuple[str, str], list[tuple[datetime, str, int]]]:
    """(camera, plate) -> [(log time, event HH:MM:SS UTC, reads)] from the worker's sighting lines."""
    out: dict[tuple[str, str], list] = defaultdict(list)
    for p in paths:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LOG_LINE.search(line)
            if not m:
                continue
            try:
                logged = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            except ValueError:
                continue
            out[(m.group(1), m.group(2))].append((logged, m.group(5), int(m.group(4))))
    return out


STATUS = re.compile(r"(\d+)/(\d+) streams up \| analysed ([0-9.]+) fps total")


def per_camera_fps(paths: list[Path]) -> str:
    """Analysed frames per second per camera from the worker's 30 s status lines (total over streams up)."""
    vals = [float(m.group(3)) / int(m.group(1)) for p in paths
            for m in STATUS.finditer(p.read_text(encoding="utf-8", errors="replace")) if int(m.group(1))]
    if not vals:
        return "no status lines"
    q = np.quantile(vals, [0.25, 0.5, 0.75])
    return f"median {q[1]:.1f}, quartiles {q[0]:.1f}-{q[2]:.1f}, over {len(vals)} status lines"


def reads_for(logs, camera: str, plate: str, ts: datetime) -> int | None:
    hms = ts.astimezone(timezone.utc).strftime("%H:%M:%S")
    for logged, when, n in logs.get((camera, plate), []):
        if when == hms and abs(logged - ts) <= timedelta(minutes=2):   # frame time can run ahead of the log clock
            return n
    return None


def reads_band(n: int | None) -> str:
    return "not in a log" if n is None else "4+" if n >= 4 else str(n)


def verdict_table(title: str, rows: list[tuple[str, str]], order: list[str]) -> list[str]:
    """rows: (group, verdict) -> a table of exact / one off / wrong per group."""
    c = Counter(rows)
    L = [f"| {title} | plates | exact | within one | wrong (2+ edits) |", "|---|---|---|---|---|"]
    for g in order:
        n = sum(c[(g, v)] for v in ("exact", "one_off", "wrong"))
        if n:
            L.append(f"| {g} | {n} | {pct(c[(g, 'exact')], n)} | {pct(c[(g, 'exact')] + c[(g, 'one_off')], n)} "
                     f"| {c[(g, 'wrong')]} |")
    return L


# ------------------------------------------------------------------ 1. sandbox blind review
async def fetch(sql: str, *args) -> list:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        async with conn.transaction(readonly=True):
            return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def sandbox_section() -> list[str]:
    rows = asyncio.run(fetch(REVIEWS_SQL))
    paths = sorted((ROOT / "data").glob("rotation*/*.log"))
    logs = load_logs(paths)
    plates = [r for r in rows if r["verdict"] in ("exact", "one_off", "wrong")]
    cams = sorted({r["camera_code"] for r in plates})
    verdicts = Counter(r["verdict"] for r in rows)
    L = ["## 1. Sandbox: the team's blind review of stored sightings", "",
         f"{len(rows)} blind reviews by `admin` on the sandbox cameras ({', '.join(f'{v} {n}' for v, n in sorted(verdicts.items()))}); "
         f"the {len(plates)} vehicle plates are analysed below. Reads per track come from the worker logs that stored "
         "them (`data/rotation*/`), matched on camera, plate and second. Analysed frames per second per camera in the "
         f"worker runs that took {', '.join(cams)}: "
         f"{per_camera_fps([p for p in paths if any(c in p.name for c in cams)])} (our own-feed reference run: about "
         "4.5). A track closes at 3 reads (`CONFIRM_READS`), so no track has more.", ""]

    reads = [(reads_band(reads_for(logs, r["camera_code"], r["plate_norm"], r["event_ts"])), r["verdict"]) for r in plates]
    L += ["### Reads behind each stored plate", ""] + \
        verdict_table("Reads in the track", reads, ["1", "2", "3", "4+", "not in a log"]) + [""]

    w_edges = [50, 65, 80, 100]
    width = [(band(r["bbox"][2], w_edges, " px"), r["verdict"]) for r in plates]
    L += ["### Plate box width (stream pixels, 1920x1080 or 1280x720)", ""] + \
        verdict_table("Box width", width, band_order(w_edges, " px")) + [""]

    boosted = [r for r in plates if r["ocr_conf"] == 0.9]
    L += ["### Stored confidence as a routing threshold", "",
          "The stored confidence is the best read's weakest character, raised to 0.6 + 0.1 x reads (at most 0.99) when "
          "three or more reads agree on every character (`tracker.py`). A track closes at 3 reads, so three agreeing "
          f"reads whose best was below 0.9 are stored at exactly 0.9: {len(boosted)} plates, "
          f"{pct(sum(r['verdict'] == 'exact' for r in boosted), len(boosted))} exact. Confidences are rounded to 3 "
          "decimals (the column is REAL: 0.9 comes back as 0.8999999761).", "",
          "| Auto band (stored confidence >=) | plates in band | share of plates | exact in band | within one in band | exact below band |",
          "|---|---|---|---|---|---|"]
    for t in (0.6, 0.7, 0.8, 0.9, 0.95, 0.98):
        hi = [r for r in plates if r["ocr_conf"] >= t]
        lo = [r for r in plates if r["ocr_conf"] < t]
        ex = sum(r["verdict"] == "exact" for r in hi)
        w1 = sum(r["verdict"] in ("exact", "one_off") for r in hi)
        L.append(f"| {t:g} | {len(hi)} | {pct(len(hi), len(plates))} | {pct(ex, len(hi))} | {pct(w1, len(hi))} "
                 f"| {pct(sum(r['verdict'] == 'exact' for r in lo), len(lo))} |")
    both = [(f"{reads_band(reads_for(logs, r['camera_code'], r['plate_norm'], r['event_ts']))} read(s), conf "
             f"{band(r['ocr_conf'], [0.6, 0.9])}", r["verdict"]) for r in plates]
    L += ["", "### Confidence and reads together", "",
          "A 1-read track is stored only on a camera analysed below 2 frames per second and only at confidence >= 0.6 "
          "(`SLOW_FPS`, `SINGLE_READ_CONF`); 2 reads are stored at any confidence that passed the gate (0.35). With two "
          "reads the per-character vote (each read weighted by its weakest character) always follows the more "
          "confident read.", ""] + verdict_table(
        "Track", both, [f"{n} read(s), conf {b}" for n in ("1", "2", "3") for b in band_order([0.6, 0.9])]) + [""]

    lo_ts, hi_ts = min(r["event_ts"] for r in plates), max(r["event_ts"] for r in plates)
    stored = asyncio.run(fetch(SANDBOX_SQL, cams, lo_ts, hi_ts + timedelta(seconds=1)))
    pairs = twins(stored)
    in_pairs = {(r["camera_code"], r["event_ts"]) for p in pairs for r in p}
    verdict_of = {(r["camera_code"], r["event_ts"]): r["verdict"] for r in plates}
    judged = Counter()
    for a, b in pairs:
        va, vb = verdict_of.get((a["camera_code"], a["event_ts"])), verdict_of.get((b["camera_code"], b["event_ts"]))
        if va and vb:
            judged["earlier exact, later not" if va == "exact" and vb != "exact" else
                   "later exact, earlier not" if vb == "exact" and va != "exact" else
                   "both exact" if va == vb == "exact" else "neither exact"] += 1
    L += ["", "### One vehicle stored twice", "",
          f"All {len(stored)} sightings the worker stored on {', '.join(cams)} over the reviewed period: {len(pairs)} "
          f"pairs within {TWIN_S:g} s on one camera whose plates are 1-2 edits apart, involving {len(in_pairs)} "
          f"sightings ({pct(len(in_pairs), len(stored))}). Pairs with both sightings reviewed: "
          + (", ".join(f"{k} {n}" for k, n in judged.most_common()) or "none") + ".", ""]

    d_edges = [0.5, 0.7]
    det = [(band(r["det_conf"], d_edges), r["verdict"]) for r in plates]
    L += ["### Detector confidence (YOLO box, or the classical finder's 0.45-0.9)", ""] + \
        verdict_table("Detector confidence", det, band_order(d_edges)) + [""]

    # error anatomy
    forms = Counter()
    form_verdict = Counter()
    kinds = Counter()
    sub_roles = Counter()
    sub_look = Counter()
    miss_where = Counter()
    miss_roles = Counter()
    shortened = Counter()
    for r in plates:
        t, s = reading(r["seen"]), r["plate_norm"]
        f = truth_form(t)
        forms[f] += 1
        form_verdict[(f, r["verdict"])] += 1
        if r["verdict"] == "exact" or f != STANDARD:   # a typed look-alike or typo is not the pipeline's error
            continue
        o = ops(t, s)
        if len(s) < len(t):
            mt, ms = _STD.match(t), _STD.match(s)
            shortened["shorter"] += 1
            # the true plate's last series letter reappears as the stored number's first digit: the positional repair
            # filled the 4-digit number from the series after the OCR lost a digit
            shortened["repaired"] += bool(mt and ms and len(ms.group(3)) < len(mt.group(3))
                                          and mt.group(3)[-1].translate(_TO_DIGIT) == ms.group(4)[0])
        kinds["same length, substitutions only" if all(k == "sub" for k, *_ in o) else
               "read shorter (dropped characters)" if len(s) < len(t) else
               "read longer (added characters)" if len(s) > len(t) else "same length, mixed edits"] += 1
        for k, pos, a, b in o:
            if k == "sub":
                sub_roles[role(t, pos)] += 1
                sub_look["look-alike pair" if lookalike(a, b) else "other pair"] += 1
            else:   # a dropped character at the plate's ends is what a tight crop does
                end = pos == 0 or (pos == len(t) - 1 if k == "miss" else pos == len(t))
                miss_roles[role(t, min(pos, len(t) - 1)) + (" (dropped)" if k == "miss" else " (added)")] += 1
                miss_where[("first or last character" if end else "inside")
                           + f" ({'dropped' if k == 'miss' else 'added'})"] += 1
    wrong = sum(kinds.values())
    L += ["### What the non-exact reads got wrong", "",
          f"{wrong} plates stored not exact whose true plate (the reviewer's reading) is in the standard layout; the "
          "rest are in the layout table below. Positions are the true plate's.", "",
          "| Kind of error (per plate) | plates |", "|---|---|"] + \
         [f"| {k} | {n} |" for k, n in kinds.most_common()] + \
         ["", "| Substituted character, part of the registration | characters |", "|---|---|"] + \
         [f"| {k} | {n} |" for k, n in sub_roles.most_common()] + \
         ["", "| Substitution pair | characters |", "|---|---|"] + \
         [f"| {k} | {n} |" for k, n in sub_look.most_common()] + \
         ["", "| Dropped or added character | characters |", "|---|---|"] + \
         ([f"| {k} | {n} |" for k, n in miss_where.most_common()] or ["| none | 0 |"]) +          ["", f"Of the {shortened['shorter']} stored reads shorter than the true plate, {shortened['repaired']} have a "
          "one-letter series where the true plate has two, and a number that starts with the digit look-alike of the "
          "true plate's last series letter: the OCR lost a digit and `normalise_plate` filled the 4-digit number from "
          "the series, which leaves a valid-looking plate that passes the gate. The watchlist's fuzzy match compares "
          "plates of the same length only, so such a read cannot raise the alert for its true plate. Where the "
          "alignment below puts a dropped character is one of several equally short explanations.", "",
          "| Dropped or added character, part of the registration | characters |", "|---|---|"] +          ([f"| {k} | {n} |" for k, n in miss_roles.most_common()] or ["| none | 0 |"]) + \
         ["", "### Layout of the true plates", "",
          "`normalise_plate` accepts SS 00 L{1,3} 0000 and BH plates only; a plate in any other form can never be "
          "stored exactly.", "", "| True plate layout | plates | stored exact | one off | wrong |", "|---|---|---|---|---|"] + \
         [f"| {f} | {n} | {form_verdict[(f, 'exact')]} | {form_verdict[(f, 'one_off')]} | {form_verdict[(f, 'wrong')]} |"
          for f, n in forms.most_common()] + [""]
    return L


# ------------------------------------------------------------------ 2. own feed, stored sightings
def own_section() -> list[str]:
    cams = {c["code"]: c for c in yaml.safe_load((ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]}
    codes = ["AMD-TRAF-001", "AMD-TRAF-002"]
    rows = asyncio.run(fetch(OWN_SQL, OWN_START, OWN_STOP, codes))
    logs = load_logs([OWN_RUN / "worker.log"])
    truth = {c: set(anpr_eval.load_truth(cams[c])["plates"]) for c in codes}
    recs = []
    for r in rows:
        if not (r["track_id"] or "").startswith(r["camera_code"] + "-"):
            continue
        gt = truth[r["camera_code"]]
        near = min(anpr_eval.edits(r["plate_norm"], g) for g in gt)
        if near > 2:            # a real, unpainted plate or other text: no ground truth for it
            continue
        v = "exact" if near == 0 else "one_off" if near == 1 else "wrong"
        recs.append((r, v, reads_for(logs, r["camera_code"], r["plate_norm"], r["event_ts"])))
    L = ["## 2. Own feeds: stored sightings against the painted plates", "",
         f"The worker run of 26 Sep 11:05-11:15 IST (`data/plate-gate-confirm/worker.env`: 4 cameras on one worker, "
         f"HW_DECODE=auto, object detection on, DETECT_FPS=5; analysed frames per second per camera: "
         f"{per_camera_fps([OWN_RUN / 'worker.log'])}, so part of it ran the slow-camera single-read path, below 2). "
         f"AMD-TRAF-001/002 only (stock footage, synthetic "
         f"plates painted on); sightings within 2 edits of a painted plate ({len(recs)}), so real unpainted plates "
         f"are left out. Wrong here means 2 edits.", ""]
    for cam in codes:
        sub = [x for x in recs if x[0]["camera_code"] == cam]
        L += [f"### {cam}", ""] + verdict_table("Reads in the track", [(reads_band(n), v) for _, v, n in sub],
                                                ["1", "2", "3", "4+", "not in a log"]) + [""]
        L += verdict_table("Box width", [(band(r["bbox"][2], [50, 65, 80, 100], " px"), v) for r, v, _ in sub],
                           band_order([50, 65, 80, 100], " px")) + [""]
        L += verdict_table("Stored confidence", [(band(r["ocr_conf"], [0.7, 0.9]), v) for r, v, _ in sub],
                           band_order([0.7, 0.9])) + [""]
    worker_rows = [r for r in rows if (r["track_id"] or "").startswith(r["camera_code"] + "-")]
    pairs = twins(worker_rows)
    judged = Counter()
    for a, b in pairs:
        ea, eb = (r["plate_norm"] in truth[r["camera_code"]] for r in (a, b))
        judged["earlier exact, later not" if ea and not eb else "later exact, earlier not" if eb and not ea else
               "both exact (two painted plates 1-2 edits apart)" if ea and eb else "neither exact"] += 1
    in_pairs = {(r["camera_code"], r["event_ts"]) for p in pairs for r in p}
    L += ["### One vehicle stored twice", "",
          f"All {len(worker_rows)} sightings the worker stored on AMD-TRAF-001/002 in the run: {len(pairs)} pairs within "
          f"{TWIN_S:g} s on one camera whose plates are 1-2 edits apart, involving {len(in_pairs)} sightings "
          f"({pct(len(in_pairs), len(worker_rows))}): " + ", ".join(f"{k} {n}" for k, n in judged.most_common()) + ".", ""]
    return L


# ------------------------------------------------------------------ 3. own feed, per read
def sharpness(img: np.ndarray) -> float:
    """Variance of the Laplacian on the crop as the OCR sees it (128x64, grey): blur and upscaling both lower it."""
    g = cv2.cvtColor(cv2.resize(img, (128, 64), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def per_read_section() -> list[str]:
    with open(OWNFEED / "manifest.csv", encoding="utf-8") as f:
        man = {r["id"]: r for r in csv.DictReader(f)}
    with open(OWNFEED_RUN, encoding="utf-8") as f:
        run = {r["id"]: r for r in csv.DictReader(f)}
    recs = []
    for cid, m in man.items():
        r = run.get(cid)
        img = cv2.imread(str(OWNFEED / f"{cid}.jpg"))
        if r is None or img is None:
            continue
        recs.append({"w": img.shape[1], "sharp": sharpness(img), "conf": float(r["conf"]),
                     "exact": normalise_plate(r["norm"]) == m["true_plate"], "cam": m["camera"]})
    sharp_q = np.quantile([x["sharp"] for x in recs], [0.25, 0.5, 0.75])
    w_edges = [70, 90, 110, 140]

    def tab(title: str, key, order: list[str]) -> list[str]:
        c, n = Counter(), Counter()
        for x in recs:
            g = key(x)
            n[g] += 1
            c[g] += x["exact"]
        return [f"| {title} | reads | exact |", "|---|---|---|"] + [f"| {g} | {n[g]} | {pct(c[g], n[g])} |" for g in order if n[g]]

    sq = ["lowest quarter", "second quarter", "third quarter", "highest quarter"]
    L = ["## 3. Own feeds, per read: does crop size or sharpness add to OCR confidence?", "",
         f"`ownfeed-v1`: {len(recs)} evidence crops from AMD-TRAF-001/002 (synthetic plates painted on stock footage), "
         "each read once by the shipped OCR in the stored baseline run (`data/ocr-eval/runs`). Width is the padded crop "
         "in stream pixels; sharpness is the variance of the Laplacian after resizing to the OCR's 128x64 input. The "
         "set is biased towards reads the product got nearly right (labelled by matching the stored read within 2 "
         "edits), and every crop is already the best-confidence read of its track.", ""]
    L += tab("Crop width", lambda x: band(x["w"], w_edges, " px"), band_order(w_edges, " px")) + [""]
    L += tab("Sharpness", lambda x: sq[int(np.searchsorted(sharp_q, x["sharp"], side="right"))], sq) + [""]
    L += ["Within one confidence band, does the sharper or larger half read better?", "",
          "| OCR confidence | reads | exact, blurrier half | exact, sharper half | exact, narrower half | exact, wider half |",
          "|---|---|---|---|---|---|"]
    for lo, hi in ((0.0, 0.7), (0.7, 0.9), (0.9, 1.01)):
        sub = [x for x in recs if lo <= x["conf"] < hi]
        if not sub:
            continue
        ms, mw = np.median([x["sharp"] for x in sub]), np.median([x["w"] for x in sub])
        cells = []
        for key, med in (("sharp", ms), ("w", mw)):
            a = [x for x in sub if x[key] < med]
            b = [x for x in sub if x[key] >= med]
            cells += [pct(sum(x["exact"] for x in a), len(a)), pct(sum(x["exact"] for x in b), len(b))]
        L.append(f"| {lo:g}-{min(hi, 1):g} | {len(sub)} | " + " | ".join(cells) + " |")
    L += [""]
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "pipeline_diag.md"))
    a = ap.parse_args()
    L = ["# Plate pipeline: where stored reads go wrong", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/pipeline_diag.py` from data already collected "
         "(read-only database access, worker logs, stored OCR runs). No worker was run and no camera was read for it. "
         "Counts and rates only: no plate text is written here. Read with `pipeline_review.md`.", ""]
    L += sandbox_section() + own_section() + per_read_section()
    L += ["## Caveats", "",
          "- Section 1 is one reviewer's reading of 120 plates on three sandbox cameras (mostly CAM06), 55 vehicles or "
          "fewer; the per-row counts are small, so read them as directions, not rates.",
          "- Reads per track are matched from the worker's log lines; a sighting whose line was not found is counted "
          "apart. The log's confidence is the stored one.",
          "- Sections 2 and 3 are synthetic plates in one clean font painted on Pexels stock footage: real plates' "
          "errors (fonts, dirt, glare, two-line layouts, night IR) are not in them.",
          "- Section 2's run was at a low and variable analysis rate; `anpr_eval_current.md` is the reference run at "
          "about 4.5 frames per second per camera.", ""]
    text = "\n".join(L)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
