"""Do the capture grades predict a right read? The grades (services/api/sentinel_api/capture_quality.py) are set
from published size guidance and our own feed's crops, never from the sandbox or the reviews; this checks them
against what they were kept apart from, without changing them.

Two checks, both on stored sightings that have a grade:
  1. Blind reviews of vehicle plates (plate_reviews, mode 'blind', verdict not not_a_plate or unreadable): the
     share read exactly, by grade and by reason. The sandbox cameras (real plates) and our own cameras apart.
  2. Our own cameras against the known plates (bench/review_truth.py's truth: feedsim/cameras.yaml for the
     synthetic clips, feedsim/media/*.plates.json for the plates painted on the stock clips): every graded
     sighting's stored read scored exact, one off or far. On the stock clips an unpainted vehicle carries a real,
     unlabelled plate, so 'far' there includes reads that may be right.

Also the per-camera tiers and recommendations, computed with the report's own SQL and rules (routers/quality.py,
camera_quality.py), so the file shows what the Health page shows for the same window. Read-only.

    PYTHONUTF8=1 uv run --no-sync python bench/quality_validate.py [--since 2026-09-23] [--until ...] \
        [--out bench/results/capture_quality.md]

Counts and rates only: the stored reads are compared in memory; no plate text is printed or written.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from sentinel_api import capture_quality as cq
from sentinel_api.camera_quality import A_WIDTH, MIN_CAPTURES, graded as tier_is_finding, recommendations, tier
from sentinel_api.config import get_settings
from sentinel_api.routers.quality import REASONS as REASONS_SQL
from sentinel_api.routers.quality import REPORT, TIER_ORDER
from sentinel_common import normalise_plate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_truth import nearest, truth  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
SANDBOX = re.compile(r"^CAM[0-9]{2}$")
CLASSES = ("good", "marginal", "poor")
NOT_READ = ("not_a_plate", "unreadable")     # a crop with no plate, or none a person can read, says nothing

GRADED = """SELECT q.sighting_id, q.sighting_ts, c.camera_code, s.plate_norm, s.ocr_conf, q.quality, q.reasons,
                   q.plate_w, q.char_h, q.layout, q.sharpness, q.brightness, q.contrast, q.oblique
            FROM sighting_quality q JOIN cameras c ON c.id = q.camera_id
            JOIN vehicle_sightings s ON s.id = q.sighting_id AND s.event_ts = q.sighting_ts
            WHERE q.sighting_ts >= $1 AND q.sighting_ts <= $2"""
# Sandbox reviews after v1's window, and the second reader's, are left out: sandbox-fresh-v1 and sandbox-blind-v2
# are scored only from their frozen files (bench/sandbox_fresh.py), never pooled with v1 (bench/pipeline_gates.md).
REVIEWS = """SELECT r.sighting_id, r.sighting_ts, r.verdict FROM plate_reviews r
             JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
             WHERE r.mode = 'blind' AND r.sighting_ts >= $1 AND r.sighting_ts <= $2
               AND NOT (c.camera_code ~ '^CAM[0-9]{2}$'
                        AND (r.sighting_ts > '2026-09-26 07:56:00+05:30' OR u.username = 'auditor'))"""


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a rate: small groups here (10 poor sandbox reviews) need it said how wide they are."""
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def rate(k: int, n: int) -> str:
    if not n:
        return "—"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.1f}% ({100 * lo:.0f}–{100 * hi:.0f}%)"


def pct(c: Counter) -> str:
    return f"{c['exact']}/{c['n']} ({100 * c['exact'] / c['n']:.1f}%)" if c["n"] else "—"


def merge(cs: list[Counter]) -> Counter:
    out = Counter()
    for c in cs:
        out.update(c)
    return out


def separation(good: Counter, other: Counter, name: str) -> str:
    """Is good read exactly more often than the other class, and do the 95% intervals clear each other?"""
    if not good["n"]:
        return f"no good captures to compare with {name}"
    pg, po = good["exact"] / good["n"], other["exact"] / other["n"]
    if pg <= po:
        how = "good is **not** read better"
    elif pg - po < 0.02:
        how = "no real difference"
    elif wilson(good["exact"], good["n"])[0] > wilson(other["exact"], other["n"])[1]:
        how = "good is read better and the intervals do not overlap"
    else:
        how = "good is read better but the intervals overlap"
    return f"good {100 * pg:.1f}% exact against {name} {100 * po:.1f}% ({how})"


def image_only(g: dict) -> str:
    """The grade the image measurements alone give: the same rules without the reader's confidence."""
    return cq.classify(g, None)[0]


async def fetch(since: datetime, until: datetime):
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        cams = await conn.fetch(REPORT.format(where="TRUE"), since, until)
        reasons: dict = {}
        for r in await conn.fetch(REASONS_SQL.format(where="TRUE"), since, until):
            reasons.setdefault(r["camera_id"], {})[r["reason"]] = r["n"]
        graded = await conn.fetch(GRADED, since, until)
        reviews = await conn.fetch(REVIEWS, since, until)
    finally:
        await conn.close()
    return cams, reasons, graded, reviews


def camera_rows(cams, reasons) -> list[dict]:
    out = []
    for r in cams:
        row = dict(r)
        row["reasons"] = dict(sorted(reasons.get(row.pop("camera_id"), {}).items(), key=lambda kv: -kv[1]))
        row["tier"], row["tier_reason"] = tier(row)
        row["graded"] = tier_is_finding(row)
        row["recommendations"] = recommendations(row, row["tier"])
        out.append(row)
    out.sort(key=lambda x: (not x["graded"], TIER_ORDER[x["tier"]], -x["captures"], x["camera_code"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", type=parse_ts, default=datetime(2026, 1, 1, tzinfo=IST),
                    help="window start, ISO (IST if no zone); default: everything stored")
    ap.add_argument("--until", type=parse_ts, help="window end; default now")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "capture_quality.md"))
    a = ap.parse_args()
    until = a.until or datetime.now(timezone.utc)
    cams, reasons, graded, reviews = asyncio.run(fetch(a.since, until))
    rows = camera_rows(cams, reasons)
    g_by = {(g["sighting_id"], g["sighting_ts"]): dict(g) for g in graded}
    # The stored measurements must give back the stored grade, or the re-grades below mean nothing.
    drift = sum(1 for g in g_by.values() if cq.classify(g, g["ocr_conf"])[0] != g["quality"])
    known = truth()

    # Blind reviews joined to their grade; each review counts once, as on the Health page.
    blind = defaultdict(Counter)            # (group, key) -> n / exact
    not_plate = Counter()                   # (group, class, verdict) -> reviews typed not a plate
    ungraded = 0
    for r in reviews:
        g = g_by.get((r["sighting_id"], r["sighting_ts"]))
        if g is None:
            ungraded += 1
            continue
        grp = "sandbox" if SANDBOX.match(g["camera_code"]) else "own"
        if r["verdict"] in NOT_READ:
            not_plate[grp, g["quality"], r["verdict"]] += 1
            continue
        ok = r["verdict"] == "exact"
        keys = [("class", g["quality"]), ("image", image_only(g)), ("all", "all")]
        keys += [("reason", x) for x in (g["reasons"] or ["(none)"])]
        for k in keys:
            blind[grp, k]["n"] += 1
            blind[grp, k]["exact"] += ok

    # Own cameras against the known plates.
    tr = defaultdict(Counter)               # (kind, camera or group, class) -> n / exact / one_off / far
    for g in graded:
        cam = g["camera_code"]
        if cam not in known:
            continue
        d = nearest(normalise_plate(g["plate_norm"]), known[cam])
        kind = "stock" if cam.startswith("AMD-TRAF") else "synthetic"
        v = "exact" if d == 0 else "one_off" if d == 1 else "far"
        for key in ((kind, "all", g["quality"]), (kind, "all", "all"), ("camera", cam, g["quality"]),
                    ("camera", cam, "all"), (kind, "image", image_only(g))):
            tr[key]["n"] += 1
            tr[key][v] += 1

    L = ["# Capture quality by camera, checked against the blind reviews", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/quality_validate.py` (read-only), window "
         f"{a.since.astimezone(IST):%Y-%m-%d %H:%M} to {until.astimezone(IST):%Y-%m-%d %H:%M} IST. Grades from "
         "`services/api/sentinel_api/capture_quality.py` (made at ingest and by `scripts/quality_backfill.py`): size "
         "cut-offs from published guidance (`docs/commercial-anpr.md`), blur, light and contrast cut-offs from our own "
         "stock-footage crops (`bench/results/quality_thresholds.md`). Nothing below was used to set them, and the "
         "grades and cut-offs were not changed after seeing it. The per-camera tier rules were changed after the "
         "first run of this file (not-a-plate captures left out, wording; see the end). Counts and rates only; "
         "intervals are 95% (Wilson).", "",
         f"- Graded sightings in the window: {len(graded)} ("
         + ", ".join(f"{q} {sum(1 for g in graded if g['quality'] == q)}" for q in CLASSES) + ").",
         f"- Blind reviews in the window: {len(reviews)}, of which {ungraded} have no grade (no crop)."
         " All blind reviews so far are by one team member. Sandbox reviews of sightings after 26 Sep 07:56 IST, and"
         " the second reader's, are left out: `bench/sandbox_fresh.py` scores them from their frozen sets.",
         f"- Re-grading the stored measurements gives back the stored grade for {len(graded) - drift} of "
         f"{len(graded)} sightings.", "",
         "## By camera", "",
         "Tiers and recommendations as the Health page computes them (`routers/quality.py` SQL, `camera_quality.py` "
         "rules): A at least 60% good and a median plate at least 100 px across, from 20 or more captures; C under "
         "20% good, median characters under 10 px, or no plate read stored; B between. Captures a reviewer marked as "
         "not a plate (either review mode) are left out of the captures, grades and tier. Blind exact counts vehicle "
         "plates only (a crop reviewed as not a plate, or unreadable, is left out and counted apart).", "",
         "| Camera | Tier | Why | Captures | Good / marginal / poor | Median plate px | Median char px | "
         "Main reasons (share of captures) | Blind exact | Not a plate (blind) | Recommendations |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    not_plate_cam = Counter()
    for r in reviews:
        g = g_by.get((r["sighting_id"], r["sighting_ts"]))
        if g is not None and r["verdict"] == "not_a_plate":
            not_plate_cam[g["camera_code"]] += 1
    empty = []
    for row in rows:
        n = row["captures"]
        if not n and not row["reviewed_blind"] and not row.get("not_plates"):
            empty.append(row)
            continue
        main = ", ".join(f"{k} {100 * v / n:.0f}%" for k, v in list(row["reasons"].items())[:4]) if n else "—"
        recs = "; ".join(f"*{x['kind']}*: {x['text']}" for x in row["recommendations"]) or "—"
        blind_s = f"{row['blind_exact']}/{row['reviewed_blind']}" if row["reviewed_blind"] else "—"
        L.append(f"| {row['camera_code']} | {row['tier']} | {row['tier_reason']} | {n} | "
                 f"{row['good']} / {row['marginal']} / {row['poor']} | {row['median_plate_w'] or '—'} | "
                 f"{row['median_char_h'] or '—'} | {main} | {blind_s} | {not_plate_cam.get(row['camera_code'], 0) or '—'} "
                 f"| {recs} |")
    if empty:
        why = defaultdict(list)
        for r in empty:
            why[(r["tier"] if r["graded"] else "not graded") + ", " + r["tier_reason"]].append(r["camera_code"])
        L += ["", f"{len(empty)} more cameras were enabled or analysed in the window with no graded capture (no plate "
              "read stored with a crop), config advice only: "
              + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(why.items(), key=lambda kv: -len(kv[1]))) + "."]

    L += ["", "## Do the grades predict a right read?", "",
          "### Blind reviews of vehicle plates, by grade", "",
          "Sandbox: the organisers' cameras, real Gujarat plates (in practice CAM06 and CAM07, and one read on CAM12). "
          "Own: our simulator's cameras (synthetic clips, and stock footage with synthetic plates painted on). "
          "*Image only* re-grades the same crops without the reader's confidence (reason `low_confidence`), so it "
          "shows what the size, blur, light and angle measurements say by themselves.", "",
          "| Cameras | Grade | Exact (95% interval) | Image only: exact |", "|---|---|---|---|"]
    for grp in ("sandbox", "own"):
        for q in CLASSES:
            c, im = blind[grp, ("class", q)], blind[grp, ("image", q)]
            L.append(f"| {grp} | {q} | {rate(c['exact'], c['n'])} | {rate(im['exact'], im['n'])} |")
        c = blind[grp, ("all", "all")]
        L.append(f"| {grp} | **all** | {rate(c['exact'], c['n'])} | |")

    L += ["", "### Blind reviews by reason", "",
          "A capture can carry several reasons, so the rows overlap; `(none)` is a capture graded good.", "",
          "| Reason | Sandbox exact | Own exact |", "|---|---|---|"]
    for reason in ("(none)", *cq.REASONS):
        s, o = blind["sandbox", ("reason", reason)], blind["own", ("reason", reason)]
        if s["n"] or o["n"]:
            L.append(f"| {reason} | {rate(s['exact'], s['n'])} | {rate(o['exact'], o['n'])} |")

    L += ["", "### Our own cameras against the known plates", "",
          "Every graded sighting on a camera whose plates are known, the stored read scored against them: exact, one "
          "character off, or further (far). Synthetic clips: every plate in view is known, so far is wrong. Stock "
          "clips: only the painted plates are known and other vehicles carry real plates, so far there includes reads "
          "that may be right and the exact rate is a floor.", "",
          "| Clips | Grade | Sightings | Exact (95% interval) | One off | Far | Image only: exact |",
          "|---|---|---|---|---|---|---|"]
    for kind in ("synthetic", "stock"):
        for q in (*CLASSES, "all"):
            c, im = tr[kind, "all", q], tr[kind, "image", q] if q != "all" else Counter()
            L.append(f"| {kind} | {q if q != 'all' else '**all**'} | {c['n']} | {rate(c['exact'], c['n'])} | "
                     f"{c['one_off']} | {c['far']} | {rate(im['exact'], im['n']) if q != 'all' else ''} |")
    L += ["", "Within each camera (one scene, so the grade is not standing in for the camera):", "",
          "| Camera | Good: exact | Marginal: exact | Poor: exact |", "|---|---|---|---|"]
    for cam in sorted({k[1] for k in tr if k[0] == "camera"}):
        L.append(f"| {cam} | " + " | ".join(rate(tr['camera', cam, q]['exact'], tr['camera', cam, q]['n'])
                                           for q in CLASSES) + " |")

    L += ["", "### Crops that were not vehicle plates", "",
          "Blind reviews typed as not a plate (or unreadable), by the grade their crop got. The grade measures the "
          "image, not what is in it.", "", "| Cameras | Grade | Not a plate | Unreadable |", "|---|---|---|---|"]
    for grp in ("sandbox", "own"):
        for q in CLASSES:
            a_, b_ = not_plate[grp, q, "not_a_plate"], not_plate[grp, q, "unreadable"]
            if a_ or b_:
                L.append(f"| {grp} | {q} | {a_} | {b_} |")

    # Plain verdict, computed: is good read better than the classes below it, and do the intervals clear?
    L += ["", "## What this shows", ""]
    for label, sets in (("Sandbox blind reviews", [blind["sandbox", ("class", q)] for q in CLASSES]),
                        ("Own blind reviews", [blind["own", ("class", q)] for q in CLASSES]),
                        ("Synthetic clips against the known plates", [tr["synthetic", "all", q] for q in CLASSES]),
                        ("Stock clips against the known plates", [tr["stock", "all", q] for q in CLASSES])):
        L.append(f"- {label}: " + "; ".join(separation(sets[0], other, name)
                                            for other, name in ((sets[2], "poor"), (merge(sets[1:]), "marginal or poor"))
                                            if other["n"]) + ".")

    lc_s, lc_o = blind["sandbox", ("reason", "low_confidence")], blind["own", ("reason", "low_confidence")]
    small_s, none_s = blind["sandbox", ("reason", "small")], blind["sandbox", ("reason", "(none)")]
    st = {q: tr["stock", "all", q] for q in CLASSES}
    stock_poor = [g for g in graded if g["camera_code"].startswith("AMD-TRAF") and g["quality"] == "poor"]
    stock_small = sum("too_small" in (g["reasons"] or []) for g in stock_poor)
    syn = tr["synthetic", "all", "all"]
    L += ["", "In plain words:", "",
          f"1. **On the blind reviews the grades do not separate readable from unreadable.** A poor capture was read "
          f"exactly as often as a good one (sandbox poor {pct(blind['sandbox', ('class', 'poor')])} against good "
          f"{pct(blind['sandbox', ('class', 'good')])}; own poor {pct(blind['own', ('class', 'poor')])} against good "
          f"{pct(blind['own', ('class', 'good')])}). The one strong signal is the reader's own confidence: captures "
          f"with `low_confidence` were exact {pct(lc_s)} on the sandbox and {pct(lc_o)} on our own cameras. `small` on "
          f"the sandbox ({pct(small_s)} against {pct(none_s)} for captures with no reason) points the right way, but "
          "the intervals overlap.",
          f"2. **On our stock clips, with thousands of sightings, the grades order the error rate but poor is not "
          f"unreadable**: good {pct(st['good'])}, marginal {pct(st['marginal'])}, poor {pct(st['poor'])} exact against "
          "the painted plates (a floor), and the same order inside AMD-TRAF-002 alone. Poor there is "
          f"`too_small` ({stock_small} of {len(stock_poor)}) by the published size guidance, which is written for "
          "commercial readers; our reader still reads "
          "most of those painted, pure black-on-white plates. These are also the clips the blur and light cut-offs "
          "were measured on (from how reads survive degrading, not from the known plates), so they are not an "
          "independent test.",
          f"3. **Reader errors the image cannot show.** On the synthetic clips "
          f"{tr['synthetic', 'image', 'good']['n']} of {syn['n']} captures are good by the image alone, yet "
          f"{pct(syn)} of the stored reads are exact. That is the reader, not the camera, and the camera report "
          "says so with its model recommendation (good crops, blind reads under 90% exact).",
          "4. **Grades exist only for reads the worker stored.** A plate too small or blurred to read at all leaves no "
          "sighting, so it never gets a poor grade; the grade cannot show misses, and capture on real plates is "
          "unmeasured. Where a poor camera shows is in fewer plates per 1,000 frames, not in more wrong reads."]
    hoard = [r for r in rows if r["captures"] and not_plate_cam.get(r["camera_code"], 0) >= r["captures"] / 2]
    if hoard:
        L.append("5. **The grade measures the image, not what is in it.** "
                 + "; ".join(f"{r['camera_code']}: {not_plate_cam[r['camera_code']]} of its {r['captures']} captures "
                             f"were reviewed as not a plate, yet it is tier {r['tier']}"
                             + (f" with the advice \"{r['recommendations'][0]['text']}\"" if r["recommendations"] else "")
                             for r in hoard) + ".")

    # Each check below looks at what the report says now, so a fix that has been made drops out of the list.
    zoom = [r for r in rows if (r["median_plate_w"] or 0) >= A_WIDTH
            and any(x["text"].startswith("Zoom") and "% of captures" not in x["text"] for x in r["recommendations"])]
    thin_c = [r for r in rows if r["tier"] == "C" and 0 < r["captures"] < MIN_CAPTURES]
    analysed = [r for r in rows if r["graded"]]
    viable_c = [r["camera_code"] for r in analysed if r["tier"] == "C" and r["anpr_viable"]
                and not any("ANPR-viable" in x["text"] for x in r["recommendations"])]
    seen_wording = [r["camera_code"] for r in rows if r["tier_reason"] == "no plates seen"]
    unanalysed = [r["camera_code"] for r in rows if not r["captures"] and not r["frames_analysed"] and r["graded"]]
    fixed = [r for r in rows if r.get("not_plates") and not r["captures"]]
    c_reads = [(r["camera_code"], tr["camera", r["camera_code"], "all"]) for r in rows
               if r["tier"] == "C" and tr["camera", r["camera_code"], "all"]["n"]]
    L += ["", "## Proposed fixes (not applied)", "",
          "None of these is made here: the grades stay as set, and any change should be decided first and then checked "
          "on blind reviews made after it, not on the ones above.", ""]
    n = 1
    if hoard:
        L.append(f"{n}. **Leave not-a-plate captures out of the tier.** Count a capture only if no review marked it "
                 "not a plate (a join to plate_reviews in the report's grade query), and give a camera whose reviewed "
                 "captures are mostly not plates tier C, \"captures are not plates\". Affects "
                 + ", ".join(r["camera_code"] for r in hoard) + ".")
        n += 1
    L.append(f"{n}. **Count the reader's confidence as a problem, not only a note.** Today `low_confidence` alone makes "
             "a capture marginal and never poor; it is the only reason whose captures were read clearly worse (95% "
             "intervals clear of the good captures') in both review sets. "
             "Making it count towards poor like an image problem is a structural change to check on the next blind "
             "batch (a pre-registered gate, as in `bench/*_gates.md`), since this batch suggested it.")
    n += 1
    L.append(f"{n}. **Set our reader's own size floor on our own feed.** Keep the published sizes for the camera "
             "advice (they are what a commercial reader needs), but decide what makes a capture poor from a downscale "
             "sweep on the stock crops, as `bench/quality_thresholds.py` does for blur and light: shrink read crops "
             "step by step and find where the reads stop surviving. Not from the reviews above.")
    n += 1
    if c_reads:
        L.append(f"{n}. **Tier C is not proof a camera cannot read plates.** "
                 + "; ".join(f"{cam} is C on size alone, yet {pct(c)} of its stored reads match a painted plate "
                             "exactly" for cam, c in c_reads)
                 + ". Painted plates are cleaner than real ones at the same size, so this does not show real plates "
                 "would read there; it shows size alone cannot settle the tier. Before calling a camera counts-only, "
                 "the tier should weigh how many passing plates it reads "
                 "(capture), which needs vehicles counted against plates read on the same frames.")
        n += 1
    if zoom:
        L.append(f"{n}. **Say why the zoom advice fires.** It fires on the share of small plates, but quotes the "
                 "median, which reads as a contradiction when the median is inside 100-150 px ("
                 + ", ".join(f"{r['camera_code']} {r['median_plate_w']} px" for r in zoom)
                 + "). Quote the share instead, e.g. \"N% of plates are under 100 px across\".")
        n += 1
    if thin_c or viable_c or unanalysed or seen_wording:
        parts = []
        if thin_c:
            parts.append("tier C is given on as little as one capture (" + ", ".join(
                f"{r['camera_code']} {r['captures']}" for r in thin_c) + f"): ask for {MIN_CAPTURES} captures before "
                "grading C on grades, as A already does")
        if seen_wording:
            parts.append("\"no plates seen\" should read \"no plate read\" (the detector may have seen plates the "
                         "reader dropped) (" + ", ".join(seen_wording) + ")")
        if viable_c:
            parts.append("a C camera the registry marks ANPR-viable should say so in its advice ("
                         + ", ".join(viable_c) + ")")
        if unanalysed:
            parts.append("a camera with no frames analysed and no capture in the window gets tier C next to \"not "
                         "analysed in this window\": show it as not graded instead (" + ", ".join(unanalysed) + ")")
        L.append(f"{n}. **Small wording and evidence rules.** " + "; ".join(parts) + ".")

    L += ["", "## Applied since the first run (26 Sep 2026)", "",
          "Report rules only (`routers/quality.py`, `camera_quality.py`); the grades and cut-offs are unchanged, so "
          "every rate above is the same as before.", "",
          "- Captures reviewed as not a plate are left out of a camera's captures, grades and tier, and counted apart ("
          + (", ".join(f"{r['camera_code']}: {r['not_plates']}, now tier {r['tier']}, \"{r['tier_reason']}\""
                       for r in fixed) or "none in this window") + ").",
          "- The zoom advice quotes the share of captures under size next to the median.",
          "- A camera with nothing graded in the window (not analysed, or reads with no crop) is marked not graded "
          "(`graded: false`) and gets no counts-only advice; the page shows it without a tier.",
          "- \"no plates seen\" reads \"no plate read\"; a C camera the registry marks ANPR-viable says so; a C "
          "given on grades says how many captures it rests on.",
          "- Not applied: C on fewer than 20 captures (a camera analysed for hours that stored one plate is "
          "counts-only in practice), and the proposed fixes above."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## What this shows"):]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
