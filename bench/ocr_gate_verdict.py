"""Apply the pre-registered OCR adoption gates (bench/ocr_gates.md, Addenda 1 and 2) to a candidate and write the
verdicts into the results file `bench/ocr_ab.py` produced. Nothing is chosen here: every threshold is the gates file's.

    uv run --no-sync python bench/ocr_gate_verdict.py --result bench/results/ocr_ft1.json \
        --candidate D:/GitHub/ocr-train/runs/ft1/cct_xs_v2_india_ft1.onnx \
        --candidate-config D:/GitHub/ocr-train/model/plate_config_india.yaml \
        --run-dir D:/GitHub/ocr-train/runs/ft1/2026-09-26_17-59-48 \
        --export-check D:/GitHub/ocr-train/runs/ft1/export_check.json \
        --selfcheck D:/GitHub/ocr-train/data/parity/parity.csv [--synth-result bench/results/ocr_ft1_synth.json]

Gate 0 also needs two measurements `ocr_ab.py` does not make, so this makes them:
- the load self-check: the candidate, loaded through the product's `PlateOCR`, reads synthetic plates;
- CPU time per crop (the gate's words; `ocr_ab.py` reports wall time per set): baseline and candidate interleaved,
  A B A B A B, over the own-feed crops, labels unused, recording whether a worker or trainer is running. A re-run
  adds its timing to the earlier runs on the same candidate (kept in the .json) and the gate takes the slowest.
The verdict section goes into the .md before the first set, replacing an earlier one, and into the .json as "gates".
Counts and rates only: no plate text is printed or written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import psutil

from ocr_ab import BATCH, load_model, load_set  # also pins the CPU and thread settings ocr_ab.py uses

from sentinel_analytics.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
SPEED_MAX = 1.25          # Gate 0
OWNFEED_EXACT_LO = -0.010  # Gate 1, ownfeed-v1: exact difference, group lower bound above -1.0 point
OWNFEED_WRONG_HI = 0.005   # Gate 1, ownfeed-v1: passes-and-wrong difference, group upper bound below +0.5 point
HELD_OUT_FONT = "tahoma-bold"  # Gate 2 (NEXT.md step 3)
REPS = 3
BUSY = ("sentinel-worker", "sentinel_analytics", "rotate_worker", "ftrain.py")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def busy_processes() -> list[str]:
    """Names of what would make a speed measurement invalid: an analytics worker, the rotation or the trainer."""
    found = set()
    for p in psutil.process_iter(["cmdline"]):
        cmd = " ".join(p.info.get("cmdline") or [])
        found.update(b for b in BUSY if b in cmd)
    return sorted(found)


def signature(model: str) -> dict:
    s = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
    i, o = s.get_inputs(), s.get_outputs()
    ok = (len(i) == 1 and i[0].name == "input" and i[0].type == "tensor(uint8)" and list(i[0].shape[1:]) == [64, 128, 3]
          and not isinstance(i[0].shape[0], int) and any(x.name == "plate" and list(x.shape[1:]) == [10, 37] for x in o))
    return {"inputs": [[x.name, [str(d) for d in x.shape], x.type] for x in i],
            "outputs": [[x.name, [str(d) for d in x.shape], x.type] for x in o], "pass": ok}


def selfcheck(models: list, csv_path: Path) -> dict:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    imgs = [cv2.imdecode(np.fromfile(str(csv_path.parent / r["image_path"]), np.uint8), cv2.IMREAD_COLOR) for r in rows]
    out = {"n": len(rows), "source": str(csv_path)}
    for ocr, label in models:
        reads = []
        for i in range(0, len(imgs), BATCH):
            reads += ocr.read_many(imgs[i:i + BATCH])
        out[label] = {"non_empty": sum(bool(t) for t, _ in reads),
                      "exact": sum(t == r["plate_text"] for (t, _), r in zip(reads, rows))}
    return out


def timing(models: list, imgs: list) -> dict:
    """CPU (process) and wall ms per crop, models interleaved so drift in the laptop's load hits both alike."""
    cpu = {label: [] for _, label in models}
    wall = {label: [] for _, label in models}
    for ocr, _ in models:
        ocr.read_many(imgs[:BATCH])   # warm-up
    for _ in range(REPS):
        for ocr, label in models:
            c0, w0 = time.process_time(), time.perf_counter()
            for i in range(0, len(imgs), BATCH):
                ocr.read_many(imgs[i:i + BATCH])
            cpu[label].append((time.process_time() - c0) * 1000 / len(imgs))
            wall[label].append((time.perf_counter() - w0) * 1000 / len(imgs))
    return {"n": len(imgs), "reps": REPS, "cpu_ms": cpu, "wall_ms": wall,
            "cpu_ms_median": {k: round(statistics.median(v), 3) for k, v in cpu.items()},
            "wall_ms_median": {k: round(statistics.median(v), 3) for k, v in wall.items()}}


def earlier_timing(prev: dict | None, onnx_sha: str) -> list[dict]:
    """Timing runs an earlier pass made on the same candidate. Every run is kept and the verdict takes the slowest
    valid one, so re-running this script cannot swap an unfavourable timing for a better one."""
    if not prev or prev.get("candidate", {}).get("onnx_sha256") != onnx_sha:
        return []
    if "timing_runs" in prev:
        return list(prev["timing_runs"])
    t = prev["timing"]   # written before runs were kept: its one run
    return [{"generated": prev["generated"], "n": t["n"], "reps": t["reps"], "cpu_ms_median": t["cpu_ms_median"],
             "wall_ms_median": t["wall_ms_median"], "ratio": prev["speed_ratio"], "busy": prev["busy"],
             "cpu_load_before": prev["cpu_load_before"]}]


def best_epoch(run_dir: Path) -> dict:
    with open(run_dir / "training_log.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    best = max(rows, key=lambda r: float(r["val_acc"]))   # first maximum, as ModelCheckpoint(save_best_only) keeps it
    return {"epochs": len(rows), "best_epoch": int(best["epoch"]) + 1, "best_val_acc": round(float(best["val_acc"]), 4)}


def pts(x: float) -> str:
    return f"{x * 100:+.2f} pt"


def gate1(res: dict, base: str, cand: str) -> list[dict]:
    """One row per scored set that Gate 1 or Addendum 1 names, in the results file's order."""
    rows = []

    def k(s, label, m):
        return s["models"][label]["metrics"][m]["k"]

    for s in res["sets"]:
        name, n = s["set"], s["n"]
        if name in ("sandbox-v1", "sandbox-blind-v1"):
            p = s["compare"]["paired"]
            wb, wc = k(s, base, "passes_wrong"), k(s, cand, "passes_wrong")
            rows.append({"gate": f"1 {name}", "source": "Gate 1" if name == "sandbox-v1" else "Addendum 1",
                         "rule": "breaks <= fixes on exact; passes-and-wrong: candidate <= baseline",
                         "result": f"{p['fixes']} fixed, {p['breaks']} broken (McNemar p = {p['mcnemar_exact_p']:.4f}); "
                                   f"passes and wrong {wc}/{n} against {wb}/{n}",
                         "verdict": "pass" if p["breaks"] <= p["fixes"] and wc <= wb else "fail"})
        elif name == "reject-v1":
            gb, gc = k(s, base, "passes_gate"), k(s, cand, "passes_gate")
            rows.append({"gate": "1 reject-v1", "source": "Gate 1, Addendum 2",
                         "rule": "crops passing the worker gate: candidate <= baseline (0 of 23 since Addendum 2)",
                         "result": f"{gc}/{n} against {gb}/{n}", "verdict": "pass" if gc <= gb else "fail"})
        elif name == "ownfeed-v1":
            ex, wr = s["compare"]["exact"], s["compare"]["passes_wrong"]
            ok = ex["group_boot95"][0] > OWNFEED_EXACT_LO and wr["group_boot95"][1] < OWNFEED_WRONG_HI
            rows.append({"gate": "1 ownfeed-v1", "source": "Gate 1",
                         "rule": "exact difference: group 95% lower bound above -1.0 pt; passes-and-wrong difference: "
                                 "upper bound below +0.5 pt",
                         "result": f"exact {pts(ex['diff'])} ({pts(ex['group_boot95'][0])} to "
                                   f"{pts(ex['group_boot95'][1])}); passes and wrong {pts(wr['diff'])} "
                                   f"({pts(wr['group_boot95'][0])} to {pts(wr['group_boot95'][1])})",
                         "verdict": "pass" if ok else "fail"})
    rows.append({"gate": "1 sandbox-fresh-v1", "source": "Addendum 2",
                 "rule": "breaks <= fixes on exact; passes-and-wrong: candidate <= baseline; all rows and new vehicles",
                 "result": "not scored: the set is frozen on 27 Sep by 10:00 IST, and no candidate is scored on its crops "
                           "before then; the gate lapses if it is not frozen by 3 Oct",
                 "verdict": "pending"})
    return rows


def gain(res: dict) -> dict:
    """Addendum 1: a real-plate gain needs p < 0.05, fixes > breaks, a group lower bound above 0 on sandbox-blind-v1
    (at least 6 fixes with no break, 8 with one, 10 with two), and (Addendum 2) fixes > breaks on sandbox-fresh-v1."""
    s = next((s for s in res["sets"] if s["set"] == "sandbox-blind-v1"), None)
    if not s:
        return {"shown": False, "why": "sandbox-blind-v1 not scored"}
    p, lo = s["compare"]["paired"], s["compare"]["exact"]["group_boot95"][0]
    blind = p["mcnemar_exact_p"] < 0.05 and p["fixes"] > p["breaks"] and lo > 0
    return {"shown": False, "blind_criteria_met": blind, "fixes": p["fixes"], "breaks": p["breaks"],
            "p": p["mcnemar_exact_p"], "exact_diff": s["compare"]["exact"]["diff"],
            "exact_group95": s["compare"]["exact"]["group_boot95"],
            "why": "sandbox-fresh-v1 not yet scored" if blind else "Addendum 1's criteria are not met on sandbox-blind-v1"}


def gate2(path: Path | None) -> dict:
    row = {"gate": "2 held-out synthetic", "source": "Gate 2",
           "rule": f"exact better with McNemar p < 0.05; no subgroup ({HELD_OUT_FONT}, two-line) with more broken than "
                   "fixed at p < 0.05"}
    if not path or not path.exists():
        return {**row, "result": "not run yet (`data/ocr-train/test.csv`, NEXT.md step 3)", "verdict": "pending"}
    s = json.loads(path.read_text(encoding="utf-8"))["sets"][0]
    p, by = s["compare"]["paired"], s["compare"].get("by", {})
    subs = [("font", HELD_OUT_FONT), ("layout", "two-line")]
    worse = [f"{v}" for key, v in subs if v in by.get(key, {})
             and by[key][v]["breaks"] > by[key][v]["fixes"] and by[key][v]["mcnemar_exact_p"] < 0.05]
    missing = [v for key, v in subs if v not in by.get(key, {})]
    ok = p["fixes"] > p["breaks"] and p["mcnemar_exact_p"] < 0.05 and not worse and not missing
    sub = "; ".join(f"{v}: {by[key][v]['fixes']} fixed, {by[key][v]['breaks']} broken, p = "
                    f"{by[key][v]['mcnemar_exact_p']:.4f}" for key, v in subs if v in by.get(key, {}))
    return {**row, "result": f"{p['fixes']} fixed, {p['breaks']} broken, p = {p['mcnemar_exact_p']:.4f}; {sub}"
                             + (f"; subgroup missing: {', '.join(missing)}" if missing else ""),
            "verdict": "pass" if ok else "fail"}


def section(g: dict) -> str:
    c = g["candidate"]
    t = g["timing"]
    base, cand = g["labels"]
    lines = ["## Gate verdicts (`bench/ocr_gates.md`, Addenda 1 and 2)", "",
             f"Written {g['generated']} by `bench/ocr_gate_verdict.py` from this file's JSON, the export check and a "
             f"timing run. Tree {g['tree']}. Candidate `{cand}`: `best.keras` of `{c['run_dir']}`, epoch "
             f"{c['best_epoch']} of {c['epochs']} (best `val_acc` {c['best_val_acc']:.4f} on the synthetic validation "
             "split: the checkpoint rule fixed before training, NEXT.md step 1; `last.keras` is not scored), exported to "
             f"ONNX (sha256 {c['onnx_sha256'][:12]}; `best.keras` {c['keras_sha256'][:12]}). Baseline `{base}`, the "
             "shipped model.", "",
             "**Not adopted.** No candidate replaces the shipped model before the 27 Sep submission, whatever it scores "
             "(Addendum 2); adoption is for the finale, with every gate passed by 9 Oct 18:00 IST.", "",
             "| Gate | Rule | Result | Verdict |", "|---|---|---|---|"]
    for r in g["rows"]:
        lines.append(f"| {r['gate']} | {r['rule']} | {r['result']} | **{r['verdict']}** |")
    gn = g["gain"]
    lo, hi = gn.get("exact_group95") or [0, 0]
    lines += ["", f"**Real-plate gain: not shown.** On sandbox-blind-v1 the candidate fixed {gn.get('fixes')} and broke "
              f"{gn.get('breaks')} (McNemar p = {gn.get('p', 1):.4f}); exact difference {pts(gn.get('exact_diff', 0))} "
              f"(groups 95% {pts(lo)} to {pts(hi)}). A gain needs p < 0.05, fixes > breaks and a lower bound above 0 "
              "there (at least 6 fixes with no break, 8 with one, 10 with two), then fixes > breaks on sandbox-fresh-v1. "
              f"{gn['why']}; the real sets show non-inferiority only.", "",
              f"**Speed.** CPU time per crop, each run the median of {t['reps']} interleaved passes (A B A B A B) over "
              f"{t['n']} own-feed crops (batches of {BATCH}, 2 ONNX threads). Every run of this script on this candidate "
              "is kept, and the verdict takes the slowest valid one: " + "; ".join(
                  f"{r['generated'][11:16]} baseline {r['cpu_ms_median'][base]:.2f} ms, candidate "
                  f"{r['cpu_ms_median'][cand]:.2f} ms ({r['ratio']:.2f}x; wall {r['wall_ms_median'][base]:.2f} and "
                  f"{r['wall_ms_median'][cand]:.2f} ms; worker, rotation or trainer running: "
                  f"{', '.join(r['busy']) or 'none'}; CPU {r['cpu_load_before']:.0f}% busy just before)"
                  for r in g["timing_runs"])
              + (f". Slowest valid run {g['speed_ratio']:.2f}x" if g["speed_ratio"] is not None else
                 ". No valid run") + ". The `ms per crop` rows below are `ocr_ab.py`'s wall time per set: " + "; ".join(
                  f"{s} {v:.2f}x" for s, v in g["wall_ratio_by_set"].items())
              + f"; pooled over every crop {g['wall_ratio_pooled']:.2f}x. Small sets (reject-v1 is 23 crops in 3 "
              "batches) swing with the laptop's load; the gate names CPU time, measured above.", "",
              f"**Overall: {g['overall']}**", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True, help="bench/results/<name>.json from ocr_ab.py with --candidate")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--candidate-config", required=True)
    ap.add_argument("--run-dir", required=True, help="the training run whose best.keras was exported")
    ap.add_argument("--export-check", required=True, help="JSON from ocr-train/export_check.py")
    ap.add_argument("--selfcheck", required=True, help="synthetic plates in the trainer's CSV format")
    ap.add_argument("--timing-set", default=str(ROOT / "data/ocr-eval/ownfeed-v1/manifest.csv"))
    ap.add_argument("--synth-result", help="bench/results/<name>_synth.json (Gate 2), if run")
    a = ap.parse_args()
    cv2.setNumThreads(1)

    res_path = Path(a.result)
    res = json.loads(res_path.read_text(encoding="utf-8"))
    base, cand = res["conditions"]["baseline"], res["conditions"]["candidate"]
    run_dir, onnx = Path(a.run_dir), Path(a.candidate)

    models = [load_model(get_settings().ocr_model, None, 2), load_model(a.candidate, a.candidate_config, 2)]
    if [m[1] for m in models] != [base, cand]:
        raise SystemExit(f"models {[m[1] for m in models]} are not the ones in {res_path} ({base}, {cand})")

    sig = signature(a.candidate)
    exp = json.loads(Path(a.export_check).read_text(encoding="utf-8"))
    chk = selfcheck(models, Path(a.selfcheck))
    busy = busy_processes()
    load = psutil.cpu_percent(interval=2)
    _, imgs = load_set(Path(a.timing_set))
    t = timing(models, imgs)
    busy = sorted(set(busy) | set(busy_processes()))
    ratio = t["cpu_ms_median"][cand] / t["cpu_ms_median"][base]
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    onnx_sha = sha(onnx)
    runs = earlier_timing(res.get("gates"), onnx_sha)
    runs.append({"generated": generated, "n": t["n"], "reps": t["reps"], "cpu_ms_median": t["cpu_ms_median"],
                 "wall_ms_median": t["wall_ms_median"], "ratio": round(ratio, 3), "busy": busy,
                 "cpu_load_before": load})
    worst = max((r["ratio"] for r in runs if not r["busy"]), default=None)

    def dims(shape: list[str]) -> str:
        return "[" + ",".join(d if d.isdigit() else "N" for d in shape) + "]"

    ex = exp["sets"]
    rows = [
        {"gate": "0 integrity", "source": "Gate 0", "rule": "ONNX input `input` [N,64,128,3] uint8, dynamic batch; "
         "output `plate` [N,10,37]",
         "result": "; ".join(f"`{n}` {dims(s)} {t.replace('tensor(', '').rstrip(')')}"
                             for n, s, t in sig["inputs"] + sig["outputs"]),
         "verdict": "pass" if sig["pass"] else "fail"},
        {"gate": "0 export", "source": "Gate 0 (export reproduces the checkpoint)",
         "rule": "ONNX gives the Keras checkpoint's plate probabilities: same top character in every slot, largest "
                 "difference below 1e-4",
         "result": "; ".join(f"{k} {v['plates_same_argmax']}/{v['n']} same, largest difference {v['max_abs_dp']:.1e}"
                             for k, v in ex.items()),
         "verdict": "pass" if exp["pass"] else "fail"},
        {"gate": "0 self-check", "source": "Gate 0", "rule": "loaded through the product's `PlateOCR`, reads a synthetic "
         "plate",
         "result": f"{chk[cand]['exact']}/{chk['n']} synthetic plates read exactly ({chk[cand]['non_empty']} non-empty); "
                   f"baseline {chk[base]['exact']}/{chk['n']}",
         "verdict": "pass" if chk[cand]["exact"] >= 1 and chk[cand]["non_empty"] == chk["n"] else "fail"},
        {"gate": "0 speed", "source": "Gate 0", "rule": "CPU time per crop at most 1.25x the baseline, back to back, "
         "worker stopped",
         "result": "; ".join(f"{r['cpu_ms_median'][cand]:.2f} against {r['cpu_ms_median'][base]:.2f} ms = "
                             f"{r['ratio']:.2f}x" + (" (not valid: a worker was running)" if r["busy"] else "")
                             for r in runs) + (f"; slowest valid run {worst:.2f}x" if len(runs) > 1 and worst else ""),
         "verdict": ("pass" if worst <= SPEED_MAX else "fail") if worst is not None
         else "not valid (a worker was running)"},
        {"gate": "0 pytest", "source": "Gate 0", "rule": "`pytest` passes after the integration change",
         "result": "no integration change: the product is unchanged (NEXT.md step 4)", "verdict": "pending"},
        *gate1(res, base, cand),
        gate2(Path(a.synth_result) if a.synth_result else None),
        {"gate": "3 live own-feed A/B", "source": "Gate 3", "rule": "AMD-TRAF-001/002, A B A B 10-minute windows, "
         "stored exact and capture no worse than the same-session baseline",
         "result": "not run: needs the worker change of NEXT.md step 4 and Gates 0-2 passed; after the submission",
         "verdict": "pending"},
    ]
    failed = [r["gate"] for r in rows if r["verdict"] not in ("pass", "pending")]
    pending = [r["gate"] for r in rows if r["verdict"] == "pending"]
    overall = (f"fails {', '.join(failed)}; a candidate that fails is recorded as failed and not adopted." if failed else
               "passes every gate scored so far. Still pending: " + ", ".join(pending)
               + ". Not adopted, and not before the submission in any case.")
    wall = {s["set"]: s["models"][cand]["ms_per_crop"] / s["models"][base]["ms_per_crop"] for s in res["sets"]}
    pooled = (sum(s["models"][cand]["ms_per_crop"] * s["n"] for s in res["sets"])
              / sum(s["models"][base]["ms_per_crop"] * s["n"] for s in res["sets"]))
    tree = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    porcelain = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True,
                               cwd=ROOT).stdout.splitlines()
    dirty = [ln[3:] for ln in porcelain if not ln[3:].startswith("bench/results/")]   # results are this pass's output
    g = {"generated": generated,
         "tree": f"{tree} plus uncommitted {', '.join(f'`{p}`' for p in dirty[:5])}" if dirty else f"{tree} (clean)",
         "labels": [base, cand],
         "candidate": {"onnx": str(onnx), "onnx_sha256": onnx_sha, "keras_sha256": sha(run_dir / "best.keras"),
                       "run_dir": run_dir.name, **best_epoch(run_dir)},
         "signature": sig, "export_check": exp, "selfcheck": chk, "timing": t, "timing_runs": runs,
         "speed_ratio": worst, "busy": busy, "cpu_load_before": load,
         "wall_ratio_by_set": {k: round(v, 2) for k, v in wall.items()},
         "wall_ratio_pooled": round(pooled, 3), "rows": rows, "gain": gain(res), "overall": overall}

    res["gates"] = g
    res_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    md_path = res_path.with_suffix(".md")
    md = md_path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(md) if ln.startswith("## "))
    if md[start].startswith("## Gate verdicts"):
        end = next((i for i in range(start + 1, len(md)) if md[i].startswith("## ")), len(md))
        del md[start:end]
    md[start:start] = section(g).split("\n")
    md_path.write_text("\n".join(md), encoding="utf-8")
    for r in rows:
        print(f"{r['gate']}: {r['verdict']}")
    print(f"speed this run {ratio:.2f}x (busy: {', '.join(busy) or 'none'}); runs kept {len(runs)}, slowest valid "
          f"{worst}; overall: {overall}")
    print("wrote", md_path, "and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
