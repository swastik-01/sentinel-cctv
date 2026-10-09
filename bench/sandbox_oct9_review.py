"""How right were the plates Sentinel stored from the organisers' sandbox on 9 Oct? Scores the blind reviews people make
on the Plate review page of the sightings the plate worker stored on CAM06 and CAM07 from 08:15 to 08:31 IST (the
15-minute run in bench/results/sandbox_oct9.md).

    uv run --no-sync python bench/sandbox_oct9_review.py --progress     # reviews made so far, per account; no verdicts
    uv run --no-sync python bench/sandbox_oct9_review.py [--reader auditor="Name"]   # -> bench/results/sandbox_oct9_review.md

Any later session (the finale's blind check after the slot) under the same rules, into a file of its own:

    uv run --no-sync python bench/sandbox_oct9_review.py --since 2026-10-12T11:00 --until 2026-10-12T11:30 \
        [--cameras "^CAM[0-9]{2}$"] --note "what ran, on what" --out bench/results/<session>_review.md

(`bench/sandbox_eye.py score --from-db` cannot do this: it leaves out every sandbox review after 26 Sep, so that
v1's figures stay v1's, and always writes v1's file.)

Rules, fixed on 9 Oct at 13:10 IST, before any of these sightings had a review (the report checks that):
- Rows: every sandbox sighting (camera code ^CAM[0-9]{2}$) with a crop and a frame time in the window.
- Reviews: blind mode only. The page reveals Sentinel's read after each typed reading, and the API refuses a blind
  review from an account that has verified the same sighting, so each account has at most one blind review a sighting.
  Verify-mode reviews are never counted.
- Readers are reported one by one (one account, one person), never pooled; with two readers, their agreement is given.
- Verdicts are the server's, made when the review was saved: exact, one character off, wrong, not a plate, unreadable.
  Precision is over the reviews that were plates a person could read: exact as typed (primary) and within one character,
  each with a Wilson 95% interval; by camera and by confidence band (>= 0.9 and below, compared as the review page does).
- Coverage: how many of the window's sightings each reader read. A rate is over the reviews made, and says so.
- Never pooled with v1 (90 of 120, bench/results/sandbox_review.md) or the 26 Sep fresh sets: another day, another
  build, and the sandbox's looping replay may show the same vehicles in each.
Added at 13:45 IST, after the first review, when the page gained a way to change a saved reading (a mistyped plate):
a change comes after Sentinel's read was shown, so it is not blind. It is reported in a section of its own, with what
the figures would be if every change were accepted; the figures above it keep the first readings.
Counts and rates only: what a reviewer typed and what Sentinel stored stay in the database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
WINDOW = (datetime(2026, 10, 9, 8, 15, tzinfo=IST), datetime(2026, 10, 9, 8, 31, tzinfo=IST))
RULES_FIXED = datetime(2026, 10, 9, 13, 10, tzinfo=IST)
CAMS = r"^CAM[0-9]{2}$"
VERDICTS = ("exact", "one_off", "wrong", "not_a_plate", "unreadable")
PLATES = ("exact", "one_off", "wrong")


async def fetch(cams: str = CAMS, window: tuple[datetime, datetime] = WINDOW) -> tuple[list, list]:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        sightings = await conn.fetch(
            """SELECT s.id, c.camera_code, s.ocr_conf >= real '0.9' AS high
               FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
               WHERE c.camera_code ~ $1 AND s.crop_path IS NOT NULL AND s.event_ts >= $2 AND s.event_ts < $3""",
            cams, *window)
        reviews = await conn.fetch(
            """SELECT r.sighting_id, r.created_at, r.mode, r.verdict, r.seen, r.ocr_conf >= real '0.9' AS high,
                      r.corrected_verdict, c.camera_code, u.username, u.full_name
               FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
               WHERE c.camera_code ~ $1 AND r.sighting_ts >= $2 AND r.sighting_ts < $3
               ORDER BY r.created_at, r.id""", cams, *window)
        return sightings, reviews
    finally:
        await conn.close()


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: int, n: int) -> str:
    if not n:
        return "none"
    lo, hi = wilson(k, n)
    return f"{k} of {n} ({100 * k / n:.0f}%; 95% interval {100 * lo:.0f}–{100 * hi:.0f}%)"


def reader(rows: list) -> dict:
    v = Counter(r["verdict"] for r in rows)
    plates = [r for r in rows if r["verdict"] in PLATES]
    cams: dict[str, Counter] = {}
    for r in rows:
        cams.setdefault(r["camera_code"], Counter())[r["verdict"]] += 1
    bands = {}
    for name, high in ((">=0.9", True), ("<0.9", False), ("no confidence", None)):
        b = [r for r in plates if r["high"] is high]
        if high is None and not b:
            continue
        bands[name] = {"plates": len(b), "exact": sum(r["verdict"] == "exact" for r in b),
                       "within_one": sum(r["verdict"] in ("exact", "one_off") for r in b)}
    exact, within = v["exact"], v["exact"] + v["one_off"]
    changed = [r for r in rows if r["corrected_verdict"]]
    after = Counter(r["corrected_verdict"] or r["verdict"] for r in rows)
    return {"reviews": len(rows), "verdicts": {k: v[k] for k in VERDICTS}, "plates": len(plates),
            "changed_after_reveal": {
                "reviews": len(changed),
                "verdict_changes": dict(Counter(f"{r['verdict']} -> {r['corrected_verdict']}" for r in changed)),
                "if_all_accepted": {"plates": sum(after[k] for k in PLATES), "exact": after["exact"],
                                    "within_one": after["exact"] + after["one_off"]}},
            "exact": exact, "exact_wilson95": wilson(exact, len(plates)),
            "within_one": within, "within_one_wilson95": wilson(within, len(plates)),
            "cameras": {c: {k: n[k] for k in VERDICTS} for c, n in sorted(cams.items())}, "bands": bands,
            "first_review_ist": f"{min(r['created_at'] for r in rows).astimezone(IST):%Y-%m-%d %H:%M}",
            "last_review_ist": f"{max(r['created_at'] for r in rows).astimezone(IST):%Y-%m-%d %H:%M}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--progress", action="store_true", help="how many sightings each account has reviewed; no verdicts")
    ap.add_argument("--reader", action="append", default=[], metavar="ACCOUNT=NAME",
                    help="the person who used an account, for the report (default: the account's name in the registry)")
    ap.add_argument("--since", help="IST, e.g. 2026-10-12T11:00 (default: the 9 Oct run)")
    ap.add_argument("--until", help="IST (default: the 9 Oct run)")
    ap.add_argument("--cameras", default=CAMS, help="camera code regex (default: the sandbox's)")
    ap.add_argument("--note", default="", help="for another session: what ran, on what (the report's conditions)")
    ap.add_argument("--out", help="default bench/results/sandbox_oct9_review.md, for the 9 Oct run only")
    a = ap.parse_args()
    ist = lambda s, d: datetime.fromisoformat(s).replace(tzinfo=IST) if s else d  # noqa: E731
    window = (ist(a.since, WINDOW[0]), ist(a.until, WINDOW[1]))
    oct9 = window == WINDOW and a.cameras == CAMS
    if not oct9 and not a.out:
        raise SystemExit("another session's window needs --out (and --note): the 9 Oct file is that run's")
    out_path = Path(a.out or ROOT / "bench" / "results" / "sandbox_oct9_review.md")
    sightings, reviews = asyncio.run(fetch(a.cameras, window))
    blind = [r for r in reviews if r["mode"] == "blind"]
    accounts = sorted({r["username"] for r in blind})
    if a.progress:
        print(f"{len(sightings)} sightings in the window; blind reviews by account: "
              f"{ {u: sum(r['username'] == u for r in blind) for u in accounts} }; "
              f"verify-mode reviews (never counted): {len(reviews) - len(blind)}")
        return 0
    if not blind:
        print("no blind review of these sightings yet; nothing written")
        return 1
    names = dict(x.split("=", 1) for x in a.reader)
    in_window = {s["id"] for s in sightings}
    outside = sum(r["sighting_id"] not in in_window for r in blind)    # e.g. a sighting whose crop has since gone
    early = sum(r["created_at"] < RULES_FIXED for r in reviews)
    per = {u: reader([r for r in blind if r["username"] == u]) for u in accounts}
    for u in accounts:
        per[u]["name"] = names.get(u) or next(r["full_name"] for r in blind if r["username"] == u)
    by_sighting: dict[int, dict] = {}
    for r in blind:
        by_sighting.setdefault(r["sighting_id"], {})[r["username"]] = r
    both = [g for g in by_sighting.values() if len(g) >= 2]
    plates_both = [g for g in both if all(x["verdict"] in PLATES for x in g.values())]
    agreement = {"sightings_read_by_two_or_more": len(both),
                 "same_verdict": sum(len({x["verdict"] for x in g.values()}) == 1 for g in both),
                 "both_typed_a_plate": len(plates_both),
                 "same_reading": sum(len({x["seen"] for x in g.values()}) == 1 for g in plates_both)}
    now = datetime.now(IST)
    high = sum(bool(s["high"]) for s in sightings)
    out = {"window_ist": [f"{t:%Y-%m-%d %H:%M}" for t in window], "cameras_pattern": a.cameras, "note": a.note,
           "rules_fixed_ist": f"{RULES_FIXED:%Y-%m-%d %H:%M}",
           "scored_ist": f"{now:%Y-%m-%d %H:%M}", "sightings": len(sightings),
           "sightings_by_camera": dict(sorted(Counter(s["camera_code"] for s in sightings).items())),
           "sightings_at_or_above_0_9": high, "reviews_before_rules_fixed": early,
           "blind_reviews_outside_window_set": outside, "verify_reviews_not_counted": len(reviews) - len(blind),
           "readers": per, "agreement": agreement if len(accounts) >= 2 else None}

    per_cam = ", ".join(f"{c} {n}" for c, n in out["sightings_by_camera"].items())
    if oct9:
        L = ["# Plates Sentinel stored from the organisers' sandbox on 9 Oct, read blind by a person", "",
             f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/sandbox_oct9_review.py` from the Plate review page's blind "
             f"reviews of the {len(sightings)} sightings the plate worker stored with a crop on CAM06 and CAM07 from "
             f"{WINDOW[0]:%H:%M} to {WINDOW[1]:%H:%M} IST on 9 Oct ({per_cam}; {high} at confidence 0.9 or above). The "
             "run: `bench/results/sandbox_oct9.md` (one laptop, GTX 1650, the plate worker on these two cameras only, its "
             "settings at their defaults, consume only).", ""]
    else:
        L = ["# Plates Sentinel stored, read blind by a person", "",
             f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/sandbox_oct9_review.py` from the Plate review page's blind "
             f"reviews of the {len(sightings)} sightings stored with a crop on cameras matching `{a.cameras}` from "
             f"{window[0]:%Y-%m-%d %H:%M} to {window[1]:%Y-%m-%d %H:%M} IST ({per_cam or 'none'}; {high} at confidence "
             f"0.9 or above). Conditions: {a.note or 'not given (--note)'}.", ""]
    L += [
         "Method: the reviewer sees only the crop, the image of the sighting's best read, and types the plate they see "
         "(`?` unreadable, `-` not a plate); the server compares that reading with the stored read (exact, one character "
         "off, wrong) and only then shows the reviewer Sentinel's read. The rules for this report were fixed at "
         f"{RULES_FIXED:%d %b %H:%M} IST"
         + (f"; {early} review(s) predate that and are counted only because they exist (check them)" if early else
            f"; the first review of these sightings was made after that, at "
            f"{min(r['created_at'] for r in reviews).astimezone(IST):%Y-%m-%d %H:%M} IST") + ". "
         "What reviewers typed holds real registrations and stays in the database; only totals are published here."]
    for u in accounts:
        p = per[u]
        L += ["", f"## Reader: {p['name']} (`{u}`)", "",
              f"{p['reviews']} blind review(s) of the {len(sightings)} sightings, {p['first_review_ist'][11:]}–"
              f"{p['last_review_ist'][11:]} IST on {p['first_review_ist'][:10]}"
              + ("" if p["reviews"] == len(sightings) else
                 f": **{len(sightings) - p['reviews']} not read, so the rates below are over the reviews made**") + ".", "",
              "| Verdict | Reviews |", "|---|---|"]
        L += [f"| {k.replace('_', ' ')} | {p['verdicts'][k]} |" for k in VERDICTS]
        L += ["", f"**Of the {p['plates']} that were vehicle plates the reader could read: exact "
                  f"{rate(p['exact'], p['plates'])}; within one character {rate(p['within_one'], p['plates'])}.**", "",
              "| Camera | exact | one off | wrong | not a plate | unreadable |", "|---|---|---|---|---|---|"]
        L += [f"| {c} | " + " | ".join(str(n[k]) for k in VERDICTS) + " |" for c, n in p["cameras"].items()]
        L += ["", "| Confidence | plates | exact | within one |", "|---|---|---|---|"]
        L += [f"| {name} | {b['plates']} | {b['exact']} | {b['within_one']} |" for name, b in p["bands"].items()]
        L += ["", "Small numbers: the bands are given as counts, not as evidence that confidence separates right reads "
                  "from wrong ones (G3 marks reads below 0.9 \"check the crop\"; it suppresses nothing)."]
        ch = p["changed_after_reveal"]
        if ch["reviews"]:
            acc = ch["if_all_accepted"]
            L += ["", f"**Changed after the reveal: {ch['reviews']} of the {p['reviews']} reviews** (" + ", ".join(
                f"{k.replace('_', ' ')} {n}" for k, n in sorted(ch["verdict_changes"].items())) + "). The page had shown "
                "Sentinel's read by then, so a change is not blind and the figures above keep the first readings. If every "
                f"change were accepted (not blind): exact {rate(acc['exact'], acc['plates'])}; within one character "
                f"{rate(acc['within_one'], acc['plates'])}."]
        else:
            L += ["", "No reading was changed after the reveal."]
    if len(accounts) >= 2:
        L += ["", "## Agreement", "",
              f"{agreement['sightings_read_by_two_or_more']} sighting(s) read blind by two or more readers: "
              f"{agreement['same_verdict']} with the same verdict; of the {agreement['both_typed_a_plate']} where each "
              f"typed a plate, {agreement['same_reading']} with the same reading."]
    L += ["", "## What this is and is not", "",
          "- Precision only: a review judges a plate Sentinel stored. Plates that passed and were never stored (capture) "
          "are not counted.",
          (f"- One session, {len(out['sightings_by_camera'])} camera(s) with sightings, "
           f"{(window[1] - window[0]).total_seconds() / 60:.0f} minutes: a small sample."),
          "- Never pooled with another set (v1's 90 of 120 on 25–26 Sep, `sandbox_review.md`, the 26 Sep fresh sets, or "
          "another session's): other days or builds, and the sandbox's looping replay may show the same vehicles in each.",
          f"- Blind reviews of sightings no longer in the window's set: {outside}; verify-mode reviews (never counted): "
          f"{len(reviews) - len(blind)}.", ""]
    path = out_path
    path.write_text("\n".join(L), encoding="utf-8", newline="\n")
    path.with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8", newline="\n")
    print("\n".join(L[4:]))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
