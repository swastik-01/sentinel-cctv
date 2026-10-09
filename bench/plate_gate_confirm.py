"""Stage A (rule 1e-k2) confirmation: gates A0-A4 of bench/plate_gate_gates.md, checked as written there from the
outputs of the runs they name. Counts only: no plate text is read into or written by this script.

    PYTHONUTF8=1 uv run --no-sync python bench/plate_gate_confirm.py --dir <run dir> [--out bench/results/plate_gate_confirm.md]

The run dir holds what the gate runs wrote; every .log starts and ends with a `date +%FT%T%z` line, and the last one
is when that check finished (A4):
  frozen.json, frozen.log   bench/plate_gate.py with its default seeds 7 and 11 (A0, A1)
  fresh.json, fresh.log     bench/plate_gate.py --seeds 101 202 303 (A2)
  pytest.log (pytest -q), pytest_new.log (the new test file, -rA), smoke.log (--skip-fleet), security.log
  worker.log, worker.env    the 10-minute worker run and its settings (KEY=value lines)
  anpr.md                   scripts/anpr_eval.py for that window; it lists wrong reads, so it stays in the run dir

Also, not a registered gate: the product helper against an independent count (digits of the cleaned read that are
letters in normalise_plate's output) on generated strings, so A0 does not rest only on the replay in plate_gate.py,
which calls the same repair functions as the helper.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sentinel_common import letters_from_digits, normalise_plate
from sentinel_common.plates import _clean

ROOT = Path(__file__).resolve().parents[1]
RULE = "1e-k2"
IST = timezone(timedelta(hours=5, minutes=30))
DEADLINE = datetime(2026, 9, 27, 12, 0, tzinfo=IST)
A0_SOURCES = ("reject-v1", "sandbox-v1", "ownfeed-v1", "stored sightings", "synthetic plates", "probe seed 7",
              "probe seed 11")
FRESH_SEEDS = (101, 202, 303)
NEW_TESTS = {   # A3's required unit tests -> the test in services/analytics/tests/test_not_a_plate.py
    "a digits-only phone-number read is dropped": "test_a_phone_number_passes_the_old_gate_but_is_dropped",
    "an exact GJ plate is kept": "test_an_exact_gj_plate_is_kept",
    "a GJ plate with one state letter read as a digit is kept": "test_one_state_letter_read_as_a_digit_is_kept",
    "an exact BH plate and a BH plate with one misread are kept": "test_bh_plates_are_kept",
    "a read whose two state letters are both digits is dropped": "test_both_state_letters_from_digits_are_dropped",
    "the known cost (two series letters read as digits) is dropped": "test_known_cost_two_series_letters_read_as_digits_are_dropped",
}


def finished(log: Path) -> datetime:
    stamps = re.findall(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}$", log.read_text(encoding="utf-8"), re.M)
    return datetime.strptime(stamps[-1], "%Y-%m-%dT%H:%M:%S%z")


def exit_code(log: Path) -> int | None:
    m = re.findall(r"^exit=(\d+)$", log.read_text(encoding="utf-8"), re.M)
    return int(m[-1]) if m else None


def row(what: str, threshold: str, measured: str, ok: bool) -> dict:
    return {"what": what, "threshold": threshold, "measured": measured, "pass": ok}


def gate_a0(res: dict, log: Path) -> list[dict]:
    out = []
    for src in A0_SOURCES:
        p = res["parity"].get(src, {})
        n, h, nz = p.get("reads", 0), p.get("helper_vs_replay"), p.get("normalise_vs_replay")
        out.append(row(f"{src}: helper vs replay / normalise_plate vs replay", "0 / 0 mismatches on every read",
                       f"{h} / {nz} of {n:,} reads", n > 0 and h == 0 and nz == 0))
    code = exit_code(log)
    out.append(row("bench/plate_gate.py exit code", "0 (it exits 1 on any parity mismatch)", str(code), code == 0))
    return out


def gate_a1(res: dict) -> list[dict]:
    s, lab, sp = res["sets"], res["labels"], res["synth_plates"]
    r = {k: v["rules"][RULE] for k, v in s.items()}
    lr, sr = lab["rules"][RULE], sp["rules"][RULE]

    def at_most(what, got, of, want_of, most):
        return row(what, f"<= {most} of {want_of:,}", f"{got} of {of:,}", of == want_of and got <= most)

    return [
        row("reject-v1 caught", "23 of 23", f"{r['reject-v1']['rejected']} of {s['reject-v1']['gate']}",
            s["reject-v1"]["gate"] == 23 and r["reject-v1"]["rejected"] == 23),
        row("stored not_a_plate dropped", "24 of 24", f"{lr.get('not_a_plate', 0)} of {lab['gate'].get('not_a_plate', 0)}",
            lab["gate"].get("not_a_plate") == 24 and lr.get("not_a_plate") == 24),
        at_most("sandbox-v1 exact reads lost", r["sandbox-v1"]["exact_lost"], s["sandbox-v1"]["gate_exact"], 25, 0),
        at_most("stored sightings exact lost", lr.get("exact", 0), lab["gate"].get("exact", 0), 92, 0),
        at_most("stored sightings one-off lost", lr.get("one_off", 0), lab["gate"].get("one_off", 0), 4, 0),
        at_most("ownfeed-v1 exact reads lost", r["ownfeed-v1"]["exact_lost"], s["ownfeed-v1"]["gate_exact"], 5307, 4),
        at_most("ownfeed-v1 vehicles gone", r["ownfeed-v1"]["groups_all_rejected"],
                r["ownfeed-v1"]["groups_with_gate"], 128, 0),
        at_most("synthetic held-out GJ exact lost", sr.get("GJ", 0), sp["gate_exact"].get("GJ", 0), 1391, 1),
        at_most("synthetic held-out other states exact lost", sr.get("other", 0), sp["gate_exact"].get("other", 0), 180, 0),
        at_most("synthetic held-out BH exact lost", sr.get("BH", 0), sp["gate_exact"].get("BH", 0), 152, 0),
    ]


def gate_a2(res: dict, log: Path) -> tuple[list[dict], list[dict]]:
    probes = {p["seed"]: p for p in res["probe"]}
    out, table, gate_sum, rule_sum = [], [], 0, 0
    for seed in FRESH_SEEDS:
        p = probes.get(seed)
        if not p:
            out.append(row(f"seed {seed}", "run", "missing", False))
            continue
        n, g, k = sum(p["n"].values()), sum(p["gate"].values()), sum(p["rules"][RULE].values())
        gate_sum, rule_sum = gate_sum + g, rule_sum + k
        table.append({"seed": seed, "n": n, "per_kind": p["per_kind"], "gate": g, "rule": k,
                      "kinds": {kind: (p["gate"].get(kind, 0), p["rules"][RULE].get(kind, 0)) for kind in p["n"]}})
        out.append(row(f"seed {seed}: crops still passing with the rule", "<= 5 of 2,400 (300 per kind)",
                       f"{k} of {n:,} ({p['per_kind']} per kind; current gate {g})",
                       n == 2400 and p["per_kind"] == 300 and k <= 5))
    share = f"{100 * rule_sum / gate_sum:.1f}%" if gate_sum else "n/a (the gate passed none)"
    out.append(row("three seeds: rule passes as a share of current-gate passes", "<= 20%",
                   f"{share} ({rule_sum} of {gate_sum})", 5 * rule_sum <= gate_sum))
    fresh_par = [f"{s}: {v['helper_vs_replay']} / {v['normalise_vs_replay']} of {v['reads']:,}"
                 for s, v in res["parity"].items() if s.startswith("probe seed")]
    ok = all(v["helper_vs_replay"] == 0 and v["normalise_vs_replay"] == 0 for v in res["parity"].values())
    out.append(row("parity on the fresh run (not registered; every source it read)", "0 / 0",
                   "; ".join(fresh_par) + ("" if ok else " (and a mismatch elsewhere)"), ok and exit_code(log) == 0))
    return out, table


def frozen_numbers(res: dict) -> dict:
    """The A1 counts only, to compare the two runs (they re-score the same frozen sets)."""
    return {"sets": {k: v["rules"][RULE] | {"gate": v["gate"], "gate_exact": v["gate_exact"]} for k, v in res["sets"].items()},
            "labels": [res["labels"]["gate"], res["labels"]["rules"][RULE]],
            "synth": [res["synth_plates"]["gate_exact"], res["synth_plates"]["rules"][RULE]]}


def independent_count(n: int, seed: int) -> dict:
    """letters_from_digits against the digits of the cleaned read that are letters in normalise_plate's output,
    on generated strings shaped like plates, BH plates and signage (made up here, never saved)."""
    rng = random.Random(seed)
    look = "0123456789OQDILZSBGTAJUVWRPCEFMNKXYH"      # digits and the letters normalise_plate repairs

    def ch(kind):
        if rng.random() < 0.25:
            return rng.choice(look)
        return rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ" if kind == "L" else "0123456789")

    shapes = ["LLDDLDDDD", "LLDDLLDDDD", "LLDDLLLDDDD", "DDLLDDDDL", "DDLLDDDDLL", "DDDDDDDDDD", "DDDDDDDD"]
    res = {"strings": n, "mismatch": 0, "count_ge2": 0, "count_1": 0}
    for _ in range(n):
        shape = rng.choice(shapes) if rng.random() < 0.8 else "".join(rng.choice("LD") for _ in range(rng.randint(4, 13)))
        raw = "".join(ch(k) for k in shape)
        if rng.random() < 0.2:
            cut = rng.randint(1, len(raw) - 1)
            raw = raw[:cut] + rng.choice(" -.") + raw[cut:]
        c, norm = _clean(raw), normalise_plate(raw)
        want = sum(a.isdigit() and b.isalpha() for a, b in zip(c, norm)) if len(c) == len(norm) else -1
        got = letters_from_digits(raw)
        res["mismatch"] += got != want
        res["count_ge2"] += got >= 2
        res["count_1"] += got == 1
    return res


def gate_a3(d: Path) -> tuple[list[dict], dict]:
    out = []
    t = (d / "pytest.log").read_text(encoding="utf-8")
    m = re.search(r"(\d+) passed", t)
    bad = re.search(r"\d+ (failed|error)", t)
    out.append(row("pytest -q", "passes", f"{m.group(1) if m else 0} passed, {'failures' if bad else '0 failed'}, "
                   f"exit {exit_code(d / 'pytest.log')}", bool(m) and not bad and exit_code(d / "pytest.log") == 0))
    nt = (d / "pytest_new.log").read_text(encoding="utf-8")
    missing = [need for need, name in NEW_TESTS.items() if f"PASSED services/analytics/tests/test_not_a_plate.py::{name}" not in nt]
    out.append(row("the six required unit tests exist and pass", "6 of 6", f"{6 - len(missing)} of 6", not missing))
    for name, log, want in (("smoke.py --skip-fleet", "smoke.log", 34), ("security_checks.py", "security.log", 19)):
        t = (d / log).read_text(encoding="utf-8")
        p, s, f = (len(re.findall(rf"^\s*\[{k}\]", t, re.M)) for k in ("PASS", "SKIP", "FAIL"))
        allp = bool(re.search(r"^ALL PASSED$", t, re.M))
        out.append(row(name, f"{want}/{want}, ALL PASSED", f"{p + s}/{want} ({p} pass, {s} skip, {f} fail), "
                       f"{'ALL PASSED' if allp else 'not all passed'}", p + s == want and f == 0 and allp))
    env = dict(ln.split("=", 1) for ln in (d / "worker.env").read_text(encoding="utf-8").splitlines() if "=" in ln)
    wl = (d / "worker.log").read_text(encoding="utf-8", errors="replace")
    errors = len(re.findall(r" (ERROR|CRITICAL) |Traceback", wl))
    decode = sorted(set(re.findall(r": connected \d+x\d+ @ [\d.]+ fps, (\S+) decode", wl)))
    status = re.findall(r"(\d+)/(\d+) streams up \| analysed ([\d.]+) fps total", wl)
    drops = re.findall(r"reads dropped as not a plate \(\d\+ letters made from digits\), of reads passing the gate: (.*)$",
                       wl, re.M)
    out.append(row("worker run: errors in its log", "no worker error", f"{errors} ERROR/CRITICAL/Traceback lines", errors == 0))
    a = (d / "anpr.md").read_text(encoding="utf-8")
    pool = re.search(r"^\| \*\*All \d+ stock footage cameras, pooled\*\* \|[^|]*\|[^|]*\|[^|]*\|[^|]*\| (\d+) \| [\d.]+% \((\d+)/(\d+)\)", a, re.M)
    traf = re.search(r"^\| AMD-TRAF-002 \|(?:[^|]*\|){7} [\d.]+% \((\d+)/(\d+)\)", a, re.M)   # 8th: shown >= 1 s
    window = re.search(r"--since (\S+) --until (\S+)", a)
    if pool:
        ex, n = int(pool.group(2)), int(pool.group(3))
        out.append(row("anpr_eval: pooled stock-footage exact", ">= 93.0%", f"{100 * ex / n:.1f}% ({ex}/{n})",
                       ex * 1000 >= 930 * n))
    else:
        out.append(row("anpr_eval: pooled stock-footage exact", ">= 93.0%", "no pooled row", False))
    if traf:
        c, v = int(traf.group(1)), int(traf.group(2))
        out.append(row("anpr_eval: AMD-TRAF-002 capture, plates shown >= 1 s", ">= 58 of 68", f"{c} of {v}",
                       v == 68 and c >= 58))
    else:
        out.append(row("anpr_eval: AMD-TRAF-002 capture, plates shown >= 1 s", ">= 58 of 68", "no row", False))
    per_cam = re.findall(r"^\| (AMD-[A-Z]+-\d+) \|(?:[^|]*\|){4} (\d+) \| ([\d.]+% \(\d+/\d+\)) \|(?:[^|]*\|){1} "
                         r"([^|]+) \|", a, re.M)
    info = {"env": env, "decode": decode, "last_status": status[-1] if status else None,
            "status_lines": len(status), "fps": [s[2] for s in status], "drops": drops[-1] if drops else "none logged",
            "window": window.groups() if window else None, "per_cam": per_cam,
            "stale": "**Warning:**" in a, "cameras": len(env.get("CAMERAS", "").split(","))}
    return out, info


def markdown(res: dict) -> str:
    g, c = res["gates"], res["conditions"]
    L = ["# Not-a-plate gate, Stage A (rule `1e-k2`): confirmation", "",
         f"Generated {res['generated']} by `bench/plate_gate_confirm.py`, from the runs that gates A0-A3 of "
         "`bench/plate_gate_gates.md` (written 26 Sep 10:45 IST) name, checked as written there. The gates were not "
         "changed. Counts only: no plate text is written here.", "",
         f"Conditions: OCR `{c['ocr_model']}` on CPU ({c['threads']} threads), `min_ocr_conf` {c['min_ocr_conf']}; "
         f"`MAX_LETTERS_FROM_DIGITS` {c['max_letters_from_digits']} (the rule on). Worker run: {c['worker']}.", "",
         f"**Verdict: {res['verdict']}.** " + res["verdict_line"], "",
         "| Gate | Check | Threshold | Measured | Result | Finished (IST) |", "|---|---|---|---|---|---|"]
    for name in ("A0", "A1", "A2", "A3"):
        for i, r in enumerate(g[name]["rows"]):
            L.append(f"| {name if i == 0 else ''} | {r['what']} | {r['threshold']} | {r['measured']} | "
                     f"{'PASS' if r['pass'] else 'FAIL'} | {g[name]['finished'] if i == 0 else ''} |")
    a4 = g["A4"]
    L.append(f"| A4 | A0-A3 all green by the deadline | by {a4['deadline']} | last gate finished {a4['last']} | "
             f"{'PASS' if a4['pass'] else 'FAIL'} | |")
    L += ["", "## A2: fresh probe, per kind", "",
          "Crops passing the current gate / still passing with the rule, 300 crops per kind; the kinds and renderer are "
          "`bench/plate_gate.py`'s probe (DejaVu Sans Bold, Arial Bold, Bahnschrift), seeds first run here.", ""]
    t = res["fresh_probe"]
    if t:
        kinds = list(t[0]["kinds"])
        L += ["| Seed | " + " | ".join(kinds) + " | all |", "|---|" + "---|" * (len(kinds) + 1)]
        for s in t:
            L.append(f"| {s['seed']} | " + " | ".join(f"{s['kinds'][k][0]} / {s['kinds'][k][1]}" for k in kinds)
                     + f" | {s['gate']} / {s['rule']} |")
    ind, rep = res["independent"], res["second_reproduction"]
    info = res["worker_info"]
    L += ["", "## Not registered: extra checks", "",
          f"- Independent count: on {ind['strings']:,} generated strings (plate-, BH- and number-shaped, with "
          "look-alike characters and separators; made up, never saved), `letters_from_digits` against the digits of the "
          f"cleaned read that are letters in `normalise_plate`'s output: {ind['mismatch']} mismatches "
          f"({ind['count_ge2']:,} strings counted 2 or more, {ind['count_1']:,} counted 1).",
          f"- The fresh-probe run re-scored the frozen sets: its A1 counts are {rep} to the A1 run's.",
          "- Worker run, per camera (sightings, exact, capture of plates shown >= 1 s): "
          + "; ".join(f"{cam} {n}, {ex}, {cap.strip()}" for cam, n, ex, cap in info["per_cam"]) + ".",
          f"- Worker log: last status {info['last_status'][0]}/{info['last_status'][1]} streams up; analysed fps "
          f"summed over the cameras, per 30 s status line ({info['status_lines']} lines): "
          f"{', '.join(info['fps'])} (`anpr_eval_current.md` had about 4.5 per camera, 18 summed); "
          f"decode {', '.join(info['decode']) or 'not logged'}; reads the rule dropped, last log line (camera "
          f"dropped/passing the gate): {info['drops']}." if info["last_status"] else "- Worker log: no status line.",
          "", "## Caveats", "",
          "- A3's live run is a wiring check, not a measurement of the rule (`bench/plate_gate_gates.md`): the "
          "stock-footage plates are synthetic registrations painted on Pexels footage, and the drawn cameras show "
          "drawn plates and an overlay. The worker logs counts, not text, so a read it dropped there may be a "
          "misread plate or other text in the scene: not known.",
          "- A2's probe assumes the plate detector has already fired on the text; it measures only what the OCR, the "
          "gate and the rule then do, in the probe's three fonts.",
          "- A1 reproduces exploratory numbers: rule `1e-k2` was chosen after looking at reject-v1, the stored "
          "sightings and probe seed 7. The non-plate evidence is 3 texts on one sandbox camera, and the sandbox "
          "labels were made by our AI coding assistant with the stored read in view, not blind; the team's blind "
          "check (A5) is still to come.",
          "- The smoke and security checks and the worker run use the live stack on this laptop (GTX 1650 Ti); "
          "the API process had loaded `sentinel_common` before the helper was added, and the API does not call it."]
    rates = [float(x) / info["cameras"] for x in info["fps"]]
    if rates and sum(rates) / len(rates) < 4.0:
        L.append(f"- The worker run was not at `anpr_eval_current.md`'s analysis rate (about 4.5 fps per camera): "
                 f"{sum(rates) / len(rates):.1f} per camera on average over its status lines, {min(rates):.1f} at the "
                 "lowest (the cause is not measured here). Below 2 fps per camera the worker accepts single "
                 "confident reads (`SLOW_FPS`), so part of the window ran that path; the A3 thresholds were checked on "
                 "the run as it was.")
    if info["stale"]:
        L.append("- `anpr_eval.py` warned that a clip is newer than the first sighting in the window.")
    return "\n".join(L + [""])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "plate_gate_confirm.md"))
    ap.add_argument("--fuzz", type=int, default=200_000)
    a = ap.parse_args()
    d = Path(a.dir)
    frozen = json.loads((d / "frozen.json").read_text(encoding="utf-8"))
    fresh = json.loads((d / "fresh.json").read_text(encoding="utf-8"))
    a3, info = gate_a3(d)
    a2, table = gate_a2(fresh, d / "fresh.log")
    a3_logs = [d / n for n in ("pytest.log", "pytest_new.log", "smoke.log", "security.log", "anpr.log")]
    gates = {"A0": {"rows": gate_a0(frozen, d / "frozen.log"), "finished": finished(d / "frozen.log")},
             "A1": {"rows": gate_a1(frozen), "finished": finished(d / "frozen.log")},
             "A2": {"rows": a2, "finished": finished(d / "fresh.log")},
             "A3": {"rows": a3, "finished": max(finished(p) for p in a3_logs)}}
    last = max(v["finished"] for v in gates.values())
    for v in gates.values():
        v["pass"] = all(r["pass"] for r in v["rows"])
        v["finished"] = v["finished"].astimezone(IST).strftime("%d %b %H:%M")
    gates["A4"] = {"deadline": DEADLINE.strftime("%d %b %Y %H:%M IST"), "last": last.astimezone(IST).strftime("%d %b %H:%M"),
                   "pass": last <= DEADLINE}
    failed = [k for k, v in gates.items() if not v["pass"]]
    env = info["env"]
    c = frozen["conditions"]
    res = {"generated": datetime.now(IST).isoformat(timespec="seconds"), "gates": gates,
           "verdict": "SHIP" if not failed else "HOLD",
           "verdict_line": "A0-A3 all pass, within A4's deadline." if not failed else f"Failed: {', '.join(failed)}.",
           "conditions": {"ocr_model": c["ocr_model"], "threads": c["threads"], "min_ocr_conf": c["min_ocr_conf"],
                          "max_letters_from_digits": env.get("MAX_LETTERS_FROM_DIGITS", "?"),
                          "worker": f"{env.get('CAMERAS', '?').replace(',', ', ')} on one worker, "
                                    f"STATIC_TEXT_WINDOW_S={env.get('STATIC_TEXT_WINDOW_S', '?')}, "
                                    f"HW_DECODE={env.get('HW_DECODE', '?')}, OBJECT_DETECTION={env.get('OBJECT_DETECTION', '?')}, "
                                    f"DETECT_FPS={env.get('DETECT_FPS', '?')}, window "
                                    + (" to ".join(info["window"]) if info["window"] else "?")},
           "fresh_probe": table, "independent": independent_count(a.fuzz, 20260926),
           "second_reproduction": "identical" if frozen_numbers(frozen) == frozen_numbers(fresh) else "NOT identical",
           "worker_info": info}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(res), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({k: v for k, v in res.items() if k != "worker_info"}, indent=1,
                                                   default=str), encoding="utf-8")
    for k, v in gates.items():
        print(k, "PASS" if v["pass"] else "FAIL", *(f"\n  {r['what']}: {r['measured']} ({r['threshold']}) "
                                                   f"{'PASS' if r['pass'] else 'FAIL'}" for r in v.get("rows", [])))
    print("independent count:", res["independent"], "| second reproduction:", res["second_reproduction"])
    print("verdict:", res["verdict"], "| wrote", out)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
