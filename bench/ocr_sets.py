"""Freeze the plate-OCR test sets that bench/ocr_ab.py scores. Test only: nothing here is ever trained on.

    uv run --no-sync python bench/ocr_sets.py [sandbox] [ownfeed] [blind]    # none named: every set not yet frozen
    uv run --no-sync python bench/ocr_sets.py fresh|blindv2 [--dry-run]      # frozen only when named
    uv run --no-sync python bench/ocr_sets.py sheet fresh|blindv2            # adjudication sheet, before the freeze

sandbox-v1        real sandbox crops our AI coding assistant labelled, not blind (data/gov-sandbox/eye/labels.csv: exact,
                  one_off, wrong)
reject-v1         sandbox crops labelled not_a_plate (a good model keeps these out of the gate)
ownfeed-v1        our AMD-TRAF-001/002 crops, labelled by matching the stored read to the painted plate
sandbox-blind-v1  real sandbox plates Sentinel stored, read blind by a team member on the Plate review page (table
                  plate_reviews): they typed the plate without seeing Sentinel's read, and their reading is the answer
sandbox-fresh-v1  sandbox sightings stored after v1, read blind by reader 1 (admin) and/or reader 2 (auditor); reviews
                  made after its freeze belong to sandbox-fresh-v2, a separate freeze this script does not build yet
sandbox-blind-v2  v1's 144 sightings with reader 2's blind reading beside reader 1's (v1 itself is never edited)

The last two follow bench/pipeline_gates.md, "Real labelled data". Freeze procedure: (1) `fresh --dry-run` and
`blindv2 --dry-run` print structural counts (rows, readers, disagreements, left out) and write nothing; (2) `sheet
fresh` (or blindv2) writes sheet.html and an adjudication.csv template under data/ocr-eval/<set>/; the two readers
settle each disagreement from the crop and their two readings only and type the answer into adjudication.csv; (3) by
27 Sep 10:00 IST, `fresh` and `blindv2` freeze once (manifest.csv, left_out.csv, freeze.json); (4) bench/sandbox_fresh.py
reports from the frozen files only.

Crops are copied under neutral names (a plain demo_prep.py deletes data/crops, and the worker names a crop after its
plate). Manifests hold plate text, real ones included, so they stay in data/ (gitignored); this script prints counts only.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from sentinel_api.review import reading, verdict as grade
from sentinel_common import normalise_plate

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "gov-sandbox" / "eye" / "labels.csv"
OUT = ROOT / "data" / "ocr-eval"
IST = timezone(timedelta(hours=5, minutes=30))
OWN = ("AMD-TRAF-001", "AMD-TRAF-002")
BLIND_REVIEWER = "admin"     # the account the team member used for the blind checks of the sandbox sightings


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def components(n: int, linked) -> list[int]:
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if linked(i, j):
                parent[find(i)] = find(j)
    names: dict[int, str] = {}
    return [names.setdefault(find(i), f"g{len(names) + 1:03d}") for i in range(n)]


def copy(src: Path, dst: Path) -> tuple[str, str, int, int]:
    """Copy a crop; return its layout (two-line when tall), the copy's sha256, and its width and height."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    data = dst.read_bytes()
    h, w = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape[:2]
    return ("two-line" if h / w > 0.45 else "one-line"), hashlib.sha256(data).hexdigest(), w, h


def frozen(name: str) -> bool:
    """A set is built once: rebuilding would quietly change the test. A new version gets a new name."""
    if (OUT / name / "manifest.csv").exists():
        print(f"{name}: already frozen, kept")
        return True
    return False


def write(name: str, rows: list[dict]) -> None:
    with open(OUT / name / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} crops, {len({r['group'] for r in rows})} groups, "
          f"layouts {dict(Counter(r['layout'] for r in rows))}")


def same_vehicle(rows: list[dict], t: list[datetime]):
    """One vehicle seen twice (the sandbox replays its footage on a loop), or a near-identical plate, must not be
    counted twice: identical or one edit apart, or the same camera within 10 s."""
    def linked(i: int, j: int) -> bool:
        a, b = rows[i], rows[j]
        return (lev(a["true_plate"], b["true_plate"]) <= 1 or
                (a["camera"] == b["camera"] and abs((t[i] - t[j]).total_seconds()) <= 10))
    return linked


def sandbox() -> None:
    with open(LABELS, encoding="utf-8") as f:
        labels = list(csv.DictReader(f))
    for name, keep in (("sandbox-v1", ("exact", "one_off", "wrong")), ("reject-v1", ("not_a_plate",))):
        if frozen(name):
            continue
        rows = []
        for r in labels:
            if r["verdict"] not in keep:
                continue
            truth = r["true_plate"].strip() or (r["stored"] if r["verdict"] == "exact" else "")
            if name == "sandbox-v1" and not truth:
                continue
            layout, sha, _, _ = copy(ROOT / "data" / r["crop"].lstrip("/"), OUT / name / f"{r['id']}.jpg")
            rows.append({"id": r["id"], "camera": r["camera"], "event_ist": r["event_ist"],
                         "true_plate": truth if name == "sandbox-v1" else "", "stored": r["stored"],
                         "verdict": r["verdict"], "group": "", "layout": layout, "sha256": sha})
        t = [datetime.fromisoformat(r["event_ist"]) for r in rows]
        if name == "reject-v1":
            linked = lambda i, j: rows[i]["stored"] == rows[j]["stored"]   # noqa: E731
        else:
            linked = same_vehicle(rows, t)
        for r, g in zip(rows, components(len(rows), linked)):
            r["group"] = g
        write(name, rows)


def ownfeed() -> None:
    if frozen("ownfeed-v1"):
        return
    rows, skipped = [], Counter()
    for code in OWN:
        painted = [p["plate"] for p in json.loads((ROOT / "feedsim" / "media" / f"{code}.plates.json")
                                                  .read_text(encoding="utf-8"))["plates"]]
        for src in sorted((ROOT / "data" / "crops" / code).glob("*.jpg")):
            unix, _, read = src.stem.partition("_")
            near = [(lev(read, p), p) for p in set(painted)]
            near = [x for x in near if x[0] <= 2]
            if len(near) != 1:
                skipped["no painted plate within 2 edits" if not near else "ambiguous"] += 1
                continue
            rid = f"{code}-{len(rows) + 1:05d}"
            layout, sha, _, _ = copy(src, OUT / "ownfeed-v1" / f"{rid}.jpg")
            rows.append({"id": rid, "camera": code,
                         "event_ist": f"{datetime.fromtimestamp(int(unix), IST):%Y-%m-%d %H:%M:%S}",
                         "true_plate": near[0][1], "stored": read, "edits": near[0][0], "group": near[0][1],
                         "layout": layout, "sha256": sha})
    names: dict[str, str] = {}
    for r in rows:
        r["group"] = names.setdefault(r["group"], f"g{len(names) + 1:03d}")
    write("ownfeed-v1", rows)
    print(f"ownfeed-v1: skipped {dict(skipped)}; stored read vs painted edits {dict(Counter(r['edits'] for r in rows))}")


def blind_reviews() -> list:
    """Blind reviews of sandbox sightings (camera codes CAM01..), with the sighting's crop. Read-only."""
    import asyncio

    import asyncpg

    from sentinel_api.config import get_settings

    async def fetch():
        conn = await asyncpg.connect(get_settings().pg_dsn)
        try:
            return await conn.fetch(
                """SELECT r.sighting_id, r.sighting_ts, c.camera_code, r.seen, r.verdict, r.stored_plate, r.ocr_conf,
                          s.crop_path, s.plate_norm
                   FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
                   LEFT JOIN vehicle_sightings s ON s.id = r.sighting_id AND s.event_ts = r.sighting_ts
                   WHERE r.mode = 'blind' AND u.username = $1 AND c.camera_code ~ '^CAM[0-9]{2}$'
                   ORDER BY r.sighting_ts, r.sighting_id""", BLIND_REVIEWER)
        finally:
            await conn.close()
    return asyncio.run(fetch())


def sandbox_blind() -> None:
    """The reviewer typed each plate without seeing Sentinel's read, and the page graded the stored read against it
    (exact, one_off, wrong). Their reading is the answer here: on our own plates, where the truth is known, the same
    reviewer was right 222 times in 226 (bench/results/review_truth.md). Vehicle plates only: the hoarding's phone
    number (not_a_plate) and anything unreadable stay out."""
    name = "sandbox-blind-v1"
    if frozen(name):
        return
    rows, t, skipped, notes = [], [], Counter(), Counter()
    for r in blind_reviews():
        if r["verdict"] not in ("exact", "one_off", "wrong"):
            skipped[r["verdict"]] += 1
            continue
        src = ROOT / "data" / (r["crop_path"] or "").lstrip("/")
        if not r["crop_path"] or not src.is_file():
            skipped["crop missing"] += 1
            continue
        layout, sha, w, h = copy(src, OUT / name / f"{r['sighting_id']}.jpg")
        truth = "".join(r["seen"].split()).upper()   # the page already kept letters and digits; spaces and case only
        notes["crop shared with another sighting"] += sum(x["crop"] == r["crop_path"] for x in rows) > 0
        notes["stored read changed since the review"] += r["plate_norm"] != r["stored_plate"]
        notes["true plate that normalise_plate would change"] += normalise_plate(truth) != truth
        rows.append({"id": str(r["sighting_id"]), "camera": r["camera_code"],
                     "event_ist": f"{r['sighting_ts'].astimezone(IST):%Y-%m-%d %H:%M:%S}", "true_plate": truth,
                     "stored": r["stored_plate"], "verdict": r["verdict"],
                     "ocr_conf": "" if r["ocr_conf"] is None else f"{r['ocr_conf']:.3f}", "group": "",
                     "layout": layout, "width_px": w, "height_px": h, "sha256": sha, "crop": r["crop_path"]})
        t.append(r["sighting_ts"])
    for r, g in zip(rows, components(len(rows), same_vehicle(rows, t))):
        r["group"] = g
    for r in rows:
        del r["crop"]    # the source name carries the plate; the copy's name does not
    write(name, rows)
    try:
        with open(OUT / "sandbox-v1" / "manifest.csv", encoding="utf-8") as f:
            earlier = {x["sha256"] for x in csv.DictReader(f)}
    except FileNotFoundError:
        earlier = set()
    print(f"{name}: cameras {dict(Counter(r['camera'] for r in rows))}; verdicts {dict(Counter(r['verdict'] for r in rows))}; "
          f"left out {dict(skipped)}; {dict(notes)}; crops also in sandbox-v1: {sum(r['sha256'] in earlier for r in rows)}")


# sandbox-fresh-v1 and sandbox-blind-v2 (bench/pipeline_gates.md, "Real labelled data").
READERS = {"admin": "1", "auditor": "2"}   # reader 1 read v1; reader 2 is a different person
SANDBOX = re.compile(r"^CAM[0-9]{2}$")
V1_WINDOW = (datetime(2026, 9, 25, 21, 0, tzinfo=IST), datetime(2026, 9, 26, 7, 56, tzinfo=IST))
V1_FROZEN = datetime(2026, 9, 26, 13, 28, 7, tzinfo=IST)     # sandbox-blind-v1/manifest.csv was written
FRESH_AFTER = datetime(2026, 9, 26, 7, 55, 27, tzinfo=IST)   # v1's last sighting (07:55:27.55; it stays v1's)
FRESH_BY = datetime(2026, 9, 27, 10, 0, tzinfo=IST)          # the fresh freeze: later reviews go to sandbox-fresh-v2
HEADLINE_BY = datetime(2026, 9, 27, 12, 0, tzinfo=IST)       # v2 can be the headline only if frozen by then
CAPTURE_BUILD = ("the tree committed as e18331a plus the uncommitted stream.py reconnect backoff (the worker as it "
                 "stood on the afternoon of 26 Sep, when the CAM06/CAM07 capture ran)")
ON_REQUEST = {"fresh": "sandbox-fresh-v1", "blindv2": "sandbox-blind-v2"}   # never frozen by the no-argument default
ANSWERED = ("single", "agreed", "settled")
UNSETTLED = "unsettled disagreement"
FIELDS = ["id", "camera", "event_ist", "true_plate", "stored", "verdict", "ocr_conf", "conf_band", "group", "vehicle",
          "readers", "answer_by", "reading_1", "reading_2", "layout", "width_px", "height_px", "sha256"]
LEFT_FIELDS = ["id", "camera", "event_ist", "reason", "readers", "ocr_conf", "conf_band", "group", "vehicle"]


def now() -> datetime:
    return datetime.now(IST)


def git_head() -> tuple[str, int]:
    """HEAD and how many paths differ from it: the freeze records what the tooling ran on."""
    def run(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()
    try:
        return run("rev-parse", "--short", "HEAD") or "unknown", len(run("status", "--porcelain").splitlines())
    except OSError:
        return "unknown", 0


def fetch(since: datetime, until: datetime | None) -> tuple[list[dict], list[int]]:
    """Every review of a sandbox sighting (any account, either mode) with the sighting's crop, and the ids of sandbox
    sightings with a crop after `since` (up to `until`). Read-only."""
    import asyncio

    import asyncpg

    from sentinel_api.config import get_settings

    async def run():
        conn = await asyncpg.connect(get_settings().pg_dsn)
        try:
            revs = await conn.fetch(
                """SELECT r.id, r.sighting_id, r.sighting_ts, r.created_at, r.mode, u.username, c.camera_code, r.seen,
                          r.stored_plate, r.ocr_conf, s.crop_path, s.plate_norm
                   FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
                   LEFT JOIN vehicle_sightings s ON s.id = r.sighting_id AND s.event_ts = r.sighting_ts
                   WHERE c.camera_code ~ '^CAM[0-9]{2}$' ORDER BY r.created_at, r.id""")
            ids = await conn.fetch(
                """SELECT s.id FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
                   WHERE c.camera_code ~ '^CAM[0-9]{2}$' AND s.crop_path IS NOT NULL AND s.event_ts > $1
                         AND ($2::timestamptz IS NULL OR s.event_ts <= $2)""", since, until)
            return [dict(r) for r in revs], [r["id"] for r in ids]
        finally:
            await conn.close()
    return asyncio.run(run())


def v1_source(revs: list[dict]) -> set[int]:
    """The 144 sightings sandbox-blind-v1 came from: reader 1's blind reviews in v1's window, made before it froze."""
    return {r["sighting_id"] for r in revs if r["username"] == BLIND_REVIEWER and r["mode"] == "blind"
            and V1_WINDOW[0] <= r["sighting_ts"] <= V1_WINDOW[1] and r["created_at"] <= V1_FROZEN}


def readers(revs: list[dict], cut: datetime) -> tuple[dict[int, dict], Counter]:
    """Each sighting's blind review by reader 1 and by reader 2, up to `cut`. A reader's later blind review of the same
    sighting was not blind (the page had shown them Sentinel's read), so the earliest counts."""
    by: dict[int, dict] = {}
    ignored = Counter()
    for r in sorted(revs, key=lambda r: (r["created_at"], r["id"])):
        who = READERS.get(r["username"])
        if who is None:
            ignored["review by another account"] += 1
        elif r["mode"] != "blind":
            ignored["verify-mode review by a reader"] += 1
        elif r["created_at"] > cut:
            ignored["made after the freeze time"] += 1
        elif who in by.get(r["sighting_id"], {}):
            ignored["later blind review by the same reader"] += 1
        else:
            by.setdefault(r["sighting_id"], {})[who] = r
    return by, ignored


def kind(typed: str) -> str:
    """The server's reading of what was typed: 'unreadable' ('?'), 'not_a_plate' ('-' or no letters), or 'plate'."""
    v = grade(typed, "")
    return v if v in ("unreadable", "not_a_plate") else "plate"


def settle(one: str | None, two: str | None, adjudicated: str | None) -> tuple[str, str]:
    """(how the answer was reached, the answer), or (why the row is left out, ""). Readings compare upper-cased with
    spaces and punctuation removed, as the review page stores them."""
    typed = [reading(x) for x in (one, two) if x is not None]
    kinds = {kind(x) for x in typed}
    if "not_a_plate" in kinds:
        return "not a plate", ""
    if "unreadable" in kinds:
        return "unreadable", ""
    if len(typed) == 1:
        return "single", typed[0]
    if typed[0] == typed[1]:
        return "agreed", typed[0]
    if not adjudicated:
        return UNSETTLED, ""
    if kind(reading(adjudicated)) != "plate":
        return "settled as not a plate or unreadable", ""
    return "settled", reading(adjudicated)


def adjudication(name: str) -> dict[int, str]:
    """data/ocr-eval/<set>/adjudication.csv (sighting_id, answer, note): the answers the two readers agreed from the
    crop and their two readings. An empty answer is not settled. utf-8-sig: a spreadsheet may add a BOM. It is the one
    file people edit by hand, so a line that does not parse stops the run (a misread file would quietly turn answers
    into exclusions in a set that cannot be edited), and no message echoes a cell: it may hold a plate."""
    path = OUT / name / "adjudication.csv"
    if not path.exists():
        return {}
    out: dict[int, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        if not {"sighting_id", "answer"} <= {(x or "").strip() for x in rd.fieldnames or ()}:
            raise SystemExit(f"{path}: the first line must name the columns sighting_id,answer,note, separated by commas")
        rd.fieldnames = [(x or "").strip() for x in rd.fieldnames]
        for r in rd:
            if any((x or "").strip() for x in r.get(None) or ()):
                raise SystemExit(f"{path}: line {rd.line_num} has more cells than the header (a comma in a note? "
                                 "put the note in double quotes)")
            sid, answer = (r.get("sighting_id") or "").strip(), (r.get("answer") or "").strip()
            if not sid:
                if answer:
                    raise SystemExit(f"{path}: line {rd.line_num} has an answer but no sighting_id")
                continue
            if not sid.isdigit():
                raise SystemExit(f"{path}: line {rd.line_num}: sighting_id is not a number (columns shifted?)")
            if int(sid) in out:
                raise SystemExit(f"{path}: sighting {int(sid)} is listed twice; keep one line per sighting")
            out[int(sid)] = answer
    return out


def band(conf: float | None) -> str:
    """The review page's band: ocr_conf is REAL, and the page compares it with real '0.9' (routers/reviews.py)."""
    if conf is None:
        return ""
    return ">=0.9" if np.float32(conf) >= np.float32(0.9) else "<0.9"


def group_rows(rows: list[dict], v1: list[dict]) -> None:
    """Groups are same_vehicle over the rows with an answer and v1's rows, exactly; a row linked to a v1 row is a seen
    vehicle. A left-out row (an unsettled disagreement, say) has no answer and is not in the set: it joins the first
    group one of its plate readings, or its camera within 10 s, links it to (or a group of its own), and never joins
    two groups, so it cannot change another row's group or class. A row nobody typed a plate for gets no group."""
    known = [r for r in rows if r["answer_by"] in ANSWERED]
    items = [{"true_plate": r["true_plate"], "camera": r["camera"]} for r in known + v1]
    t = [r["_ts"] for r in known] + [datetime.fromisoformat(r["event_ist"]).replace(tzinfo=IST) for r in v1]
    groups = components(len(items), same_vehicle(items, t))
    seen = set(groups[len(known):])
    plates = [[x["true_plate"]] for x in items]
    for r, g in zip(known, groups):
        r["group"] = g
    for r in rows:
        if r["answer_by"] in ANSWERED:
            continue
        mine = [x for x in (r["reading_1"], r["reading_2"]) if x and kind(x) == "plate"]
        if not mine:
            continue
        i = next((i for i in range(len(items)) if (items[i]["camera"] == r["camera"] and
                                                    abs((t[i] - r["_ts"]).total_seconds()) <= 10)
                  or any(lev(x, y) <= 1 for x in mine for y in plates[i])), None)
        r["group"] = groups[i] if i is not None else f"g{len(set(groups)) + 1:03d}"
        items.append({"camera": r["camera"]})
        t.append(r["_ts"])
        plates.append(mine)
        groups.append(r["group"])
    for r in rows:
        r["vehicle"] = ("seen" if r["group"] in seen else "new") if v1 and r["group"] else ""


def v1_rows() -> list[dict]:
    path = OUT / "sandbox-blind-v1" / "manifest.csv"
    if not path.exists():
        raise SystemExit(f"{path} is missing: the fresh set's seen and new vehicles are defined against it")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gather(key: str) -> dict:
    """What a freeze of `key` would hold, from the live database, writing nothing."""
    name = ON_REQUEST[key]
    if key == "fresh":
        revs, window = fetch(FRESH_AFTER, None)
        src = v1_source(revs)
        cut = min(now(), FRESH_BY)
        pool = [r for r in revs if r["sighting_ts"] > FRESH_AFTER and r["sighting_id"] not in src]
        left_to_v1 = sum(i in src for i in window)    # v1's last sighting falls inside the boundary second
        window = [i for i in window if i not in src]
    else:
        revs, window = fetch(V1_WINDOW[0], V1_WINDOW[1])
        src = v1_source(revs)
        cut = now()
        pool = [r for r in revs if r["sighting_id"] in src]
        left_to_v1 = 0
    by, ignored = readers(pool, cut)
    if key == "blindv2":
        ignored["reader 2 review in v1's window but not of its 144"] += sum(
            r["username"] == "auditor" and V1_WINDOW[0] <= r["sighting_ts"] <= V1_WINDOW[1] and r["sighting_id"] not in src
            for r in revs)
    adj = adjudication(name)
    rows, notes = [], Counter()
    for sid in sorted(by, key=lambda s: (min(x["sighting_ts"] for x in by[s].values()), s)):
        one, two = by[sid].get("1"), by[sid].get("2")
        first = min(by[sid].values(), key=lambda r: (r["created_at"], r["id"]))   # its stored read is the one graded
        how, answer = settle(one and one["seen"], two and two["seen"], adj.get(sid))
        notes["the two reviews graded different stored reads"] += bool(one and two
                                                                       and one["stored_plate"] != two["stored_plate"])
        notes["stored read changed since the review"] += bool(first["plate_norm"] is not None
                                                              and first["plate_norm"] != first["stored_plate"])
        src_crop = ROOT / "data" / (first["crop_path"] or "").lstrip("/")
        if how in ANSWERED and not (first["crop_path"] and src_crop.is_file()):
            how, answer = "crop missing", ""
        both = bool(one and two)
        rows.append({
            "id": str(sid), "camera": first["camera_code"],
            "event_ist": f"{first['sighting_ts'].astimezone(IST):%Y-%m-%d %H:%M:%S}", "true_plate": answer,
            "stored": first["stored_plate"], "verdict": grade(answer, first["stored_plate"]) if answer else "",
            "ocr_conf": "" if first["ocr_conf"] is None else f"{first['ocr_conf']:.3f}", "conf_band": band(first["ocr_conf"]),
            "group": "", "vehicle": "", "readers": "both" if both else "1" if one else "2", "answer_by": how,
            "reading_1": reading(one["seen"]) if one else "", "reading_2": reading(two["seen"]) if two else "",
            "_ts": first["sighting_ts"], "_crop": src_crop,
            "_plates_both": both and kind(reading(one["seen"])) == kind(reading(two["seen"])) == "plate",
        })
        rows[-1]["_disagree"] = rows[-1]["_plates_both"] and rows[-1]["reading_1"] != rows[-1]["reading_2"]
    disputed = {int(r["id"]) for r in rows if r["_disagree"]}
    notes["adjudication lines not for a disagreement"] += sum(s not in disputed for s in adj)   # a mistyped id
    group_rows(rows, v1_rows() if key == "fresh" else [])
    return {"key": key, "name": name, "rows": rows, "ignored": ignored, "notes": notes, "window": window, "src": src,
            "cut": cut, "adj": adj, "by": by, "left_to_v1": left_to_v1}


def reader_counts(rows: list[dict]) -> dict:
    """The readers' figures for one population of reviewed sightings (all, or new vehicles)."""
    kept = [r for r in rows if r["answer_by"] in ANSWERED]
    both = [r for r in rows if r["readers"] == "both"]
    return {"rows": len(kept), "rows_by_readers": dict(Counter(r["readers"] for r in kept)),
            "rows_by_answer": dict(Counter(r["answer_by"] for r in kept)),
            "both_typed_a_plate": sum(r["_plates_both"] for r in rows),
            "same_reading": sum(r["_plates_both"] and not r["_disagree"] for r in rows),
            "disagreements": sum(r["_disagree"] for r in rows),
            "settled": sum(r["_disagree"] and r["answer_by"] != UNSETTLED for r in rows),
            "unsettled": sum(r["answer_by"] == UNSETTLED for r in rows),
            "readers_split_plate_or_not": sum((kind(r["reading_1"]) == "plate") != (kind(r["reading_2"]) == "plate")
                                              for r in both),
            "neither_typed_a_plate": sum(kind(r["reading_1"]) != "plate" and kind(r["reading_2"]) != "plate"
                                         for r in both),
            "left_out": dict(Counter(r["answer_by"] for r in rows if r["answer_by"] not in ANSWERED))}


def counts(g: dict) -> dict:
    """Structural counts only: never a verdict, never how many stored reads were right."""
    rows = g["rows"]
    kept = [r for r in rows if r["answer_by"] in ANSWERED]
    out = {"sightings_in_window_with_crop": len(g["window"]), "sightings_with_a_reader_review": len(rows),
           "reviews_by_reader": {"1": sum(r["reading_1"] != "" for r in rows), "2": sum(r["reading_2"] != "" for r in rows)},
           **reader_counts(rows), "cameras": dict(Counter(r["camera"] for r in kept))}
    if g["key"] == "fresh":
        pool = [r for r in rows if r["answer_by"] in (*ANSWERED, UNSETTLED)]
        out["vehicles"] = dict(Counter(r["vehicle"] for r in kept))
        out["vehicles_with_unsettled"] = dict(Counter(r["vehicle"] for r in pool))
        out["new_vehicles"] = reader_counts([r for r in rows if r["vehicle"] == "new"])
        out["left_out_no_plate_typed"] = sum(r["answer_by"] not in ANSWERED and not r["group"] for r in rows)
        out["v1_sightings_left_to_v1"] = g["left_to_v1"]
    else:
        read2 = [s for s in g["src"] if "2" in g["by"].get(s, {})]
        order = sorted(read2, key=lambda s: (g["by"][s]["2"]["sighting_ts"], s))   # the queue: oldest sighting first
        out |= {"v1_source_sightings": len(g["src"]), "reader2_read": len(read2),
                "reader2_read_all": bool(g["src"]) and len(read2) == len(g["src"]),
                "reader2_in_page_order": order == sorted(read2, key=lambda s: (g["by"][s]["2"]["created_at"], s))}
    return out


def describe(g: dict, c: dict, dry_run: bool) -> None:
    print(f"{g['name']}{' (dry run: nothing written)' if dry_run else ''}: {c['sightings_in_window_with_crop']} sandbox "
          f"sightings with a crop in the window, {c['sightings_with_a_reader_review']} with a reader's blind review "
          f"(reader 1 {c['reviews_by_reader']['1']}, reader 2 {c['reviews_by_reader']['2']}); reviews counted up to "
          f"{g['cut']:%d %b %H:%M} IST")
    print(f"  rows {c['rows']}: by readers {c['rows_by_readers']}, answer {c['rows_by_answer']}; both typed a plate "
          f"{c['both_typed_a_plate']} (same reading {c['same_reading']}, disagreements {c['disagreements']}: settled "
          f"{c['settled']}, unsettled {c['unsettled']}); one typed a plate and the other not "
          f"{c['readers_split_plate_or_not']}; neither typed a plate {c['neither_typed_a_plate']}")
    print(f"  left out {c['left_out']}; cameras {c['cameras']}; reviews ignored {dict(g['ignored'])}; {dict(g['notes'])}")
    if "vehicles" in c:
        n = c["new_vehicles"]
        print(f"  vehicles (rows) {c['vehicles']}; with unsettled rows {c['vehicles_with_unsettled']}; new vehicles: "
              f"rows {n['rows']}, both typed a plate {n['both_typed_a_plate']}, disagreements {n['disagreements']} "
              f"(unsettled {n['unsettled']}), left out {n['left_out']}; left out with no plate typed "
              f"{c['left_out_no_plate_typed']}; v1's own sightings after the boundary left to v1 "
              f"{c['v1_sightings_left_to_v1']}")
    else:
        print(f"  v1's source {c['v1_source_sightings']} sightings; reader 2 has read {c['reader2_read']} "
              f"(all: {c['reader2_read_all']}, in the page's order: {c['reader2_in_page_order']})")


def freeze(key: str, dry_run: bool = False) -> None:
    """sandbox-fresh-v1 or sandbox-blind-v2, once. manifest.csv (the rows with an answer, as sandbox-blind-v1's plus the
    readers' columns) is written last: it is what marks the set frozen."""
    name = ON_REQUEST[key]
    if frozen(name):
        if key == "fresh":
            print("  reviews made after its freeze belong to sandbox-fresh-v2, a separate freeze this script does not "
                  "build yet; rows are never appended to a frozen set")
        return
    g = gather(key)
    c = counts(g)
    describe(g, c, dry_run)
    if dry_run:
        return
    kept = [r for r in g["rows"] if r["answer_by"] in ANSWERED]
    if not kept:
        print(f"{name}: no row has an answer yet; nothing frozen")
        return
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for r in kept:
        try:
            r["layout"], r["sha256"], r["width_px"], r["height_px"] = copy(r["_crop"], d / f"{r['id']}.jpg")
        except (OSError, AttributeError):    # never the error itself: the source crop's name carries the plate
            raise SystemExit(f"{name}: sighting {r['id']}: its crop could not be copied or decoded; nothing frozen "
                             "(manifest.csv is written last), run it again") from None
    left = [r | {"reason": r["answer_by"]} for r in g["rows"] if r["answer_by"] not in ANSWERED]
    with open(d / "left_out.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEFT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(left)
    at, (head, changed) = now(), git_head()
    info = {"set": name, "frozen_ist": at.isoformat(timespec="seconds"), "git_head": head,
            "uncommitted_paths_at_freeze": changed, "rule": "bench/pipeline_gates.md, 'Real labelled data'",
            "readers": {"1": "admin", "2": "auditor"}, "reviews_up_to_ist": g["cut"].isoformat(timespec="seconds"),
            "counts": c, "layouts": dict(Counter(r["layout"] for r in kept)), "ignored_reviews": dict(g["ignored"]),
            "notes": dict(g["notes"]), "adjudication_lines": len(g["adj"])}
    if key == "fresh":
        info |= {"window": {"after_ist": FRESH_AFTER.isoformat(), "cameras": "^CAM[0-9]{2}$",
                            "v1_sightings_left_to_v1": g["left_to_v1"],
                            "rule": "frame time after 07:55:27 IST, the last sighting in v1; v1's own sightings stay "
                                    "v1's (its last, at 07:55:27.55, falls inside that second)"},
                 "capture_build": CAPTURE_BUILD, "frozen_by_deadline": at <= FRESH_BY,
                 "deadline_ist": FRESH_BY.isoformat(),
                 "later_reviews": "reviews made after reviews_up_to_ist belong to sandbox-fresh-v2, a separate freeze "
                                  "(not built yet); rows are never appended to this set"}
    else:
        by_time = at <= HEADLINE_BY
        info |= {"window": {"from_ist": V1_WINDOW[0].isoformat(), "to_ist": V1_WINDOW[1].isoformat()},
                 "headline": {"frozen_by_deadline": by_time, "deadline_ist": HEADLINE_BY.isoformat(),
                              "reader2_read_all": c["reader2_read_all"], "all_disagreements_settled": c["unsettled"] == 0,
                              "holds_as_far_as_checkable": by_time and c["reader2_read_all"] and c["unsettled"] == 0,
                              "not_checkable_here": ["reader 2 is a different person from reader 1",
                                                     "each disagreement was settled from the crop and the two "
                                                     "readings only, never Sentinel's read"]}}
        try:
            with open(OUT / "sandbox-blind-v1" / "manifest.csv", encoding="utf-8") as f:
                v1 = {x["id"]: x["sha256"] for x in csv.DictReader(f)}
        except FileNotFoundError:
            v1 = {}
        info["notes"]["v1 rows not in v1's source"] = sum(i not in {str(s) for s in g["src"]} for i in v1)
        info["notes"]["crop differs from v1's copy"] = sum(r["id"] in v1 and v1[r["id"]] != r["sha256"] for r in kept)
    (d / "freeze.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    write(name, [{k: r[k] for k in FIELDS} for r in kept])


def sheet(key: str) -> None:
    """The adjudication sheet: each disagreement's crop and the two readings, never Sentinel's read, its confidence or
    the crop's file name (which carries the stored plate). A template adjudication.csv is written only if none exists."""
    name = ON_REQUEST[key]
    if (OUT / name / "manifest.csv").exists():
        print(f"{name}: already frozen; adjudication is closed")
        return
    g = gather(key)
    todo = [r for r in g["rows"] if r["_disagree"]]
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    cards = []
    for r in todo:
        try:     # never the error itself: the source crop's name carries the plate
            img = f'<img alt="crop" src="data:image/jpeg;base64,{base64.b64encode(r["_crop"].read_bytes()).decode()}">'
        except OSError:
            img = "<p>crop missing or unreadable</p>"
        answer = g["adj"].get(int(r["id"]))
        cards.append(f"<section><h2>Sighting {r['id']}</h2><p>{html.escape(r['camera'])}, {r['event_ist']} IST</p>{img}"
                     f"<p>Reader 1: <code>{html.escape(r['reading_1'])}</code> &nbsp; Reader 2: "
                     f"<code>{html.escape(r['reading_2'])}</code></p><p>Answer in adjudication.csv: "
                     f"{'<code>' + html.escape(answer) + '</code>' if answer else 'not settled'}</p></section>")
    page = ("<!doctype html><html><head><meta charset='utf-8'><title>Adjudication sheet</title><style>body{font:15px "
            "system-ui,sans-serif;margin:16px;max-width:900px}section{border-top:1px solid #999;padding:8px 0}"
            "img{max-width:100%;image-rendering:pixelated;min-width:320px}code{font-size:18px}</style></head><body>"
            f"<h1>{name}: {len(todo)} disagreements</h1><p>Settle each from the crop and the two readings only, "
            "together, and type the plate in adjudication.csv (<code>?</code> unreadable, <code>-</code> not a plate); "
            "leave the answer empty if you cannot agree. Sentinel's read is not shown and must not be looked up.</p>"
            + "".join(cards) + "</body></html>")
    (d / "sheet.html").write_text(page, encoding="utf-8")
    template = d / "adjudication.csv"
    if template.exists():
        kept = f"adjudication.csv kept ({len(g['adj'])} lines; {sum(int(r['id']) not in g['adj'] for r in todo)} " \
               "disagreements not listed in it)"
    else:
        with open(template, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sighting_id", "answer", "note"])
            w.writerows([r["id"], "", ""] for r in todo)
        kept = f"adjudication.csv template written ({len(todo)} lines)"
    print(f"{name}: sheet.html with {len(todo)} disagreements "
          f"({sum(r['answer_by'] != UNSETTLED for r in todo)} settled); {kept}")


BUILDERS = {"sandbox": sandbox, "ownfeed": ownfeed, "blind": sandbox_blind}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Freeze the OCR test sets; a set already frozen is kept as it is.")
    ap.add_argument("sets", nargs="*", choices=[*BUILDERS, *ON_REQUEST, "sheet"],
                    help="sandbox (sandbox-v1, reject-v1), ownfeed, blind; fresh and blindv2 only when named; "
                         "sheet fresh|blindv2 writes the adjudication sheet")
    ap.add_argument("--dry-run", action="store_true", help="fresh, blindv2: print counts only, write nothing")
    a = ap.parse_args(argv)
    if "sheet" in a.sets:
        if a.sets[0] != "sheet" or len(a.sets) != 2 or a.sets[1] not in ON_REQUEST or a.dry_run:
            ap.error("usage: ocr_sets.py sheet fresh|blindv2")
        sheet(a.sets[1])
        return
    if a.dry_run and not (a.sets and all(s in ON_REQUEST for s in a.sets)):
        ap.error("--dry-run applies to fresh and blindv2, named")
    for key in a.sets or BUILDERS:
        if key in ON_REQUEST:
            freeze(key, a.dry_run)
        else:
            BUILDERS[key]()


if __name__ == "__main__":
    main()
