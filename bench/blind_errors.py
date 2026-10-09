"""Why stored sandbox plates were missed: an error analysis of the blind-checked set sandbox-blind-v1.

    PYTHONUTF8=1 uv run --no-sync python bench/blind_errors.py [--out bench/results/blind_errors.md]
    PYTHONUTF8=1 uv run --no-sync python bench/blind_errors.py --sheets    # once: sheets for the blind second reading

A team member read 120 stored sandbox plates blind (bench/ocr_sets.py blind): 90 exact, 30 misses (17 one off, 13
wrong). Before choosing a fix, this asks what the misses share that the hits do not, and which characters went wrong.
Nothing is re-read or tuned here: the set is test-only (bench/ocr_gates.md, addendum 1). The inputs, all read-only:

- the frozen manifest and crops (data/ocr-eval/sandbox-blind-v1);
- bench/ocr_ab.py's single-crop re-reads by the shipped model (data/ocr-eval/runs), for this set and for ownfeed-v1;
- each sighting's plate box, detector confidence and vehicle type (vehicle_sightings);
- reads per track from the worker logs, and the analysis windows of the 25 Sep evening and 26 Sep morning runs
  (data/rotation, data/rotation-day);
- data/ocr-eval/blind-errors/adjudication.csv: for each miss, whose reading the crop supports (sentinel, reviewer, both,
  unclear), the likely cause and the visible condition. Our AI coding assistant wrote it from the crops with both
  readings in view, and from the same vehicle's other passes where the sandbox loop replayed it. That is not blind (the
  same kind of label overstated sandbox-v1), so it ranks causes and is not an answer key;
- data/ocr-eval/blind-errors/second: a check on that file. The same assistant read the 30 misses again, blind this time:
  shuffled among 15 hits on contact sheets that show no reading, no verdict and no id (`--sheets` builds them and the
  key; reading.csv was typed from the sheets before the key was opened). Still an AI and not a person, so it too
  corrects nothing.

Plate text stays in memory. The report holds counts and rates only; the single characters in confusion pairs are not
registrations.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from sentinel_common import looks_like_indian_plate, normalise_plate
from sentinel_common.plates import _LOOKALIKES, _STD, _TO_ALPHA, _TO_DIGIT, _clean

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "data" / "ocr-eval" / "sandbox-blind-v1"
RUNS = ROOT / "data" / "ocr-eval" / "runs"
BLIND_RUN = RUNS / "ocr_baseline_blind__sandbox-blind-v1__cct-xs-v2-global-model.csv"
OWN_RUN = RUNS / "ocr_baseline__ownfeed-v1__cct-xs-v2-global-model.csv"
ADJ = ROOT / "data" / "ocr-eval" / "blind-errors" / "adjudication.csv"
SECOND = ROOT / "data" / "ocr-eval" / "blind-errors" / "second"
# The two runs replayed the same looping sandbox footage (fixed clips, each camera's from one time of day), so the
# labels name the run, never day or night.
WINDOWS = {"25 Sep evening run": ROOT / "data" / "rotation", "26 Sep morning run": ROOT / "data" / "rotation-day"}
IST = timezone(timedelta(hours=5, minutes=30))
PAD = 0.15          # worker.py pads the plate box by 15% of the box height on every side
MODEL_WH = (128, 64)  # the OCR model's input: every crop is stretched to this
MONO_CHROMA = 8     # a camera whose crops never carry more colour than this sends a monochrome (IR) picture
BOOT = 2000
# Two series letters then only three digits: a ten-character plate with a digit missing. normalise_plate turns it into
# a valid one-letter-series plate (the second series letter becomes the number's first digit), so the gate passes it.
SHORT = re.compile(r"^[A-Z]{2}[0-9A-Z]{2}[A-Z]{2}[0-9]{3}$")
LOG_LINE = re.compile(r"sentinel\.worker: (CAM\d\d): ([A-Z0-9]+) \(ocr [0-9.]+, (\d+) reads\).* @ (\d\d:\d\d:\d\d)")
SENTINEL_SIDE = ("sentinel", "both")
CAUSES = {
    "dropped-char": "a character dropped: ten-character plate stored as nine",
    "vote-chose-short": "the vote took the length of truncated reads; the best single read was right",
    "edge-misread": "last characters misread where the plate box stopped short of the plate's end",
    "digit-misread": "a digit read as another digit",
    "letter-lookalike": "a letter read as a similar letter",
    "typo": "reading has an extra, missing or doubled character, or an impossible state code",
    "lookalike-typed": "reviewer typed a look-alike where the format fixes a letter or a digit",
    "reviewer-misread": "crop (and the same vehicle's exact pass, where there is one) shows the stored characters",
    "unreadable": "crop too small or blurred to say who is right",
}


# ----------------------------------------------------------------------------------------------------------- inputs

def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sightings(ids: list[int]) -> dict[int, dict]:
    import asyncpg

    from sentinel_api.config import get_settings

    async def fetch():
        conn = await asyncpg.connect(get_settings().pg_dsn)
        try:
            return await conn.fetch("SELECT id, bbox, det_conf, vehicle_type FROM vehicle_sightings "
                                    "WHERE id = ANY($1::bigint[])", ids)
        finally:
            await conn.close()
    return {r["id"]: dict(r) for r in asyncio.run(fetch())}


def windows() -> dict[str, list[tuple[str, datetime, datetime]]]:
    """camera -> [(run, start, end)] from the rotation files (sandbox_daynight.py reads the same ones)."""
    out: dict[str, list] = defaultdict(list)
    for label, folder in WINDOWS.items():
        for f in sorted(folder.glob("*.csv")):
            for r in read_csv(f):
                a, b = (datetime.fromisoformat(r[k]).replace(tzinfo=IST) for k in ("start_ist", "end_ist"))
                for code in r["cameras"].split(","):
                    out[code].append((label, a, b))
    return out


def sheets(hits: int, seed: int, exclude: set[str]) -> None:
    """Contact sheets for a blind second reading: every miss, shuffled among `hits` random hits, each crop at 150 px
    high beside a contrast-stretched copy and labelled by number only. The key goes beside them, not on them. Refuses
    to redo a key: a new shuffle after a reading would unblind it. `exclude` keeps out hits whose text the reader has
    already seen."""
    key = SECOND / "key.csv"
    if key.exists():
        raise SystemExit(f"{key} exists: a second reading was already set up; delete the folder only to start over")
    rows = read_csv(SET / "manifest.csv")
    rng = random.Random(seed)
    items = [r for r in rows if r["verdict"] != "exact"]
    items += rng.sample([r for r in rows if r["verdict"] == "exact" and r["id"] not in exclude], hits)
    rng.shuffle(items)
    SECOND.mkdir(parents=True, exist_ok=True)
    with open(key, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["n", "id"])
        w.writerows([n, r["id"]] for n, r in enumerate(items, 1))
    h = 150
    for s in range(0, len(items), 8):
        tiles = []
        for n, r in enumerate(items[s:s + 8], s + 1):
            img = cv2.imread(str(SET / f"{r['id']}.jpg"))
            big = cv2.resize(img, (min(int(img.shape[1] * h / img.shape[0]), 520), h), interpolation=cv2.INTER_CUBIC)
            lab = cv2.cvtColor(big, cv2.COLOR_BGR2LAB)
            lab[..., 0] = cv2.createCLAHE(2.0, (4, 4)).apply(lab[..., 0])
            pair = np.hstack([big, np.full((h, 8, 3), 255, np.uint8), cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)])
            tile = np.full((h + 12, 1130, 3), 40, np.uint8)
            tile[6:6 + h, 70:70 + pair.shape[1]] = pair
            cv2.putText(tile, str(n), (8, h // 2 + 12), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 2)
            tiles.append(tile)
        cv2.imwrite(str(SECOND / f"sheet_{s // 8 + 1}.png"), np.vstack(tiles))
    print(f"{len(items)} crops on {(len(items) + 7) // 8} sheets in {SECOND}; type reading.csv (n,reading,sure) "
          "from the sheets before opening key.csv")


def track_reads() -> dict[tuple[str, str, str], int]:
    """(camera, stored plate, UTC hh:mm:ss) -> reads in the track, from the line the worker logs for each sighting."""
    out = {}
    for folder in WINDOWS.values():
        for log in sorted(folder.glob("*.log")):
            with open(log, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = LOG_LINE.search(line)
                    if m:
                        out.setdefault((m[1], m[2], m[4]), int(m[3]))
    return out


# --------------------------------------------------------------------------------------------------------- measures

def image_features(img: np.ndarray, box_h: int) -> dict:
    """Sharpness, light, contrast and colour of a stored crop. The plate region is the crop less the worker's pad."""
    h, w = img.shape[:2]
    p = int(box_h * PAD)
    inner = img[p:h - p, p:w - p] if h > 2 * p and w > 2 * p else img
    grey, grey_in = (cv2.cvtColor(x, cv2.COLOR_BGR2GRAY) for x in (img, inner))
    b, g, r = (img[..., i].astype(int) for i in range(3))
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    bg = hsv[..., 2] >= np.percentile(hsv[..., 2], 60)       # the plate's background (or its bright characters)
    return {"sharp_model": float(cv2.Laplacian(cv2.resize(grey, MODEL_WH), cv2.CV_64F).var()),
            "sharp_native": float(cv2.Laplacian(grey, cv2.CV_64F).var()),
            "brightness": float(grey_in.mean()),
            "contrast": float(np.percentile(grey_in, 95) - np.percentile(grey_in, 5)),
            "chroma": float(np.maximum(np.maximum(abs(b - g), abs(g - r)), abs(b - r)).mean()),
            "hue": float(np.median(hsv[..., 0][bg])), "sat": float(np.median(hsv[..., 1][bg]))}


def plate_colour(f: dict, mono: bool) -> str:
    if mono:
        return "not visible (monochrome picture)"
    if f["sat"] >= 60 and 15 <= f["hue"] <= 35:
        return "yellow"
    if f["sat"] >= 60 and 35 < f["hue"] <= 95:
        return "green"
    return "white"


def align(truth: str, read: str) -> list[tuple[str, str, str, int]]:
    """Edit operations turning the true plate into the read: (sub|dropped|extra, true char, read char, index in truth)."""
    n, m = len(truth), len(read)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j - 1] + (truth[i - 1] != read[j - 1]), d[i - 1][j] + 1, d[i][j - 1] + 1)
    ops, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (truth[i - 1] != read[j - 1]):
            if truth[i - 1] != read[j - 1]:
                ops.append(("sub", truth[i - 1], read[j - 1], i - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("dropped", truth[i - 1], "", i - 1))
            i -= 1
        else:
            ops.append(("extra", "", read[j - 1], i))
            j -= 1
    return ops[::-1]


def slot(truth: str, i: int) -> str:
    """Which part of the plate a position is in: state, district (RTO), series letters or the four-digit number."""
    m = _STD.match(truth)
    if not m:
        return "reading not a standard plate"
    i = min(i, len(truth) - 1)
    return "state" if i < 2 else "district" if i < 4 else "series" if i < len(truth) - 4 else "number"


def sub_class(t: str, s: str) -> str:
    look = s in _LOOKALIKES.get(t, "") or t in _LOOKALIKES.get(s, "")
    if t.isdigit() and s.isdigit():
        return "digit for digit"
    if t.isalpha() and s.isalpha():
        return "letter for similar letter" if look else "letter for other letter"
    look = look or t.translate(_TO_DIGIT) == s or s.translate(_TO_DIGIT) == t or t.translate(_TO_ALPHA) == s \
        or s.translate(_TO_ALPHA) == t
    return "letter/digit look-alike" if look else "letter/digit other"


def auc(lo: np.ndarray, hi: np.ndarray) -> float:
    """P(a miss's value < a hit's value), ties half: 0.5 is no difference; above 0.5, misses tend to be lower."""
    return float((lo[:, None] < hi[None, :]).mean() + 0.5 * (lo[:, None] == hi[None, :]).mean())


def auc_boot(vals: np.ndarray, miss: np.ndarray, groups: list[str], rng) -> list[float] | None:
    """Group bootstrap of the AUC: a vehicle the loop replayed, or crops seconds apart, count as one draw."""
    names = sorted(set(groups))
    idx = {g: [i for i, x in enumerate(groups) if x == g] for g in names}
    stats = []
    for _ in range(BOOT):
        pick = np.concatenate([idx[names[k]] for k in rng.integers(0, len(names), len(names))])
        v, mm = vals[pick], miss[pick]
        if mm.any() and (~mm).any():
            stats.append(auc(v[mm], v[~mm]))
    return [round(float(np.percentile(stats, 2.5)), 3), round(float(np.percentile(stats, 97.5)), 3)] if stats else None


def band(conf: float) -> str:
    return "< 0.6" if conf < 0.6 else "0.6-0.8" if conf < 0.8 else "0.8-0.9" if conf < 0.9 else ">= 0.9"


def short_reads(run: Path) -> dict:
    """How often the model's single read has the dropped-digit shape, and how often such a read is right."""
    rows = read_csv(run)
    hit = [r for r in rows if SHORT.match(_clean(r["read"]))]
    return {"reads": len(rows), "short": len(hit), "short_exact": sum(r["norm"] == r["true_plate"] for r in hit),
            "short_pass_gate": sum(r["gate"] == "1" for r in hit),
            "short_truth_len": dict(Counter(len(r["true_plate"]) for r in hit))}


# ----------------------------------------------------------------------------------------------------------- build

def build() -> tuple[list[dict], dict]:
    rows = read_csv(SET / "manifest.csv")
    crop = {r["id"]: r for r in read_csv(BLIND_RUN)}
    adj = {r["id"]: r for r in read_csv(ADJ)}
    db = sightings([int(r["id"]) for r in rows])
    win, reads = windows(), track_reads()
    recs = []
    for r in rows:
        s = db[int(r["id"])]
        x, y, bw, bh = s["bbox"]
        img = cv2.imread(str(SET / f"{r['id']}.jpg"))
        f = image_features(img, bh)
        ts = datetime.fromisoformat(r["event_ist"]).replace(tzinfo=IST)
        truth_n = normalise_plate(r["true_plate"])
        miss = r["verdict"] != "exact"
        a = adj.get(r["id"], {})
        if miss and not a:
            raise SystemExit(f"{ADJ.name}: no row for a miss (sighting {r['id']})")
        chars = len(truth_n) if looks_like_indian_plate(truth_n) else len(r["stored"])   # a typo'd reading's length
        per_row = -(-chars // 2) if r["layout"] == "two-line" else chars
        recs.append({
            "id": r["id"], "group": r["group"], "camera": r["camera"], "layout": r["layout"], "verdict": r["verdict"],
            "miss": miss, "side": a.get("side", "exact"), "cause": a.get("cause", ""),
            "condition": a.get("condition", ""),
            "truth": r["true_plate"], "truth_n": truth_n, "stored": r["stored"],
            "crop_read": crop[r["id"]]["norm"], "crop_raw": _clean(crop[r["id"]]["read"]),
            "crop_conf": float(crop[r["id"]]["conf"]),
            "conf": float(r["ocr_conf"]), "det_conf": float(s["det_conf"]),
            "vehicle": s["vehicle_type"] or "not bound to a vehicle",
            "crop_w": int(r["width_px"]), "crop_h": int(r["height_px"]),
            "px_per_char": bw / per_row, "box_aspect": bw / bh,
            "reads": reads.get((r["camera"], r["stored"], ts.astimezone(timezone.utc).strftime("%H:%M:%S"))),
            "window": next((lab for lab, t0, t1 in win.get(r["camera"], []) if t0 <= ts < t1), "outside a window"),
            **f})
    mono = {c: max(x["chroma"] for x in recs if x["camera"] == c) < MONO_CHROMA for c in {x["camera"] for x in recs}}
    for x in recs:
        x["picture"] = "monochrome" if mono[x["camera"]] else "colour"
        x["colour"] = plate_colour(x, mono[x["camera"]])
    extra = {"short_blind": short_reads(BLIND_RUN), "short_own": short_reads(OWN_RUN), "mono": mono}
    return recs, extra


# --------------------------------------------------------------------------------------------------------- analyse

NUMERIC = [  # key, label, format
    ("crop_w", "crop width, px", "{:.0f}"),
    ("crop_h", "crop height, px", "{:.0f}"),
    ("px_per_char", "plate box width per character, px", "{:.1f}"),
    ("sharp_model", "sharpness at the model's 128x64 input (Laplacian variance)", "{:.0f}"),
    ("sharp_native", "sharpness at native size (Laplacian variance)", "{:.0f}"),
    ("brightness", "plate brightness (mean grey, 0-255)", "{:.0f}"),
    ("contrast", "plate contrast (grey p95 - p5)", "{:.0f}"),
    ("conf", "Sentinel's stored confidence", "{:.3f}"),
    ("crop_conf", "confidence of the single-crop re-read", "{:.3f}"),
    ("det_conf", "plate detector confidence", "{:.2f}"),
    ("reads", "reads in the track (worker log)", "{:.0f}"),
]
CATEGORIES = [("camera", "Camera"), ("window", "Analysis window"), ("picture", "Picture"),
              ("colour", "Plate colour"), ("layout", "Layout"), ("vehicle", "Vehicle bound to the plate"),
              ("conf_band", "Sentinel's stored confidence"), ("reads_band", "Reads in the track")]
ORDER = {"conf_band": ["< 0.6", "0.6-0.8", "0.8-0.9", ">= 0.9"], "reads_band": ["1", "2", "3", "4 or more", "unknown"]}


def numeric(recs: list[dict], rng) -> list[dict]:
    out = []
    for key, label, fmt in NUMERIC:
        have = [x for x in recs if x[key] is not None]
        vals = np.array([x[key] for x in have], float)
        groups = [x["group"] for x in have]
        row = {"key": key, "label": label, "fmt": fmt, "n": len(have)}
        for name, want in (("all misses", lambda x: x["miss"]),
                           ("Sentinel-side misses", lambda x: x["side"] in SENTINEL_SIDE)):
            keep = np.array([not x["miss"] or want(x) for x in have])    # these misses against the hits
            v, g = vals[keep], [grp for grp, k in zip(groups, keep) if k]
            m = np.array([want(x) for x in have])[keep]
            row[name] = {"median_miss": float(np.median(v[m])), "median_hit": float(np.median(v[~m])),
                         "n_miss": int(m.sum()), "auc": round(auc(v[m], v[~m]), 3), "boot95": auc_boot(v, m, g, rng)}
        out.append(row)
    return out


def categorical(recs: list[dict]) -> dict:
    for x in recs:
        x["conf_band"] = band(x["conf"])
        x["reads_band"] = "unknown" if x["reads"] is None else str(x["reads"]) if x["reads"] < 4 else "4 or more"
    out = {}
    for key, _ in CATEGORIES:
        rows = defaultdict(Counter)
        for x in recs:
            c = rows[x[key]]
            c["n"] += 1
            c["exact"] += not x["miss"]
            c["sentinel"] += x["side"] in SENTINEL_SIDE
            c["reviewer"] += x["side"] == "reviewer"
            c["unclear"] += x["side"] == "unclear"
        order = ORDER.get(key)
        out[key] = {k: dict(v) for k, v in sorted(rows.items(), key=lambda kv: order.index(kv[0]) if order else kv[0])}
    return out


def confusions(recs: list[dict]) -> dict:
    """Character edits from the reviewer's reading (put through normalise_plate, so a look-alike typed where the
    format fixes the kind of character is not counted) to the stored read, and to the single-crop re-read."""
    out = {}
    for name, sel, read in (("stored, all misses", lambda x: x["miss"], "stored"),
                            ("stored, Sentinel-side misses", lambda x: x["side"] in SENTINEL_SIDE, "stored"),
                            ("single-crop re-read, where it is not exact", lambda x: x["crop_read"] != x["truth"],
                             "crop_read")):
        kinds, classes, pairs, per_plate, lengths = Counter(), Counter(), Counter(), Counter(), Counter()
        lookalike = Counter()   # letter/digit look-alikes: normalise's repair after a drop, or a misread of its own
        n = 0
        for x in recs:
            if not sel(x):
                continue
            n += 1
            ops = align(x["truth_n"], x[read])
            per_plate[min(len(ops), 3)] += 1
            lengths[(len(x["truth_n"]), len(x[read]))] += 1
            dropped = any(op[0] == "dropped" for op in ops)
            for kind, t, s, i in ops:
                where = slot(x["truth_n"], i)
                kinds[(kind, where)] += 1
                if kind == "sub":
                    cls = sub_class(t, s)
                    classes[(cls, where)] += 1
                    pairs[f"{t}>{s}"] += 1
                    if cls == "letter/digit look-alike":
                        lookalike["with a drop" if dropped else "without"] += 1
        out[name] = {"n": n, "kinds": kinds, "classes": classes, "pairs": pairs, "per_plate": per_plate,
                     "lengths": lengths, "lookalike": lookalike}
    return out


def drop_at(truth: str, read: str) -> str:
    """Where a nine-character read lost a ten-character plate's character, compared after normalise_plate (which repairs
    look-alikes by position). A repeated character counts at its later position."""
    target = normalise_plate(read)
    pos = [i for i in range(len(truth)) if normalise_plate(truth[:i] + truth[i + 1:]) == target]
    if not pos:
        return "drop plus a misread"
    return "last" if max(pos) == len(truth) - 1 else "second-last" if max(pos) == len(truth) - 2 else "earlier"


def drops(recs: list[dict]) -> dict:
    """Where ten-character plates lost a character: in the stored reads of the Sentinel-side misses, and in the
    single-crop re-reads of this set and of ownfeed-v1 (our own feeds, where the true plate is known). Also the plate
    box's width over height, to see whether a box that stopped short explains it."""
    out = {}
    stored = [x for x in recs if x["side"] in SENTINEL_SIDE and len(x["truth_n"]) == 10 and len(x["stored"]) == 9]
    out["stored, Sentinel-side misses"] = Counter(drop_at(x["truth_n"], x["stored"]) for x in stored)
    for name, run in (("single crop, sandbox-blind-v1", BLIND_RUN), ("single crop, ownfeed-v1", OWN_RUN)):
        c = Counter()
        for r in read_csv(run):
            t, raw = normalise_plate(r["true_plate"]), _clean(r["read"])
            if len(t) == 10 and len(raw) == 9:
                c[drop_at(t, raw)] += 1
        out[name] = c
    one = [x for x in recs if x["layout"] == "one-line"]
    aspect = lambda xs: round(float(np.median([x["box_aspect"] for x in xs])), 2) if xs else None  # noqa: E731
    out["aspect"] = {"one-line stored drops": aspect([x for x in stored if x["layout"] == "one-line"]),
                     "n_drops": sum(x["layout"] == "one-line" for x in stored),
                     "one-line hits": aspect([x for x in one if not x["miss"]]),
                     "n_hits": sum(not x["miss"] for x in one)}
    return {k: dict(v) for k, v in out.items()}


def second_reading(recs: list[dict]) -> dict | None:
    """The blind second reading against both readings, by the adjudication's side. For a miss, 'equal once
    normalised' means the reviewer's reading and the stored read agree after normalise_plate."""
    key, typed = SECOND / "key.csv", SECOND / "reading.csv"
    if not (key.exists() and typed.exists()):
        return None
    ids = {r["n"]: r["id"] for r in read_csv(key)}
    by_id = {x["id"]: x for x in recs}
    out: dict[str, Counter] = defaultdict(Counter)
    for r in read_csv(typed):
        x = by_id[ids[r["n"]]]
        mine = normalise_plate(r["reading"])
        c = out[x["side"] if x["miss"] else "hit"]
        c["n"] += 1
        c["unsure"] += r["sure"] != "1"
        c["both" if mine == x["truth_n"] == x["stored"] else "stored" if mine == x["stored"]
          else "reviewer" if mine == x["truth_n"] else "neither"] += 1
    return {k: dict(v) for k, v in out.items()}


def reviewer_signals(recs: list[dict]) -> dict:
    """Evidence against the reviewer's reading that needs no judgement: not a valid registration as typed; equal to the
    stored read once both are normalised; or the same stored plate on the same camera judged exact on another pass."""
    exact_pass = {(x["camera"], x["stored"]) for x in recs if not x["miss"]}
    out = Counter()
    for x in recs:
        if not x["miss"]:
            continue
        sig = {"invalid": not looks_like_indian_plate(x["truth"]),
               "equal_normalised": x["truth_n"] == x["stored"],
               "other_pass_exact": (x["camera"], x["stored"]) in exact_pass}
        for k, v in sig.items():
            out[k] += v
            out[f"{k}|{x['side']}"] += v
        out["any"] += any(sig.values())
        out[f"any|{x['side']}"] += any(sig.values())
    return dict(out)


def vote_vs_crop(recs: list[dict]) -> dict:
    out = Counter()
    for x in recs:
        if x["side"] not in SENTINEL_SIDE:
            continue
        right = x["crop_read"] == x["truth_n"]
        out["crop right" if right else "crop same as stored" if x["crop_read"] == x["stored"] else "crop wrong too"] += 1
        out["stored 9, reading 10"] += len(x["stored"]) == 9 and len(x["truth_n"]) == 10
        out["crop read has the dropped-digit shape"] += bool(SHORT.match(x["crop_raw"]))
    return dict(out)


# ---------------------------------------------------------------------------------------------------------- report

def pct(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n:.0%})" if n else "0/0"


def markdown(recs: list[dict], res: dict) -> str:
    n, misses = len(recs), [x for x in recs if x["miss"]]
    side = Counter(x["side"] for x in misses)
    cause = Counter((x["side"], x["cause"]) for x in misses)
    sb, so = res["extra"]["short_blind"], res["extra"]["short_own"]
    mono = sorted(c for c, v in res["extra"]["mono"].items() if v)
    L = ["# Blind-checked sandbox plates: why the misses missed", "",
         f"Generated {res['generated']} by `bench/blind_errors.py` (read-only; nothing re-read or tuned). Set: "
         f"`sandbox-blind-v1`, {n} stored sandbox plates a team member read blind on the Plate review page "
         f"(`ocr_baseline_blind.md`): {n - len(misses)} exact, {len(misses)} misses "
         f"({sum(x['verdict'] == 'one_off' for x in misses)} one off, {sum(x['verdict'] == 'wrong' for x in misses)} "
         "wrong). A miss is the review page's verdict: the stored read differs from the reviewer's reading. "
         "Counts and rates only: no plate text.", "",
         "**How to read this.** The reviewer's reading is the answer in the headline numbers. The split into *Sentinel* "
         "and *reviewer* misses below comes from `data/ocr-eval/blind-errors/adjudication.csv`, written by our AI coding "
         "assistant from each miss's crop with both readings in view, and from the same vehicle's other passes where "
         "the sandbox loop replayed it. It is not blind and not a person, and the same kind of label overstated "
         "`sandbox-v1`, so it ranks causes; it does not correct the headline number. Only a second blind reviewer can.",
         "", "## 1. Whose reading does the crop support?", "",
         "| Side | Misses | Causes |", "|---|---|---|"]
    for sd, label in (("sentinel", "Sentinel's stored read is wrong"), ("both", "both readings wrong"),
                      ("reviewer", "the reviewer's reading is wrong"), ("unclear", "cannot tell from the crop")):
        cs = "; ".join(f"{c} {k}" for (s_, c), k in sorted(cause.items(), key=lambda kv: -kv[1]) if s_ == sd)
        L.append(f"| {label} | {side[sd]} | {cs} |")
    L += ["", "Causes: " + "; ".join(f"*{k}*: {v}" for k, v in CAUSES.items()) + ".", ""]
    conds = Counter(c.strip() for x in misses if x["side"] in SENTINEL_SIDE for c in x["condition"].split(";") if c)
    L += ["Visible conditions on the Sentinel-side misses (one miss can have two): "
          + "; ".join(f"{c} {k}" for c, k in conds.most_common()) + ".", ""]
    rs = res["reviewer_signals"]
    L += ["Evidence against the reviewer's reading that needs no judgement: "
          f"the reading is not a valid registration as typed on {rs.get('invalid', 0)} misses; it equals the stored read "
          f"once both go through `normalise_plate` on {rs.get('equal_normalised', 0)}; the same stored plate on the same "
          f"camera was judged exact by the same reviewer on another pass of the loop on {rs.get('other_pass_exact', 0)}. "
          f"At least one of these holds on {rs.get('any', 0)} misses: {rs.get('any|reviewer', 0)} of the "
          f"{side['reviewer']} put on the reviewer side, {rs.get('any|sentinel', 0) + rs.get('any|both', 0)} of the "
          f"{side['sentinel'] + side['both']} on the Sentinel side, {rs.get('any|unclear', 0)} of the {side['unclear']} "
          "unclear.", "",
          f"The quoted figure stays {n - len(misses)}/{n}: this split estimates no corrected figure, and only a second "
          "blind reviewer can change the answer key (a correction to the key, not a gain in the product).", ""]
    sr = res["second_reading"]
    if sr:
        h = sr.get("hit", {})
        L += ["**A blind check on the split.** Because the split above was made with both readings in view, the same "
              f"assistant read the {len(misses)} misses again blind: shuffled among {h.get('n', 0)} random hits on "
              "contact sheets that show no reading, verdict or id, typed before the key was opened "
              "(`bench/blind_errors.py --sheets`). Which reading its own matches, after `normalise_plate`:", "",
              "| Split above | Crops | Stored read only | Reviewer's reading only | Both (equal once normalised) | "
              "Neither | Marked unsure |", "|---|---|---|---|---|---|---|"]
        for sd, label in (("sentinel", "Sentinel's stored read is wrong"), ("both", "both readings wrong"),
                          ("reviewer", "the reviewer's reading is wrong"), ("unclear", "cannot tell from the crop"),
                          ("hit", "hits (the control)")):
            c = sr.get(sd, {})
            L.append(f"| {label} | {c.get('n', 0)} | {c.get('stored', 0)} | {c.get('reviewer', 0)} | "
                     f"{c.get('both', 0)} | {c.get('neither', 0)} | {c.get('unsure', 0)} |")
        rv, st = sr.get("reviewer", {}), [sr.get(k, {}) for k in SENTINEL_SIDE]
        rv_ok = rv.get("stored", 0) + rv.get("both", 0)
        st_n = sum(c.get("n", 0) for c in st)
        st_ok = st_n - sum(c.get("stored", 0) + c.get("both", 0) for c in st)
        L += ["", f"On the hits, the reviewer's reading, the stored read and the blind reading agree on {h.get('both', 0)} "
              f"of {h.get('n', 0)}. The blind reading sides with the stored read on {rv_ok} of the {rv.get('n', 0)} "
              f"reviewer-side misses, and differs from the stored read on {st_ok} of the {st_n} Sentinel-side ones"
              + (", so the split holds up when read blind" if rv_ok == rv.get("n", 0) and st_ok == st_n else "")
              + ". It is still one AI reader, so it too corrects nothing: only a person's blind reading can change the "
              "quoted figure.", ""]

    L += ["## 2. What the misses share", "",
          "Medians, and the AUC: the chance that a miss has the lower value when a miss and a hit are drawn at random "
          "(0.5 means no difference; above 0.5, misses tend to be lower). The 95% interval is a bootstrap over groups "
          f"(a vehicle the loop replayed, or crops seconds apart, is one group; {BOOT} draws). *Sentinel-side* compares "
          "the Sentinel-side misses with the hits and leaves the reviewer-side and unclear misses out.", "",
          "| Measure | Hits | All misses | AUC (95%) | Sentinel-side misses | AUC (95%) |", "|---|---|---|---|---|---|"]
    for row in res["numeric"]:
        a, s = row["all misses"], row["Sentinel-side misses"]
        f = row["fmt"]
        ci = lambda b: f"{b[0]:.2f}–{b[1]:.2f}" if b else "n/a"   # noqa: E731
        L.append(f"| {row['label']} | {f.format(a['median_hit'])} | {f.format(a['median_miss'])} | {a['auc']:.2f} "
                 f"({ci(a['boot95'])}) | {f.format(s['median_miss'])} | {s['auc']:.2f} ({ci(s['boot95'])}) |")
    unknown = sum(x["reads"] is None for x in recs)
    L += ["", f"Crop sizes include the worker's pad (15% of the box height on each side). Reads per track come from the "
              f"worker's log line for the sighting ({n - unknown} of {n} found). When three or more reads agree "
              "unanimously, `tracker.py` raises the stored confidence to at least 0.6 + 0.1 per read, so 0.900 exactly "
              "marks a unanimous three-read vote whose best single read was below 0.9.", ""]
    for key, title in CATEGORIES:
        L += [f"**{title}**", "", "| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |",
              "|---|---|---|---|---|---|"]
        for val, c in res["categorical"][key].items():
            L.append(f"| {val} | {c['n']} | {pct(c.get('exact', 0), c['n'])} | {c.get('sentinel', 0)} | "
                     f"{c.get('reviewer', 0)} | {c.get('unclear', 0)} |")
        L.append("")
    L += [f"The 25 Sep evening run's windows span 20:07–23:48 IST, the 26 Sep morning run's 06:51–07:58 IST, both on our "
          "clock (`sandbox_daynight.md`). The sandbox replays fixed recorded clips, each camera's from one time of day "
          "and looping, so both runs replayed the same footage: the split is by run, not by day and night. "
          f"{', '.join(mono) or 'No camera'} sent a monochrome picture in every crop, in both runs, so plate colour "
          "cannot be seen there.", ""]

    L += ["## 3. Which characters went wrong", "",
          "Edits from the reviewer's reading, put through `normalise_plate` (so a look-alike typed where the format "
          "fixes a letter or a digit does not count), to the read. Position is the part of the plate the reading's "
          "character sits in.", ""]
    for name, c in res["confusions"].items():
        L += [f"**{name}** ({c['n']} plates; edits per plate: "
              + ", ".join(f"{'3 or more' if k == 3 else k} {v}" for k, v in sorted(c["per_plate"].items())) + ")", "",
              "| Edit | Position | Count |", "|---|---|---|"]
        for (kind, where), k in sorted(c["kinds"].items(), key=lambda kv: -kv[1]):
            if kind != "sub":
                L.append(f"| character {kind} | {where} | {k} |")
        for (cls, where), k in sorted(c["classes"].items(), key=lambda kv: -kv[1]):
            L.append(f"| {cls} | {where} | {k} |")
        L += ["", "Substitutions, reading > read: " + ", ".join(f"{p} {k}" for p, k in c["pairs"].most_common()) + ".",
              "Lengths, reading > read: " + ", ".join(f"{a}>{b} {k}" for (a, b), k in sorted(c["lengths"].items())
                                                     if a != b) + ".", ""]
    la = res["confusions"]["stored, Sentinel-side misses"]["lookalike"]
    round_ = {name: sum(k for p, k in c["pairs"].items() if set(p.split(">")) <= set("DOQ"))
              for name, c in res["confusions"].items()}
    L += [f"On the Sentinel side, {la.get('with a drop', 0)} of the {sum(la.values())} letter/digit look-alike edits "
          "sit on a plate stored one character short: they are `normalise_plate` turning the second series letter into "
          "a digit after the drop (section 4), not the model mistaking a letter for a digit. Position-by-position repair "
          "already absorbs the classic look-alikes (O/0, D/0, Q/0, B/8, Z/2, S/5) wherever the format fixes the kind of "
          "character; what is left is digit for digit, letter for letter, and dropped characters. In the series, where "
          "any letter may stand, the round letters D, O and Q are still confused with each other: "
          f"{round_['stored, Sentinel-side misses']} on the Sentinel-side stored reads, "
          f"{round_['single-crop re-read, where it is not exact']} on the single-crop re-reads.", ""]

    vc, dr = res["vote_vs_crop"], res["drops"]
    L += ["## 4. Dropped characters", "",
          f"Of the {side['sentinel'] + side['both']} Sentinel-side misses, {vc.get('stored 9, reading 10', 0)} are a "
          "ten-character plate stored as nine. `normalise_plate` then turns the second series letter into the number's "
          "first digit (the reading's letter A becomes a 4, Z a 2, L a 1, B an 8), so the result is a valid "
          "one-letter-series plate and passes `looks_like_indian_plate`: the gate cannot see the loss. "
          f"Re-reading the stored crop alone, over all {side['sentinel'] + side['both']} Sentinel-side misses: right on "
          f"{vc.get('crop right', 0)}, the same wrong read on {vc.get('crop same as stored', 0)}, a different wrong read "
          f"on {vc.get('crop wrong too', 0)}. So the misreads are the model's, not the vote's. On one (cause "
          "*vote-chose-short*) the best single read was right and the track's vote still stored the short read: "
          "`tracker.vote` keeps only reads of the modal length, so two short reads outvote one full one.", "",
          "Where the character went, for ten-character plates read as nine (a repeated character counts at its later "
          "position):", "",
          "| Reads | Plates | Last character | Second-last | Earlier | Drop plus a misread |", "|---|---|---|---|---|---|"]
    for name in ("stored, Sentinel-side misses", "single crop, sandbox-blind-v1", "single crop, ownfeed-v1"):
        c = dr[name]
        L.append(f"| {name} | {sum(c.values())} | {c.get('last', 0)} | {c.get('second-last', 0)} | "
                 f"{c.get('earlier', 0)} | {c.get('drop plus a misread', 0)} |")
    asp = dr["aspect"]
    end = {k: (dr[k].get("last", 0) + dr[k].get("second-last", 0),
               dr[k].get("last", 0) + dr[k].get("second-last", 0) + dr[k].get("earlier", 0)) for k in dr if k != "aspect"}
    s1, s2, o = (end["stored, Sentinel-side misses"], end["single crop, sandbox-blind-v1"],
                 end["single crop, ownfeed-v1"])
    L += ["", f"Of the clean drops (one character gone, nothing else wrong), {s1[0]} of {s1[1]} stored and {s2[0]} of "
          f"{s2[1]} single-crop drops on the sandbox are in the plate's last two positions, against {o[0]} of {o[1]} on "
          "our own feeds (synthetic plates painted on stock footage). The plate box does not explain it: its width "
          f"over height has a median of {asp['one-line stored drops']} on the {asp['n_drops']} one-line stored drops "
          f"against {asp['one-line hits']} on the {asp['n_hits']} one-line hits, so the detector did not stop short on "
          "these plates as a rule. The right end of real plates, as the shipped model reads them, is where characters "
          "are lost. There are too few drops here to say why.", "",
          "The raw read of a dropped digit has a shape no Indian plate has: two series letters followed by three "
          "digits (`AA99AA999`). How often the shipped model's single read has that shape, and how often such a read "
          "is right (from `bench/ocr_ab.py`'s per-crop runs):", "",
          "| Set | Reads | Dropped-digit shape | ...exact | ...passes today's gate |", "|---|---|---|---|---|",
          f"| sandbox-blind-v1 | {sb['reads']} | {sb['short']} | {sb['short_exact']} | {sb['short_pass_gate']} |",
          f"| ownfeed-v1 | {so['reads']} | {so['short']} | {so['short_exact']} | {so['short_pass_gate']} |", "",
          f"Across both, such reads are right on {sb['short_exact'] + so['short_exact']} of {sb['short'] + so['short']} "
          "(a genuine nine-character plate whose first number digit was also misread as a letter). "
          f"On the Sentinel-side misses, the single-crop re-read has this shape on "
          f"{vc.get('crop read has the dropped-digit shape', 0)}.", ""]

    n_s = side["sentinel"] + side["both"]
    confused = sum(k for (s_, c), k in cause.items() if s_ in SENTINEL_SIDE and c in ("digit-misread", "letter-lookalike"))
    short9 = vc.get("stored 9, reading 10", 0)
    shape_hit = vc.get("crop read has the dropped-digit shape", 0)
    low_s = sum(x["conf"] < 0.9 for x in misses if x["side"] in SENTINEL_SIDE)
    low_h = sum(x["conf"] < 0.9 for x in recs if not x["miss"])
    low_all = sum(x["conf"] < 0.9 for x in recs)
    rv_invalid = rs.get("invalid|reviewer", 0)
    unclear_stored = (sr or {}).get("unclear", {}).get("stored", 0)
    rv2 = (sr or {}).get("reviewer", {})
    second = (f"the blind second reading sides with the stored read on {rv2.get('stored', 0) + rv2.get('both', 0)} of "
              "them" if sr else "no blind second reading has been made")
    L += ["## 5. The fixes with the largest expected gain", "",
          f"Ranked by how many of the {len(misses)} misses each could remove. None is measured here, and none may be "
          "tuned on this set (it is test-only); each says how it would be measured.", ""]
    L += [f"1. **Settle the answer key** (measurement, not product; up to {side['reviewer']} of the {len(misses)} "
          f"misses, {side['reviewer'] + unclear_stored} if the unclear one the blind reading gives to the stored read "
          f"goes the same way). The split puts {side['reviewer']} misses on the reviewer, {second}, and "
          f"{rs.get('any|reviewer', 0)} carry a signal that needs no judgement (section 1). Only a person may move the "
          f"quoted {n - len(misses)}/{n}: have a second team member read the {len(misses)} misses blind on the Plate "
          "review page (it records agreement when a sighting has two blind reviews) and freeze the adjudicated answers "
          "as `sandbox-blind-v2` beside v1 (never edit v1). On the review page, normalise the typed reading as the "
          "stored read is normalised before comparing, and warn when it is not a valid registration: that would have "
          f"flagged {rv_invalid} of the {side['reviewer']} at typing time without showing the reviewer Sentinel's read.",
          f"2. **Read Indian plates better** (model; up to {n_s} of the {len(misses)}). The model makes "
          f"{n_s - vc.get('crop right', 0)} of the {n_s} Sentinel-side misreads again on the stored crop alone "
          f"({vc.get('crop same as stored', 0)} identically), and the short reads the vote chose on the last one were "
          f"the model's too, so the model, not the vote, is the main cause: {short9} dropped characters ({s1[0]} of the "
          f"{s1[1]} clean drops in "
          f"the last two positions, section 4), and {confused} confusions of a digit for a digit or a letter for a "
          "letter (section 3), on "
          "yellow commercial plates with a thin typeface, blurred crops and the monochrome camera (section 1). The "
          "shipped model is a global one that lists no Indian region. The Indian-format fine-tune (synthetic plates "
          "from `bench/plategen.py`, never these crops) is the fix, adopted only through `bench/ocr_gates.md`, whose "
          "Gate 1 scores it on this set's crops against the baseline.",
          f"3. **Keep short reads out, and send low-confidence reads to the crop** (product; a few wrong sightings "
          f"removed, and {low_s} of the {n_s} Sentinel-side misses flagged). Reject a raw read of shape `AA99AA999` in "
          "`worker.check_read` (as the not-a-plate rule rejects phone numbers), and choose the vote's length by summed "
          f"confidence rather than by count. The stored crop's re-read has that shape on {shape_hit} of the {short9} "
          "short stored reads (the others were read in a valid shape, which no rule can catch), and on "
          f"{cause[('sentinel', 'vote-chose-short')]} more the vote chose short reads over a right full-length one. "
          "On the per-crop runs the rule drops "
          f"{sb['short'] - sb['short_exact'] + so['short'] - so['short_exact']} wrong reads and "
          f"{sb['short_exact'] + so['short_exact']} right one. A track whose every read was short is then not stored, so "
          "most of these become no sighting rather than an exact one. Until a better model ships, mark alerts and "
          f"search results stored below 0.9, the review page's top band, as 'check the crop': {low_s} of the {n_s} "
          f"Sentinel-side misses are below it, against {low_h} of the {n - len(misses)} hits ({low_all} of {n} "
          "sightings flagged). The capture grade's low-confidence mark is at 0.6, which catches "
          f"{sum(x['conf'] < 0.6 for x in misses if x['side'] in SENTINEL_SIDE)} of them. Confirm both on our own "
          "feeds with `scripts/anpr_eval.py` before shipping.", "",
          "Not recommended from this set: a wider crop. The box is no shorter on the drops (section 4), and stored "
          "crops cannot test it.", ""]

    L += ["## Caveats", "",
          f"- {n} plates in {len({x['group'] for x in recs})} groups, {len({x['camera'] for x in recs})} cameras, one "
          "reviewer. Treat the rates per category as descriptive, and the AUC intervals as the guide to what is signal.",
          "- The Sentinel/reviewer split is our AI assistant's reading of the crops, made with both readings in view. "
          "Its blind re-read (section 1) is a check, not a second reviewer: it is the same AI. A second blind person "
          "is what settles it.",
          "- The blind re-read saw each crop at 150 px high beside a contrast-stretched copy. Where the loop had replayed "
          "a vehicle, its other passes on the sheets were in view too, as they were for the adjudication; the reviewer "
          "saw the review page's own view, one sighting at a time.",
          "- Only stored sightings are here, so plates Sentinel never stored are not analysed.",
          "- Hits are sightings where the reviewer and Sentinel agree; a plate both read the same wrong way would count "
          "as a hit.",
          "- The stored crop is the track's best-confidence read, saved as JPEG 85; the stored read is a vote over the "
          "track's reads, whose raw text is not kept, so the raw shape of the stored read cannot be checked.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="bench/results/blind_errors.md")
    ap.add_argument("--sheets", action="store_true", help="build the blind second reading's sheets and key, then stop")
    ap.add_argument("--hits", type=int, default=15, help="--sheets: hits shuffled in with the misses")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--exclude", default="13000,13001,13002,13003",
                    help="--sheets: sighting ids whose plate text the reader has already seen")
    a = ap.parse_args()
    if a.sheets:
        sheets(a.hits, a.seed, set(a.exclude.split(",")) - {""})
        return 0
    recs, extra = build()
    rng = np.random.default_rng(0)
    res = {"generated": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"), "extra": extra,
           "numeric": numeric(recs, rng), "categorical": categorical(recs), "confusions": confusions(recs),
           "reviewer_signals": reviewer_signals(recs), "vote_vs_crop": vote_vs_crop(recs), "drops": drops(recs),
           "second_reading": second_reading(recs)}
    out = ROOT / a.out
    out.write_text(markdown(recs, res), encoding="utf-8")
    js = {k: v for k, v in res.items() if k != "confusions"}
    js["confusions"] = {name: {"n": c["n"], "per_plate": {str(k): v for k, v in c["per_plate"].items()},
                               "edits": {f"{k[0]}|{k[1]}": v for k, v in c["kinds"].items()},
                               "substitution_classes": {f"{k[0]}|{k[1]}": v for k, v in c["classes"].items()},
                               "pairs": dict(c["pairs"]),
                               "lengths": {f"{k[0]}>{k[1]}": v for k, v in c["lengths"].items()},
                               "lookalike": dict(c["lookalike"])}
                        for name, c in res["confusions"].items()}
    js["sides"] = dict(Counter(x["side"] for x in recs))
    js["causes"] = dict(Counter(f"{x['side']}|{x['cause']}" for x in recs if x["miss"]))
    out.with_suffix(".json").write_text(json.dumps(js, indent=1), encoding="utf-8")
    print(f"{len(recs)} plates, {sum(x['miss'] for x in recs)} misses; sides {dict(Counter(x['side'] for x in recs))}")
    print("wrote", out, "and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
