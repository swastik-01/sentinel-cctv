"""Replay own-feed track logs under other tracker rules: which plate would each rule have stored?

Why: several changes in `bench/results/pipeline_review.md` touch only the tracker's rules (tracker.py): how many reads
a track waits for, how the vote picks a length and weighs reads, when one read is enough, and which confidence goes on
the sighting. A TRACK_LOG (every harvested track with all its reads, in arrival order) holds everything those rules
see, so they can be compared offline on the same reads, with no worker, GPU or camera, against the plates the
simulator painted on the stock-footage cameras (AMD-TRAF-001/002). The drawn cameras are left out: their vehicles
loop through the view without a gap, so their reads do not split into passes.

A vehicle pass: the worker closes a track at 3 reads (CONFIRM_READS) and the vehicle's later reads start new tracks,
which the repeat filter then drops unless they read differently. Consecutive tracks on one camera whose plates are at
most two edits apart and whose best reads are at most GAP_S apart are chained into one pass; the chain's reads, in
order, are what a longer track would have seen. The shipped rule is replayed as the worker runs it (a vote over each
3-read track, then the 8 s repeat filter with its one-substitution fold), so its sightings include the extra ones a
pass produces when a later track reads differently.

A lower analysis rate is imitated by keeping every 2nd or 3rd read of a pass (about 2.3 or 1.5 frames per second from
the logs' ~4.5), every offset counted as one trial. That thins reads, not frames: a frame that gave no valid read
is not in the log. The sandbox cameras were analysed at a median 1.6 frames per second (`pipeline_diag.md`).

Own feeds only: TRACK_LOG is never turned on for the organisers' sandbox, and sandbox camera codes are refused.
Plate text stays in memory; the report holds counts and rates only.

    PYTHONUTF8=1 uv run --no-sync python bench/track_replay.py data/track-logs/*.jsonl [--out bench/results/track_replay.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

from sentinel_analytics.tracker import levenshtein, vote
from sentinel_common import looks_like_indian_plate, normalise_plate

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
_spec = importlib.util.spec_from_file_location("anpr_eval", ROOT / "scripts" / "anpr_eval.py")
anpr_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anpr_eval)

GAP_S = 2.0          # next track of the same pass: best reads this close (the logs' tracks are ~0.7 s apart)
WINDOW_S = 8.0       # DEDUP_SECONDS
CONFIRM = 3          # CONFIRM_READS
SINGLE_CONF = 0.6    # SINGLE_READ_CONF, below SLOW_FPS
REF_FPS = 4.5        # analysed frames per second per camera in the logged runs (their 30 s status lines)
STOCK = ("AMD-TRAF-001", "AMD-TRAF-002")
SANDBOX = re.compile(r"^CAM\d{2}$")


# ------------------------------------------------------------------ rules
def best_read(reads: list) -> tuple[str, float]:
    """The worker's best read: the first read with the highest confidence (a later read must beat it strictly)."""
    b = reads[0]
    for r in reads[1:]:
        if r[1] > b[1]:
            b = r
    return b


def vote_by(reads: list, weight=lambda c: max(c, 0.05), length: str = "count") -> str:
    """tracker.vote with the length rule and the read weight as parameters. length='count' is the shipped rule (most
    reads, a tie going to the length read first); 'weight' breaks a tie by summed weight instead."""
    n, w = Counter(), defaultdict(float)
    for p, c in reads:
        n[len(p)] += 1
        w[len(p)] += weight(c)
    L = n.most_common(1)[0][0] if length == "count" else max(n, key=lambda k: (n[k], w[k]))
    same = [(p, c) for p, c in reads if len(p) == L]
    out = []
    for i in range(L):
        pos: dict[str, float] = defaultdict(float)
        for p, c in same:
            pos[p[i]] += weight(c)
        out.append(max(pos.items(), key=lambda kv: kv[1])[0])
    return "".join(out)


def stored(reads: list, voted: str | None = None) -> str:
    """What harvest() stores: the vote if it is a valid plate, else the best single read."""
    v = normalise_plate(vote(reads)[0] if voted is None else voted)
    return v if looks_like_indian_plate(v) else normalise_plate(best_read(reads)[0])


def stored_conf(reads: list) -> float:
    """harvest()'s confidence: the best read's, raised to 0.6 + 0.1 x reads (at most 0.99) when 3+ reads agree."""
    _, agreement = vote(reads)
    c = best_read(reads)[1]
    if len(reads) >= 3 and agreement >= 0.99:
        c = max(c, min(0.99, 0.6 + 0.1 * len(reads)))
    return round(c, 3)


# ------------------------------------------------------------------ data
def load(paths: list[str]) -> dict[str, list[dict]]:
    by_cam: dict[str, list[dict]] = defaultdict(list)
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            if SANDBOX.match(t["camera"]):
                raise SystemExit(f"{p}: a sandbox camera's track log. TRACK_LOG is for our own feeds only.")
            if t["camera"] not in STOCK:
                continue
            t["reads"] = [(str(a), float(b)) for a, b in t["reads"]]
            t["run"] = Path(p).name
            by_cam[t["camera"]].append(t)
    for ts in by_cam.values():
        ts.sort(key=lambda t: (t["run"], t["ts"]))
    return by_cam


def chains(tracks: list[dict]) -> list[list[dict]]:
    """Tracks of one vehicle pass: same run, next best read within GAP_S of the pass's last, plate within 2 edits of
    the pass's first track (the closest open pass wins; several vehicles can be in view at once)."""
    open_: list[list[dict]] = []
    done: list[list[dict]] = []
    for t in tracks:
        t["plate"] = stored(t["reads"])
        still = []
        for c in open_:
            (still if c[-1]["run"] == t["run"] and t["ts"] - c[-1]["ts"] <= GAP_S else done).append(c)
        open_ = still
        cand = [(levenshtein(c[0]["plate"], t["plate"], cap=2), i) for i, c in enumerate(open_)]
        cand = [x for x in cand if x[0] <= 2]
        if cand:
            open_[min(cand)[1]].append(t)
        else:
            open_.append([t])
    return done + open_


def shipped_sightings(tracks: list[dict]) -> list[dict]:
    """The worker's repeat filter over one camera's tracks, in time order (tracker.harvest)."""
    emitted: dict[str, float] = {}
    out = []
    for t in tracks:
        key = t["plate"]
        if key not in emitted:
            key = next((p for p, last in emitted.items() if len(p) == len(key) and t["ts"] - last <= WINDOW_S
                        and levenshtein(p, key, cap=1) <= 1), key)
        last = emitted.get(key)
        if last is None or t["ts"] - last > WINDOW_S:
            out.append(t)
        emitted[key] = max(last or 0.0, t["ts"])
    return out


def logged(paths: list[str]) -> str:
    """Sightings the worker logged on the stock-footage cameras in the same runs, if its log sits beside the track log."""
    line = re.compile(r"sentinel\.worker: (AMD-TRAF-00[12]): \S+ \(ocr ")
    logs = [Path(p).with_suffix(".worker.log") for p in paths]
    if not all(f.exists() for f in logs):
        return "no count (a worker log is missing)"
    return str(sum(bool(line.search(x)) for f in logs for x in f.read_text(encoding="utf-8", errors="replace").splitlines()))


# ------------------------------------------------------------------ report helpers
def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "n/a"


def table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "track_replay.md"))
    a = ap.parse_args()
    cams = {c["code"]: c for c in yaml.safe_load((ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]}
    by_cam = load(a.logs)
    truth = {c: set(anpr_eval.load_truth(cams[c])["plates"]) for c in by_cam}
    order = [c for c in STOCK if c in by_cam]
    passes = {}
    for cam in order:
        runs = defaultdict(list)
        for t in by_cam[cam]:
            runs[t["run"]].append(t)
        passes[cam] = [c for ts in runs.values() for c in chains(ts)]
        for ts in runs.values():
            for t in shipped_sightings(ts):
                t["emitted"] = True

    L = ["# Tracker rules replayed on our own feeds' track logs", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/track_replay.py` from "
         f"{', '.join(f'`{Path(p).name}`' for p in a.logs)} (TRACK_LOG of two 5-minute worker runs on 24 Sep 2026, "
         "01:16-01:27 IST: 4 cameras on one worker, GTX 1650 Ti laptop, object detection on, about 4.5 analysed frames "
         "per second per camera, software then hardware decode; the tracks behind `plate_choice.md`). No worker, GPU or "
         "camera was used. Stock-footage cameras AMD-TRAF-001 (PTZ view, plates read at a median 55 px wide) and "
         "AMD-TRAF-002 (ANPR view, ~100 px). Exact = the stored plate is one of the camera's painted registrations. "
         "**Synthetic registrations in one clean font painted on Pexels stock footage, not real Gujarat plates.** "
         "Counts and rates only.", "",
         f"A pass is the chain of tracks one vehicle produced (same camera, plates within 2 edits, best reads within "
         f"{GAP_S:g} s); see the docstring. Check on the replay: from the same reads, it stores "
         f"{sum(len([t for c in passes[x] for t in c if t.get('emitted')]) for x in order)} sightings on these two "
         f"cameras; the worker's own logs of the runs (`*.worker.log` beside each track log) show {logged(a.logs)}.", ""]

    def first_sighting(c: list[dict]) -> str | None:
        return next((t["plate"] for t in c if t.get("emitted")), None)

    # 1. passes and the shipped rule
    rows = []
    for cam in order:
        P = passes[cam]
        n_reads = [sum(len(t["reads"]) for t in c) for c in P]
        emitted = [t for c in P for t in c if t.get("emitted")]
        with_sighting = sum(first_sighting(c) is not None for c in P)
        rows.append([cam, len(P), f"{np.median(n_reads):.0f} / {np.percentile(n_reads, 90):.0f}",
                     len(emitted), pct(sum(t["plate"] in truth[cam] for t in emitted), len(emitted)),
                     len(emitted) - with_sighting, pct(sum(first_sighting(c) in truth[cam] for c in P), len(P))])
    L += ["## 1. The shipped rule: sightings per pass", "",
          "The shipped tracker stores each track's vote as soon as it has 3 reads (or its hold of about 1 s ends with "
          "2); the pass's later tracks are dropped as repeats unless they read two or more characters differently (or "
          "one dropped or added), and then the same vehicle is stored again.", ""]
    L += table(["Camera", "Passes", "Reads per pass, median / p90", "Sightings stored", "Sightings exact",
                "Extra sightings of a pass already stored", "Passes whose first sighting is exact"], rows) + [""]

    # 2. more reads per pass
    def k_rule(c: list[dict], k: int | None, **kw) -> str:
        reads = [r for t in c for r in t["reads"]][:k]
        return stored(reads, vote_by(reads, **kw) if kw else None)

    rules = {"first 3 reads of the pass": dict(k=3), "first 5 reads": dict(k=5), "first 7 reads": dict(k=7),
             "whole pass": dict(k=None), "whole pass, length tie by weight": dict(k=None, length="weight"),
             "whole pass, equal weights": dict(k=None, weight=lambda c: 1.0),
             "whole pass, confidence squared": dict(k=None, weight=lambda c: max(c, 0.05) ** 2)}
    rows = [["shipped (first sighting of the pass)"]
            + [pct(sum(first_sighting(c) in truth[cam] for c in passes[cam]), len(passes[cam])) for cam in order]
            + ["-", "-"]]
    for name, kw in rules.items():
        cells, fx, br = [], 0, 0
        for cam in order:
            ok = 0
            for c in passes[cam]:
                new, old = k_rule(c, **kw) in truth[cam], first_sighting(c) in truth[cam]
                ok += new
                fx += new and not old
                br += old and not new
            cells.append(pct(ok, len(passes[cam])))
        rows.append([name] + cells + [fx, br])
    L += ["## 2. One plate per pass, voted over more of its reads", "",
          f"Exact passes when each pass stores one plate, voted over its first k reads; fixes and breaks are paired "
          f"against the shipped first sighting, both cameras together. At about {REF_FPS:g} analysed frames per second, "
          f"k reads arrive about (k - 1) / {REF_FPS:g} s after the first (3 reads ~0.4 s, 5 ~0.9 s, 7 ~1.3 s); the "
          "whole pass waits until the vehicle has left.", ""]
    L += table(["Rule"] + order + ["fixes", "breaks"], rows) + [""]
    L += ["A late correction (store the first track as now, so alerts keep their latency, then correct the sighting "
          "when the pass ends if the whole-pass vote differs) is the `whole pass` row's fixes and breaks.", ""]

    # 3. lower analysis rate
    L += ["## 3. At a lower analysis rate", "",
          "Every s-th read of a pass is kept (s = 1, 2, 3: about 4.5, 2.3 and 1.5 analysed frames per second), each "
          "offset one trial. The first track is the first 3 kept reads. The shipped worker stores a one-read track only "
          "below 2 analysed frames per second (`SLOW_FPS`) and only at confidence >= 0.6 (`SINGLE_READ_CONF`); the other "
          "rows are alternatives. Capture = trials whose pass stored an exact plate, over passes the worker stored at "
          "4.5 (a vehicle read once at 4.5 is not in the log: the worker drops such a track before logging it); "
          "precision = exact over trials that stored a plate.", ""]
    rows = []
    for s, single, note in ((1, None, "shipped"), (2, None, "shipped"), (2, 0.9, "alternative"),
                            (3, SINGLE_CONF, "shipped"), (3, 0.8, "alternative"), (3, 0.9, "alternative"),
                            (3, None, "alternative")):
        for cam in order:
            trials = stored_n = exact = single_n = single_ok = 0
            for c in passes[cam]:
                reads = [r for t in c for r in t["reads"]]
                for o in range(s):
                    first = reads[o::s][:CONFIRM]
                    trials += 1
                    if not first or (len(first) == 1 and (single is None or first[0][1] < single)):
                        continue
                    ok = stored(first) in truth[cam]
                    stored_n += 1
                    exact += ok
                    if len(first) == 1:
                        single_n += 1
                        single_ok += ok
            rows.append([f"{REF_FPS / s:.1f}", f"{'never' if single is None else f'>= {single:g}'} ({note})", cam,
                         trials, pct(exact, trials), pct(exact, stored_n), pct(single_ok, single_n) if single_n else "-"])
    L += table(["Frames per second (approx.)", "One-read track stored at", "Camera", "Trials", "Capture", "Precision",
                "Exact among one-read sightings"], rows) + [""]

    # 4. confidence routing
    L += ["## 4. Which sightings could skip review", "",
          "An auto band is the set of stored sightings trusted without a person; the rest would go to review. First "
          "track of each pass (the plate the shipped worker stores first), both cameras together; at 1.5 the shipped "
          "one-read rule (>= 0.6) applies.", ""]
    rows = []
    for s in (1, 3):
        recs = []
        for cam in order:
            for c in passes[cam]:
                reads = [r for t in c for r in t["reads"]]
                for o in range(s):
                    first = reads[o::s][:CONFIRM]
                    if not first or (len(first) == 1 and (s < 3 or first[0][1] < SINGLE_CONF)):
                        continue
                    p = stored(first)
                    agree = sum(normalise_plate(x) == p for x, _ in first)
                    recs.append((p in truth[cam], stored_conf(first), len(first), agree))
        bands = {"stored confidence >= 0.9 (as the review page bands it)": lambda r: r[1] >= 0.9,
                 "stored confidence >= 0.9 and 2+ reads": lambda r: r[1] >= 0.9 and r[2] >= 2,
                 "2+ reads equal to the stored plate": lambda r: r[3] >= 2,
                 "3 reads, all equal": lambda r: r[2] >= 3 and r[3] == r[2]}
        for name, f in bands.items():
            hi = [r for r in recs if f(r)]
            lo = [r for r in recs if not f(r)]
            rows.append([f"{REF_FPS / s:.1f}", name, pct(len(hi), len(recs)), pct(sum(r[0] for r in hi), len(hi)),
                         pct(sum(r[0] for r in lo), len(lo))])
    L += table(["Frames per second (approx.)", "Auto band", "Sightings in band", "Exact in band", "Exact below band"],
               rows) + [""]

    # 5. length ties inside the shipped track
    tie = Counter()
    for cam in order:
        for t in by_cam[cam]:
            n = Counter(len(p) for p, _ in t["reads"]).most_common()
            if len(n) > 1 and n[0][1] == n[1][1]:
                tie["tracks"] += 1
                a_, b_ = t["plate"], stored(t["reads"], vote_by(t["reads"], length="weight"))
                if a_ != b_:
                    tie["fixes" if b_ in truth[cam] and a_ not in truth[cam] else
                        "breaks" if a_ in truth[cam] and b_ not in truth[cam] else "other change"] += 1
    total = sum(len(v) for v in by_cam.values())
    L += ["## 5. Length ties in one track", "",
          f"Tracks whose reads split evenly between two lengths (the shipped vote then takes the length read first): "
          f"{tie['tracks']} of {total}. Breaking the tie by summed confidence instead: {tie['fixes']} fixes, "
          f"{tie['breaks']} breaks, {tie['other change']} other changes. The painted plates are clean and nearly all "
          "the same length, so ties are rare here; on real plates a dropped character was 7 of 19 standard-layout "
          "misses (`pipeline_diag.md`).", ""]

    L += ["## Caveats", "",
          "- Synthetic registrations in one clean font (painted on Pexels stock footage, or drawn): real plates' errors "
          "are not in these reads, and accuracy here sits near its ceiling on AMD-TRAF-002. Compare rules with each "
          "other, not with the sandbox.",
          "- Passes are rebuilt from the tracks' best-read times; a read's own time is not logged. Two vehicles with "
          "plates two edits apart in view together would be one pass (the painted plates are chosen to differ more).",
          "- Section 3 thins reads, not frames, and ignores the longer hold at a low rate; it is an estimate of the "
          "direction, to be confirmed with a live run at DETECT_FPS=1.5 (TRACK_LOG on, own feeds only).",
          "- The logs are from the 24 Sep worker (before the not-a-plate rule and the fixed-text rule); neither changes "
          "a painted plate's reads.", ""]
    text = "\n".join(L)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
