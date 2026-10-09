"""How right are the plates Sentinel stored from the organisers' sandbox? The sandbox has no ground truth, so each
stored sighting is checked by eye against its own evidence crop.

    uv run --no-sync python bench/sandbox_eye.py sheets [--since ...]   # contact sheets + a labels CSV to fill in
    uv run --no-sync python bench/sandbox_eye.py score                   # labels CSV -> bench/results/sandbox_eye.md
    uv run --no-sync python bench/sandbox_eye.py sheets --blind          # sheets without the stored read + blind.csv
    uv run --no-sync python bench/sandbox_eye.py score --blind --reviewer "Name"   # -> bench/results/sandbox_eye_blind.md
    uv run --no-sync python bench/sandbox_eye.py score --from-db [--since ...]     # -> bench/results/sandbox_review.md

`--from-db` scores the verdicts people recorded in the control room's Plate review page (table plate_reviews),
blind and verify kept apart, counts only.

Blind mode is for a person: the sheets show only the crop, and they type the plate they see into blind.csv
(`?` if they cannot read it, `-` if it is not a plate). The verdicts are then derived by comparing their reading
with the stored read, so the reviewer never sees what Sentinel stored.

Verdicts: exact (stored text = the plate in the crop), one_off (one character different, missing or extra),
wrong (further off), not_a_plate (the crop shows no vehicle plate, e.g. a hoarding), unreadable (a person
cannot read the plate in the crop either; left out of precision).

The sheets and the labels CSV hold real registration numbers and stay in data/gov-sandbox/eye (gitignored);
only totals go into the results file.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import cv2
import numpy as np

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
EYE = ROOT / "data" / "gov-sandbox" / "eye"
LABELS = EYE / "labels.csv"
BLIND = EYE / "blind"
IST = timezone(timedelta(hours=5, minutes=30))
VERDICTS = ("exact", "one_off", "wrong", "not_a_plate", "unreadable")


async def sightings(since: datetime | None) -> list:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        return await conn.fetch(
            """SELECT s.id, c.camera_code, s.event_ts, s.plate_norm, s.ocr_conf, s.crop_path
               FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
               WHERE c.camera_code ~ '^CAM[0-9]{2}$' AND ($1::timestamptz IS NULL OR s.event_ts >= $1)
               ORDER BY s.event_ts""", since)
    finally:
        await conn.close()


def sheets(a) -> int:
    rows = asyncio.run(sightings(datetime.fromisoformat(a.since).replace(tzinfo=IST) if a.since else None))
    EYE.mkdir(parents=True, exist_ok=True)
    known = {}
    if LABELS.exists():
        with open(LABELS, encoding="utf-8") as f:
            known = {r["id"]: r for r in csv.DictReader(f)}
    tiles, out = [], []
    for r in rows:
        rid = str(r["id"])
        prev = known.get(rid, {})
        out.append({"id": rid, "camera": r["camera_code"], "event_ist": f"{r['event_ts'].astimezone(IST):%Y-%m-%d %H:%M:%S}",
                    "stored": r["plate_norm"], "ocr_conf": f"{r['ocr_conf']:.2f}", "crop": r["crop_path"] or "",
                    "true_plate": prev.get("true_plate", ""), "verdict": prev.get("verdict", ""), "note": prev.get("note", "")})
        p = ROOT / "data" / (r["crop_path"] or "").lstrip("/")
        img = cv2.imread(str(p)) if r["crop_path"] and p.exists() else np.zeros((60, 200, 3), np.uint8)
        t = cv2.resize(img, (360, max(60, min(180, int(360 * img.shape[0] / max(1, img.shape[1]))))))
        t = cv2.copyMakeBorder(t, 0, 180 - t.shape[0] + 34, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        label = f"#{len(out)} {r['camera_code']}" + ("" if a.blind else f" {r['plate_norm']}")
        cv2.putText(t, label, (4, t.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
        tiles.append(t)
    if a.blind:
        BLIND.mkdir(parents=True, exist_ok=True)
        seen = {}
        if (BLIND / "blind.csv").exists():
            with open(BLIND / "blind.csv", encoding="utf-8") as f:
                seen = {r["id"]: r["seen"] for r in csv.DictReader(f)}
        with open(BLIND / "blind.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["n", "id", "camera", "seen"])
            w.writeheader()
            w.writerows({"n": i, "id": r["id"], "camera": r["camera"], "seen": seen.get(r["id"], "")}
                        for i, r in enumerate(out, 1))
    else:
        with open(LABELS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["id"])
            w.writeheader()
            w.writerows(out)
    where = BLIND if a.blind else EYE
    for old in where.glob("sheet_*.jpg"):
        old.unlink()
    per = 20
    for i in range(0, len(tiles), per):
        chunk = tiles[i:i + per] + [np.zeros_like(tiles[0])] * (-len(tiles[i:i + per]) % 4)
        grid = np.vstack([np.hstack(chunk[j:j + 4]) for j in range(0, len(chunk), 4)])
        cv2.imwrite(str(where / f"sheet_{i // per + 1:02d}.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"{len(out)} sightings -> {BLIND / 'blind.csv' if a.blind else LABELS} and "
          f"{len(range(0, len(tiles), per))} sheets in {where}")
    return 0


def edits(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def blind_verdict(seen: str, stored: str) -> str:
    s = "".join(ch for ch in seen.upper() if ch.isalnum() or ch in "?-")
    if s == "?":
        return "unreadable"
    if s == "-":
        return "not_a_plate"
    d = edits(s, stored)
    return "exact" if d == 0 else "one_off" if d == 1 else "wrong"


def score(a) -> int:
    with open(LABELS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assistant = {r["id"]: r["verdict"] for r in rows}
    if a.blind:
        if not a.reviewer:
            raise SystemExit("--blind needs --reviewer: the person who read the plates")
        with open(BLIND / "blind.csv", encoding="utf-8") as f:
            seen = {r["id"]: r["seen"] for r in csv.DictReader(f) if r["seen"].strip()}
        for r in rows:
            r["verdict"] = blind_verdict(seen[r["id"]], r["stored"]) if r["id"] in seen else ""
    labelled = [r for r in rows if r["verdict"] in VERDICTS]
    v = Counter(r["verdict"] for r in labelled)
    judged = [r for r in labelled if r["verdict"] != "unreadable"]
    per_cam: dict[str, Counter] = {}
    for r in labelled:
        per_cam.setdefault(r["camera"], Counter())[r["verdict"]] += 1
    plates = [r for r in judged if r["verdict"] != "not_a_plate"]
    exact = v["exact"]
    first = min((r["event_ist"] for r in rows), default="")
    last = max((r["event_ist"] for r in rows), default="")
    # once people have checked the same sightings blind on the Plate review page, this (not blind) check is not the
    # figure to quote, and its own file says so
    review = ROOT / "bench" / "results" / "sandbox_review.json"
    people = (json.loads(review.read_text(encoding="utf-8")).get("modes", {}).get("blind") or {}) if review.exists() else {}
    method = (f"each stored sighting was compared with its own evidence crop (the image of the best read) by {a.reviewer}, "
              "blind: the sheets showed only the crop, the reviewer typed the plate they saw, and the verdict comes from "
              "comparing that reading with the stored read." if a.blind else
              "each stored sighting was compared with its own evidence crop (the image of the best read) by the team's AI "
              "coding assistant (Claude, by Anthropic), with the stored read shown on each tile: not blind, and not a "
              "person. "
              + ("It is the earlier check, not the figure to quote: "
                 + ("a team member" if len(people.get("reviewers", [])) == 1 else "team members")
                 + " later checked these sightings blind on the control room's Plate review page "
                 f"({people['reviews']} reviews; `sandbox_review.md`)."
                 if people.get("reviews") else
                 "A blind check by a team member: the control room's Plate review page, then `score --from-db`."))
    agree = sum(1 for r in labelled if assistant.get(r["id"]) == r["verdict"])
    L = [f"# Plates stored from the organisers' sandbox, checked against their crops{' (blind)' if a.blind else ''}", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_eye.py score` from {len(labelled)} labelled of "
         f"{len(rows)} stored sightings on the sandbox cameras ({first} to {last} IST). Real Gujarat plates on "
         "government cameras (replayed recordings), not synthetic ones.", "",
         f"Method: the sandbox gives no ground truth, so {method} The crop is the best-read frame, so a plate that "
         "cannot be read in it is left out (unreadable). The labels hold real registrations and are kept locally "
         "(data/gov-sandbox/eye), not published."
         + (f" Agreement with the assistant's verdicts: {agree} of {len(labelled)}." if a.blind else ""), "",
         "| Verdict | Sightings |", "|---|---|"]
    L += [f"| {k.replace('_', ' ')} | {v[k]} |" for k in VERDICTS]
    if judged:
        L += ["", f"**Exact, of every stored sighting a person could judge: {exact}/{len(judged)} = "
                  f"{100 * exact / len(judged):.1f}%.** Within one character: {exact + v['one_off']}/{len(judged)} = "
                  f"{100 * (exact + v['one_off']) / len(judged):.1f}%."]
    if plates:
        L += [f"Of the sightings that were vehicle plates: exact {exact}/{len(plates)} = {100 * exact / len(plates):.1f}%; "
              f"within one character {exact + v['one_off']}/{len(plates)} = {100 * (exact + v['one_off']) / len(plates):.1f}%."]
    L += ["", "| Camera | exact | one off | wrong | not a plate | unreadable |", "|---|---|---|---|---|---|"]
    L += [f"| {c} | " + " | ".join(str(n[k]) for k in VERDICTS) + " |" for c, n in sorted(per_cam.items())]
    L += ["", "Precision only: how many plates on screen were never stored (capture rate) needs every plate in the "
              "footage labelled, which the sandbox's live, unrecorded replay does not allow."]
    out = ROOT / "bench" / "results" / ("sandbox_eye_blind.md" if a.blind else "sandbox_eye.md")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({
        "stored": len(rows), "labelled": len(labelled), "verdicts": {k: v[k] for k in VERDICTS},
        "judged": len(judged), "plates": len(plates), "exact": exact, "one_off": v["one_off"],
        "cameras_with_plates": sorted({r["camera"] for r in plates}), "first_ist": first, "last_ist": last,
        "reviewer": a.reviewer if a.blind else "AI assistant (not blind)", "blind": bool(a.blind)}, indent=1),
        encoding="utf-8")
    print("\n".join(L[8:16]))
    print("wrote", out)
    return 0


BANDS = ((0.9, ">=0.9"), (0.7, "0.7-0.9"), (0.5, "0.5-0.7"), (0.35, "0.35-0.5"), (0.0, "<0.35"))


def band(conf: float) -> str:
    conf = round(conf, 3)   # REAL in the database: 0.9 comes back as 0.8999999761
    return next(name for floor, name in BANDS if conf >= floor)


async def reviews(since: datetime | None, until: datetime | None, cameras: str) -> list:
    """Reviews of sandbox sightings after v1's window, and the second reader's, are left out: sandbox-fresh-v1 and
    sandbox-blind-v2 are scored only from their frozen files (bench/sandbox_fresh.py), never pooled with v1
    (bench/pipeline_gates.md, "Real labelled data")."""
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        return await conn.fetch(
            """SELECT r.sighting_id, r.sighting_ts, r.mode, r.verdict, r.ocr_conf, r.seen, c.camera_code,
                      u.username, u.full_name
               FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
               WHERE c.camera_code ~ $1 AND ($2::timestamptz IS NULL OR r.sighting_ts >= $2)
                 AND ($3::timestamptz IS NULL OR r.sighting_ts <= $3)
                 AND NOT (c.camera_code ~ '^CAM[0-9]{2}$'
                          AND (r.sighting_ts > '2026-09-26 07:56:00+05:30' OR u.username = 'auditor'))
               ORDER BY r.sighting_ts""", cameras, since, until)
    finally:
        await conn.close()


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "none"


def score_db(a) -> int:
    """Totals from the verdicts people recorded on the control room's Plate review page. The rows hold what
    each reviewer typed; only counts leave the database."""
    ist = lambda s: datetime.fromisoformat(s).replace(tzinfo=IST) if s else None  # noqa: E731
    rows = asyncio.run(reviews(ist(a.since), ist(a.until), a.cameras))
    out: dict = {"cameras_pattern": a.cameras, "since_ist": a.since, "until_ist": a.until, "modes": {}}
    L = ["# Plates stored by Sentinel, checked by people on the Plate review page", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_eye.py score --from-db` from "
         f"{len(rows)} review(s) in the database (cameras matching `{a.cameras}`"
         + (f", sightings from {a.since} IST" if a.since else "") + (f" to {a.until} IST" if a.until else "") + "). "
         "Sandbox reviews of sightings after 26 Sep 07:56 IST, and the second reader's (`auditor`), are left out: "
         "`bench/sandbox_fresh.py` scores them from their frozen sets, never pooled with these.", "",
         "Method: a reviewer opens a stored sighting's evidence crop (the image of the best read) in the control room. "
         "**Blind**: the page shows only the crop; the reviewer types the plate they see (`?` unreadable, `-` not a "
         "plate) and the server derives the verdict by comparing that reading with the stored read (exact, one "
         "character off, wrong). **Verify**: the page shows the stored read and its confidence, and the reviewer "
         "confirms or corrects it. The two are never mixed: only blind numbers are an independent measure. The "
         "readings hold real registrations and stay in the database; only totals are published here."]
    for mode in ("blind", "verify"):
        mine = [r for r in rows if r["mode"] == mode]
        v = Counter(r["verdict"] for r in mine)
        plates = [r for r in mine if r["verdict"] not in ("not_a_plate", "unreadable")]
        exact, one = v["exact"], v["one_off"]
        per_cam: dict[str, Counter] = {}
        for r in mine:
            per_cam.setdefault(r["camera_code"], Counter())[r["verdict"]] += 1
        bands: dict[str, Counter] = {}
        for r in plates:
            if r["ocr_conf"] is not None:
                bands.setdefault(band(r["ocr_conf"]), Counter())[r["verdict"]] += 1
        people = Counter((r["username"], r["full_name"]) for r in mine)
        by_sighting: dict[int, list] = {}
        for r in mine:
            by_sighting.setdefault(r["sighting_id"], []).append(r)
        multi = [g for g in by_sighting.values() if len(g) >= 2]
        agree = {"sightings_with_2plus": len(multi),
                 "same_verdict": sum(len({r["verdict"] for r in g}) == 1 for g in multi),
                 "same_reading": sum(len({r["seen"] for r in g}) == 1 for g in multi)}
        out["modes"][mode] = {
            "reviews": len(mine), "sightings": len(by_sighting), "verdicts": {k: v[k] for k in VERDICTS},
            "plates": len(plates), "exact": exact, "one_off": one,
            "cameras": {c: {k: n[k] for k in VERDICTS} for c, n in sorted(per_cam.items())},
            "bands": {name: {"plates": sum(bands[name].values()), "exact": bands[name]["exact"],
                             "one_off": bands[name]["one_off"]} for _, name in BANDS if name in bands},
            "reviewers": [{"username": u, "full_name": f, "reviews": n} for (u, f), n in sorted(people.items())],
            **({"agreement": agree} if mode == "blind" else {})}
        L += ["", f"## {mode.capitalize()}", ""]
        if not mine:
            L += [f"No {mode} reviews yet."]
            continue
        L += [f"{len(mine)} review(s) of {len(by_sighting)} sighting(s) by "
              + ", ".join(f"{f} (`{u}`, {n})" for (u, f), n in sorted(people.items())) + ".", "",
              "| Verdict | Reviews |", "|---|---|"]
        L += [f"| {k.replace('_', ' ')} | {v[k]} |" for k in VERDICTS]
        L += ["", f"**Of the reviews that were vehicle plates a person could read: exact {pct(exact, len(plates))}; "
                  f"within one character {pct(exact + one, len(plates))}.**", "",
              "| Camera | exact | one off | wrong | not a plate | unreadable |", "|---|---|---|---|---|---|"]
        L += [f"| {c} | " + " | ".join(str(n[k]) for k in VERDICTS) + " |" for c, n in sorted(per_cam.items())]
        L += ["", "| OCR confidence | plates | exact | within one |", "|---|---|---|---|"]
        L += [f"| {name} | {sum(bands[name].values())} | {pct(bands[name]['exact'], sum(bands[name].values()))} | "
              f"{pct(bands[name]['exact'] + bands[name]['one_off'], sum(bands[name].values()))} |"
              for _, name in reversed(BANDS) if name in bands]
        if mode == "blind":
            L += ["", f"Agreement: {agree['sightings_with_2plus']} sighting(s) checked blind by two or more reviewers; "
                      f"{agree['same_verdict']} with the same verdict, {agree['same_reading']} with the same reading."]
    L += ["", "Precision only: a review judges a plate Sentinel stored. Plates on screen that were never stored "
              "(capture rate) are not counted here."]
    path = ROOT / "bench" / "results" / "sandbox_review.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    path.with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(L[5:]))
    print("wrote", path)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheets")
    s.add_argument("--since", help="IST, e.g. 2026-09-25T20:00")
    s.add_argument("--blind", action="store_true", help="sheets without the stored read, and blind.csv for a person")
    c = sub.add_parser("score")
    c.add_argument("--blind", action="store_true", help="score a person's readings in blind.csv")
    c.add_argument("--reviewer", help="with --blind: who read the plates")
    c.add_argument("--from-db", action="store_true",
                   help="score the Plate review page's verdicts -> bench/results/sandbox_review.md")
    c.add_argument("--since", help="with --from-db: sightings from, IST, e.g. 2026-09-26T09:00")
    c.add_argument("--until", help="with --from-db: sightings until, IST")
    c.add_argument("--cameras", default="^CAM[0-9]{2}$", help="with --from-db: camera code regex (default: sandbox)")
    a = ap.parse_args()
    if a.cmd == "sheets":
        return sheets(a)
    return score_db(a) if a.from_db else score(a)


if __name__ == "__main__":
    raise SystemExit(main())
