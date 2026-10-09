"""Score Sentinel's stored reads on the frozen fresh sandbox sets, by the rules pre-registered in bench/pipeline_gates.md
("Real labelled data: new blind reviews and a second reader"):

    uv run --no-sync python bench/sandbox_fresh.py fresh   # sandbox-fresh-v1 -> bench/results/sandbox_fresh.md + .json
    uv run --no-sync python bench/sandbox_fresh.py v2      # sandbox-blind-v2 -> bench/results/sandbox_blind_v2.md + .json

Reads only the frozen files bench/ocr_sets.py wrote (manifest.csv, left_out.csv, freeze.json) and refuses a set that is
not frozen: there is no path from the live database to these rates, so nobody sees them before the freeze. The capture
windows come from the rotation logs (data/rotation*/rotation.csv). Counts and rates only; plate text stays under data/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_ab import boot_ci, by_group, pct, wilson  # noqa: E402  (ocr_ab sets a CPU-only environment; no crop is read here)
from ocr_sets import CAPTURE_BUILD, FRESH_AFTER, IST  # noqa: E402

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime  # noqa: E402

import numpy as np  # noqa: E402

from sentinel_common import normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SETS = {"fresh": ("sandbox-fresh-v1", "sandbox_fresh"), "v2": ("sandbox-blind-v2", "sandbox_blind_v2")}
CAMS = ("CAM06", "CAM07")
BANDS = (">=0.9", "<0.9")
MEASURES = {"exact": "Exact as typed (primary)", "within1": "Within one character",
            "norm": "Exact after normalising the reading"}
SHORT = {"exact": "exact as typed", "within1": "within one", "norm": "exact after normalising"}
UNLOGGED_GAP_MIN = 30    # rows outside the logs further apart than this are counted as separate runs


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(root: Path, name: str) -> tuple[list[dict], list[dict], dict]:
    d = root / name
    if not (d / "manifest.csv").exists() or not (d / "freeze.json").exists():
        raise SystemExit(f"{name} is not frozen (bench/ocr_sets.py freezes it): nothing is scored before the freeze")
    left = read_csv(d / "left_out.csv") if (d / "left_out.csv").exists() else []
    return read_csv(d / "manifest.csv"), left, json.loads((d / "freeze.json").read_text(encoding="utf-8"))


def recs(rows: list[dict]) -> list[dict]:
    """Per row: the stored read against the answer. `verdict` is the server's grading, frozen with the set."""
    return [{"id": r["id"], "group": r["group"], "one": 1, "exact": int(r["verdict"] == "exact"),
             "within1": int(r["verdict"] in ("exact", "one_off")),
             "norm": int(normalise_plate(r["true_plate"]) == normalise_plate(r["stored"])),
             "band": r["conf_band"], "camera": r["camera"], "layout": r.get("layout", ""), "vehicle": r.get("vehicle", "")}
            for r in rows]


def misses(left: list[dict]) -> list[dict]:
    """Unsettled disagreements, counted as misses for the variant the rule asks for."""
    return [{"id": r["id"], "group": r["group"], "one": 1, "exact": 0, "within1": 0, "norm": 0, "band": r["conf_band"],
             "camera": r["camera"], "layout": "", "vehicle": r.get("vehicle", "")}
            for r in left if r["reason"] == "unsettled disagreement"]


def measure(rs: list[dict], key: str) -> dict:
    groups = sorted({r["group"] for r in rs})
    k, n = sum(r[key] for r in rs), len(rs)
    boot = boot_ci([by_group(rs, key, groups)], [by_group(rs, "one", groups)], [1], np.random.default_rng(0)) if n else None
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n), "group_boot95": boot}


def gap(rs: list[dict], key: str) -> dict | None:
    """(rate at >= 0.9) - (rate below 0.9), with a group-bootstrap interval: G3's test of whether confidence separates
    right reads from wrong ones."""
    hi, lo = ([r for r in rs if r["band"] == b] for b in BANDS)
    if not hi or not lo:
        return None
    groups = sorted({r["group"] for r in rs})
    ci = boot_ci([by_group(hi, key, groups), by_group(lo, key, groups)],
                 [by_group(hi, "one", groups), by_group(lo, "one", groups)], [1, -1], np.random.default_rng(0))
    return {"diff": round(sum(r[key] for r in hi) / len(hi) - sum(r[key] for r in lo) / len(lo), 4), "group_boot95": ci}


def block(rs: list[dict], extra: list[dict]) -> dict:
    """Every figure for one population (all rows, or new vehicles)."""
    out = {m: measure(rs, m) for m in MEASURES}
    out["exact_unsettled_as_misses"] = measure(rs + extra, "exact")
    out["within1_unsettled_as_misses"] = measure(rs + extra, "within1")
    def split(field: str, values) -> dict:
        return {v: {m: measure([r for r in rs if r[field] == v], m) for m in MEASURES} for v in values}
    out["bands"] = split("band", BANDS)
    if any(not r["band"] for r in rs):
        out["bands"] |= {"no confidence stored": split("band", [""])[""]}
    out["band_gap"] = {m: gap(rs, m) for m in MEASURES}
    out["cameras"] = split("camera", sorted({r["camera"] for r in rs}))
    out["layouts"] = split("layout", sorted({r["layout"] for r in rs}))
    return out


def capture_windows(logs: Path, since: datetime, until: datetime, cams: set[str]) -> list[dict]:
    """Analysis windows that included one of `cams`, from scripts/rotate_worker.py's logs, clipped to the set's span."""
    out = []
    for log in sorted(logs.glob("rotation*/rotation.csv")):
        for r in read_csv(log):
            on = r["cameras"].split(",")
            a = max(datetime.fromisoformat(r["start_ist"]).replace(tzinfo=IST), since)
            b = min(datetime.fromisoformat(r["end_ist"]).replace(tzinfo=IST), until)
            if set(on) & cams and b > a:
                out.append({"log": log.parent.name, "start": a, "end": b, "cameras": on})
    return sorted(out, key=lambda w: w["start"])


def stamp(r: dict) -> datetime:
    return datetime.fromisoformat(r["event_ist"]).replace(tzinfo=IST)


def unlogged(rows: list[dict], wins: list[dict]) -> list[dict]:
    """Rows stored outside every logged window (a minute's slack), as spans: a worker started by hand is not in the
    logs, so its run is known only from the first and last row it stored."""
    def inside(r):
        t = stamp(r)
        return any((w["start"] - t).total_seconds() <= 60 and (t - w["end"]).total_seconds() <= 60
                   for w in wins if r["camera"] in w["cameras"])
    spans: list[dict] = []
    for r in sorted((r for r in rows if not inside(r)), key=stamp):
        if not spans or (stamp(r) - spans[-1]["end"]).total_seconds() > UNLOGGED_GAP_MIN * 60:
            spans.append({"start": stamp(r), "end": stamp(r), "rows": Counter()})
        spans[-1]["end"] = stamp(r)
        spans[-1]["rows"][r["camera"]] += 1
    return spans


def cell(x: dict | None) -> str:
    return "n/a" if not x else pct(x)


def gap_text(x: dict | None) -> str:
    if not x:
        return "n/a (a band is empty)"
    ci = x["group_boot95"]
    return f"{x['diff']:+.1%} (groups 95% {ci[0]:+.1%} to {ci[1]:+.1%})" if ci else f"{x['diff']:+.1%}"


def tables(cols: dict[str, dict]) -> list[str]:
    """The measures, bands, cameras and layouts, one column per population."""
    names = list(cols)
    head = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines = ["## Stored read against the answer", ""] + head
    for m, label in MEASURES.items():
        lines.append(f"| {label} | " + " | ".join(cell(cols[c][m]) for c in names) + " |")
    lines.append("| Exact as typed, unsettled disagreements counted as misses | "
                 + " | ".join(cell(cols[c]["exact_unsettled_as_misses"]) for c in names) + " |")
    lines.append("| Within one, unsettled disagreements counted as misses | "
                 + " | ".join(cell(cols[c]["within1_unsettled_as_misses"]) for c in names) + " |")
    lines += ["", "## By confidence band", "",
              "Bands as the Plate review page draws them: the stored confidence (a REAL column) compared with real "
              "'0.9', so a sighting stored at exactly 0.9 (three agreeing reads) is in the top band.", ""] + head
    for b in cols[names[0]]["bands"]:
        for m, label in SHORT.items():
            lines.append(f"| {b}, {label} | " + " | ".join(cell(cols[c]["bands"].get(b, {}).get(m)) for c in names) + " |")
    for m, label in SHORT.items():
        lines.append(f"| >= 0.9 minus < 0.9, {label} | " + " | ".join(gap_text(cols[c]["band_gap"][m]) for c in names)
                     + " |")
    for title, field in (("By camera", "cameras"), ("By layout (one-line or two-line crop)", "layouts")):
        lines += ["", f"## {title}", ""] + head
        for v in sorted({k for c in names for k in cols[c][field]}):
            for m, label in SHORT.items():
                lines.append(f"| {v}, {label} | " + " | ".join(cell(cols[c][field].get(v, {}).get(m)) for c in names)
                             + " |")
    return lines


def agreement(c: dict) -> str:
    both, same = c["both_typed_a_plate"], c["same_reading"]
    w = wilson(same, both)
    return f"{same}/{both} = {same / both:.1%} (Wilson {w[0]:.1%}–{w[1]:.1%})" if both else "none yet"


def readers_lines(pops: dict[str, dict]) -> list[str]:
    """The readers' figures, one column per population (reader_counts in ocr_sets.py, fixed at the freeze)."""
    names = list(pops)
    rows = [("Rows in the set read by reader 1 only", lambda c: c["rows_by_readers"].get("1", 0)),
            ("Rows in the set read by reader 2 only", lambda c: c["rows_by_readers"].get("2", 0)),
            ("Rows in the set read by both", lambda c: c["rows_by_readers"].get("both", 0)),
            ("Exact agreement on plates both read (both typed a plate)", agreement),
            ("Disagreements", lambda c: c["disagreements"]),
            ("of which settled together from the crop and the two readings", lambda c: c["settled"]),
            ("of which unsettled at the freeze (left out; misses in the variant rows)", lambda c: c["unsettled"]),
            ("One reader typed a plate, the other not a plate or unreadable (left out)",
             lambda c: c["readers_split_plate_or_not"]),
            ("Both called it not a plate or unreadable (left out)", lambda c: c["neither_typed_a_plate"]),
            ("Left out, by reason", left_text)]
    return (["## Readers", "", "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
            + [f"| {label} | " + " | ".join(str(f(pops[n])) for n in names) + " |" for label, f in rows])


def left_text(c: dict) -> str:
    return ", ".join(f"{v} {k}" for k, v in sorted(c["left_out"].items())) or "none"


def fresh_report(root: Path, logs: Path) -> tuple[str, dict]:
    name = SETS["fresh"][0]
    rows, left, info = load(root, name)
    c = info["counts"]
    frozen = datetime.fromisoformat(info["frozen_ist"])
    rs, ms = recs(rows), misses(left)
    cols = {"All rows": block(rs, ms), "New vehicles": block([r for r in rs if r["vehicle"] == "new"],
                                                             [r for r in ms if r["vehicle"] == "new"])}
    cams = set(CAMS) | {r["camera"] for r in rows + left}
    wins = capture_windows(logs, FRESH_AFTER, frozen, cams)
    spans = unlogged(rows + left, wins)
    out_n = sum(sum(s["rows"].values()) for s in spans)
    seen, new = sum(r["vehicle"] == "seen" for r in rs), sum(r["vehicle"] == "new" for r in rs)
    to_v1 = info["window"].get("v1_sightings_left_to_v1", 0)
    cut = datetime.fromisoformat(info["reviews_up_to_ist"])
    lines = [
        f"# Fresh sandbox plates, read blind: {name}", "",
        f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_fresh.py` from the frozen set "
        f"`data/ocr-eval/{name}` (frozen {frozen:%d %b %Y %H:%M} IST, tooling at git {info['git_head']}). Rules "
        "pre-registered in `bench/pipeline_gates.md`, \"Real labelled data\". Counts and rates only: no plate text is "
        "written here.", "",
        "Scored: the plate Sentinel stored for each sandbox sighting (the read the Plate review page graded) against "
        "the answer from blind readings on that page. Primary: exact as typed; secondary: within one character, and "
        "exact after `normalise_plate` is applied to the reading. Intervals: Wilson treats every row as independent; "
        "`groups` resamples whole vehicles (`ocr_sets.same_vehicle`: true plates within one edit, or the same camera "
        "within 10 s; 2000 draws).", "",
        f"**The set re-reads the same looping footage as sandbox-blind-v1.** {seen} of {len(rs)} rows are vehicles seen "
        f"in v1 (grouped with a v1 row), {new} are new. Every figure is given for all rows and for new vehicles; "
        "wherever the fresh rate is quoted, the new-vehicle rate goes beside it. It is never pooled with v1.", "",
        "## Conditions", "",
        f"- Build that stored the sightings: {info.get('capture_build', CAPTURE_BUILD)}.",
        f"- Rows: sandbox sightings (camera code `^CAM[0-9]{{2}}$`) with a frame time after "
        f"{FRESH_AFTER:%d %b %H:%M:%S} IST (the last sighting in v1) and at least one reader's blind review by "
        f"{cut:%d %b %H:%M} IST. v1's own sightings stay v1's and are not in this set (v1 sightings after that time: "
        f"{to_v1}; v1's last is at 07:55:27.55). {c['sightings_in_window_with_crop']} fresh sightings had a crop; "
        f"{c['sightings_with_a_reader_review']} had a reader's review; {len(rs)} rows have an answer. Reviews made "
        f"after {cut:%d %b %H:%M} IST are not here: they belong to sandbox-fresh-v2, a separate freeze (not built yet).",
        "- Cameras: " + ", ".join(f"{k} {v} rows" for k, v in sorted(c["cameras"].items())) + ".",
        f"- Capture windows on {', '.join(sorted(cams))} (rotation logs, clipped to the set's span): "
        + ("; ".join(f"{w['start']:%d %b %H:%M}–{w['end']:%H:%M} on one worker with {', '.join(w['cameras'])} "
                     f"(`data/{w['log']}`)" for w in wins) or "none logged") + ".",
        f"- Not in any log (a worker started by hand): {out_n} of {len(rows) + len(left)} rows (answered and left out)"
        + (", stored " + "; ".join(f"{s['start']:%d %b %H:%M}–{s['end']:%H:%M} ("
                                   + ", ".join(f"{k} {v}" for k, v in sorted(s["rows"].items())) + ")" for s in spans)
           + ". These spans run from the first to the last row stored, not the run's own start and end, which were "
             "not logged" if spans else "") + ".",
        "- The laptop was shared with other CPU jobs during the capture (the CAM01-CAM30 rotation for part of it, and "
        "the OCR fine-tune at Idle priority).",
        f"- Readers: reader 1 `admin` (read v1), reader 2 `auditor`. Left out: {left_text(c)}. Reviews ignored: "
        + (", ".join(f"{v} {k}" for k, v in info["ignored_reviews"].items()) or "none") + ".",
        f"- Frozen by the pre-registered deadline (27 Sep 10:00 IST): {'yes' if info.get('frozen_by_deadline') else 'no'}.",
        "",
    ]
    lines += tables(cols)
    lines += [""] + readers_lines({"All rows": c, "New vehicles": c["new_vehicles"]}) + [
              "", f"A row no reader typed a plate for (a hoarding, an unreadable crop) is not a vehicle, so it has no "
              f"seen or new class and is counted under all rows only: {c['left_out_no_plate_typed']} such rows.",
              "", "## Caveats", "",
              "- The answer is a person's reading, not a known plate. On our own plates, where the truth is known, "
              "reader 1 was right 222 times in 226 (`review_truth.md`). A single-reader row rests on one reading.",
              "- A seen vehicle is not blind for a reader who read it in v1: after each typed reading the page reveals "
              "Sentinel's read. That is why new vehicles are reported apart.",
              "- Only stored sightings are in the set: it says nothing about plates Sentinel never stored (capture on "
              "real plates is unmeasured).",
              "- The two cameras replay recorded footage on a loop of unknown length; the rows are not an independent "
              "sample of vehicles.",
              "- A frozen test set: never trained on, never used to tune.", ""]
    res = {"set": name, "generated": datetime.now(IST).isoformat(timespec="seconds"), "freeze": info,
           "capture_windows": [w | {"start": w["start"].isoformat(), "end": w["end"].isoformat()} for w in wins],
           "rows_outside_logged_windows": out_n,
           "unlogged_spans": [{"first_row": s["start"].isoformat(), "last_row": s["end"].isoformat(),
                               "rows": dict(s["rows"])} for s in spans],
           "vehicles": {"seen": seen, "new": new}, "results": cols}
    return "\n".join(lines), res


def v2_report(root: Path) -> tuple[str, dict]:
    name = SETS["v2"][0]
    rows, left, info = load(root, name)
    c, h = info["counts"], info["headline"]
    v1 = read_csv(root / "sandbox-blind-v1" / "manifest.csv")
    frozen = datetime.fromisoformat(info["frozen_ist"])
    rs, ms = recs(rows), misses(left)
    v1r = recs([r | {"conf_band": ""} for r in v1])
    both = sum(r["readers"] == "both" for r in rows)
    col = f"v2 ({both} of {len(rows)} rows read by both readers)"    # a row reader 2 has not read keeps v1's answer
    cols = {col: block(rs, ms)}
    v1m = {m: measure(v1r, m) for m in MEASURES}
    by_id, gone = {r["id"]: r for r in rows}, {r["id"]: r for r in left}
    change = {}
    for label, hit in (("hits", True), ("misses", False)):
        ids = [r for r in v1 if (r["verdict"] == "exact") == hit]
        n = Counter()
        for r in ids:
            x = by_id.get(r["id"])
            n["read by reader 2"] += (x or gone.get(r["id"], {})).get("readers") in ("both", "2")
            if x is None:
                n["left out: " + gone.get(r["id"], {}).get("reason", "not in v2")] += 1
            else:
                n["exact in v2" if x["verdict"] == "exact" else "a miss in v2"] += 1
                n["answer changed"] += x["true_plate"] != r["true_plate"]
        change[label] = {"n": len(ids), **n}
    holds = h["holds_as_far_as_checkable"]
    yn = lambda b: "yes" if b else "no"   # noqa: E731
    lines = [
        f"# sandbox-blind-v1 read again by a second reader: {name}", "",
        f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_fresh.py` from the frozen set "
        f"`data/ocr-eval/{name}` (frozen {frozen:%d %b %Y %H:%M} IST, tooling at git {info['git_head']}). Rules "
        "pre-registered in `bench/pipeline_gates.md`, \"sandbox-blind-v2\". Counts and rates only: no plate text is "
        "written here.", "",
        "v1's answers were one reader's (`admin`). Here a second reader (`auditor`) read v1's 144 sightings blind; "
        "equal readings are the answer, unequal ones were settled by the two readers together from the crop and their "
        "two readings; a disagreement unsettled at the freeze is left out and counted, and a row either reader called "
        "not a plate or unreadable is left out. v1 itself is unchanged.", "",
        "## Headline condition (fixed before the result)", "",
        f"- Frozen by 27 Sep 12:00 IST: {yn(h['frozen_by_deadline'])} ({frozen:%d %b %H:%M} IST).",
        f"- Reader 2 read all {c['v1_source_sightings']} v1 sightings blind: {yn(h['reader2_read_all'])} "
        f"({c['reader2_read']} read; in the page's order: {yn(c['reader2_in_page_order'])}).",
        f"- Every disagreement settled: {yn(h['all_disagreements_settled'])} ({c['unsettled']} unsettled).",
        "- Not checkable by this script, for the team to state: " + "; ".join(h["not_checkable_here"]) + ".",
        f"- **Holds as far as the script can check: {yn(holds)}.** "
        + ("If the team confirms the two points above, the documents give the v2 figure as the headline, with 90 of "
           "120 beside it as one reader's." if holds else
           "90 of 120 stays the quoted figure; v2 is reported from the finale on."), "",
        "## v2 against v1", "",
        f"| | {col} | v1 (one reader) |", "|---|---|---|",
    ]
    for m, label in MEASURES.items():
        lines.append(f"| {label} | {cell(cols[col][m])} | {cell(v1m[m])} |")
    lines.append(f"| Exact as typed, unsettled counted as misses | {cell(cols[col]['exact_unsettled_as_misses'])} | n/a |")
    lines += ["", "What happened to v1's rows in v2. A row reader 2 has not read keeps reader 1's answer and cannot "
              "change, so only the rows read by reader 2 re-check v1:", "",
              "| v1 | Rows | Read by reader 2 | Exact in v2 | A miss in v2 | Left out of v2 | Answer changed |",
              "|---|---|---|---|---|---|---|"]
    for label, x in change.items():
        out = {k[len("left out: "):]: v for k, v in x.items() if k.startswith("left out: ")}
        lines.append(f"| {label} | {x['n']} | {x.get('read by reader 2', 0)} | {x.get('exact in v2', 0)} | "
                     f"{x.get('a miss in v2', 0)} | "
                     f"{sum(out.values())}{' (' + ', '.join(f'{v} {k}' for k, v in out.items()) + ')' if out else ''} | "
                     f"{x.get('answer changed', 0)} |")
    lines += ["", f"Left out of v2 overall: {left_text(c)}. Reviews ignored: "
              + (", ".join(f"{v} {k}" for k, v in info["ignored_reviews"].items()) or "none") + ".", ""]
    lines += tables(cols)
    lines += [""] + readers_lines({"All rows": c}) + ["", "## Caveats", "",
              "- Reader 1 saw Sentinel's read after typing each v1 plate (the page reveals it once a reading is "
              "typed), so when the two readers settled a disagreement, reader 1's side was not free of that memory.",
              "- The answer is still people's reading, not a known plate. A second pass by reader 1 would be a re-read "
              "by the same person and would change nothing.",
              "- Only stored sightings: nothing about plates Sentinel never stored.",
              "- A frozen test set: never trained on, never used to tune.", ""]
    res = {"set": name, "generated": datetime.now(IST).isoformat(timespec="seconds"), "freeze": info,
           "results": {"v2": cols[col]}, "rows_read_by_both": both, "v1": v1m, "changes_from_v1": change}
    return "\n".join(lines), res


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Report a frozen fresh sandbox set (counts and rates only).")
    ap.add_argument("set", choices=list(SETS))
    ap.add_argument("--manifest-root", default=str(ROOT / "data" / "ocr-eval"))
    ap.add_argument("--logs-root", default=str(ROOT / "data"), help="where the rotation*/rotation.csv logs are")
    ap.add_argument("--out", help="the .md path (a .json is written beside it); default bench/results/<name>.md")
    a = ap.parse_args(argv)
    root = Path(a.manifest_root)
    md, res = fresh_report(root, Path(a.logs_root)) if a.set == "fresh" else v2_report(root)
    out = Path(a.out) if a.out else ROOT / "bench" / "results" / f"{SETS[a.set][1]}.md"
    out.write_text(md, encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote", out, "and .json")


if __name__ == "__main__":
    main()
