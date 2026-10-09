"""Score plate-OCR models on the frozen test sets (bench/ocr_sets.py) exactly as the worker reads a crop: ocr.py's
preprocessing and weakest-character confidence, then normalise_plate, then the worker gate (worker.check_read: min_ocr_conf,
looks_like_indian_plate, and the letters-from-digits rule, MAX_LETTERS_FROM_DIGITS). CPU only, 2 threads. The
letters-from-digits rule was added on 26 Sep (bench/ocr_gates.md Addendum 2); results files written before that
counted reject-v1 crops the worker drops as passing.

    uv run --no-sync python bench/ocr_ab.py --set data/ocr-eval/sandbox-v1/manifest.csv --set ... \
        --baseline cct-xs-v2-global-model [--candidate path.onnx --candidate-config path.yaml] \
        --out bench/results/ocr_baseline.md

A manifest with empty true_plate is a reject set: only the gate is scored (every crop that passes goes on to the
tracker as a plate read). A manifest with a `stored` column also gets the stored read scored: the plate Sentinel saved
for the sighting is the track's vote over several reads, while the crop is only its best-confidence read, so the two
are different numbers. Results hold counts and rates only; per-crop reads go to data/ocr-eval/runs (gitignored).

A split in the trainer's format (data/ocr-train/test.csv from bench/plategen.py: image_path, plate_text) is read as a
set too, with layout and font from its _meta.csv, for Gate 2 of bench/ocr_gates.md. With a candidate, labelled sets
also get fixes and breaks by layout and by font: Gate 2 asks about the held-out font and two-line plates taken alone.
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # a live worker owns the GPU
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import csv  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from importlib.metadata import version  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402
from fast_plate_ocr import LicensePlateRecognizer  # noqa: E402

from sentinel_analytics.config import get_settings  # noqa: E402
from sentinel_analytics.ocr import PlateOCR  # noqa: E402
from sentinel_common import letters_from_digits, looks_like_indian_plate, normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "ocr-eval" / "runs"
BATCH = 8          # the worker OCRs every candidate from a tick in one call; a handful is typical
BOOT = 2000
METRICS = {        # name -> (label, numerator, denominator) over per-crop records
    "exact": ("exact after normalise", "exact", "one"),
    "raw_exact": ("raw exact", "raw", "one"),
    "within_one": ("within one character", "within1", "one"),
    "char_acc": ("per-character accuracy (1 - CER)", "char_ok", "chars"),
    "passes_gate": ("passes the worker gate", "gate", "one"),
    "passes_wrong": ("passes the gate and is wrong", "gate_wrong", "one"),
    "exact_of_passed": ("exact, of those that pass", "gate_exact", "gate"),
}
REJECT = ("passes_gate",)
PAIRED = {"exact": "exact", "passes_gate": "gate"}   # labelled sets pair on exact, reject sets on the gate
STORED_CONF = 0.9  # the Plate review page's top band of stored confidence


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load_model(model: str, config: str | None, threads: int) -> tuple[PlateOCR, str]:
    so = ort.SessionOptions()
    so.intra_op_num_threads, so.inter_op_num_threads = threads, 1
    kw = {"onnx_model_path": model, "plate_config_path": config} if config else {"hub_ocr_model": model}
    ocr = PlateOCR.__new__(PlateOCR)   # the product's own _prep and read_many, with this model in place
    ocr.rec = LicensePlateRecognizer(device="cpu", sess_options=so, **kw)
    ocr.rgb = getattr(ocr.rec.config, "image_color_mode", "rgb") == "rgb"
    return ocr, Path(model).stem if config else model


def load_split(path: Path, rows: list[dict]) -> tuple[list[dict], list[np.ndarray]]:
    """A synthetic split in the trainer's format (bench/plategen.py: image_path relative to the CSV, plate_text), with
    layout and font from its _meta.csv. Each plate is drawn on its own, so each crop is its own group."""
    with open(path.with_name(f"{path.stem}_meta.csv"), encoding="utf-8") as f:
        meta = {r["image_path"]: r for r in csv.DictReader(f)}
    out, imgs = [], []
    for i, r in enumerate(rows):
        m = meta[r["image_path"]]
        out.append({"id": Path(r["image_path"]).stem, "true_plate": r["plate_text"], "group": f"p{i:05d}",
                    "layout": f"{m['layout']}-line", "font": m["font"]})
        imgs.append(cv2.imdecode(np.fromfile(str(path.parent / r["image_path"]), np.uint8), cv2.IMREAD_COLOR))
    return out, imgs


def load_set(manifest: Path) -> tuple[list[dict], list[np.ndarray]]:
    with open(manifest, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if rows and "image_path" in rows[0]:
        return load_split(manifest, rows)
    imgs, changed = [], 0
    for r in rows:
        p = manifest.parent / f"{r['id']}.jpg"
        data = p.read_bytes() if p.exists() else b""
        changed += not data or hashlib.sha256(data).hexdigest() != r["sha256"]
        imgs.append(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None)
    if changed:
        raise SystemExit(f"{manifest}: {changed} crops missing or changed since the set was frozen")
    return rows, imgs


def passes(text: str, conf: float, min_conf: float, max_digits: int) -> bool:
    """worker.check_read(...) == "ok", restated because importing the worker loads the detectors (torch)."""
    return (bool(text) and conf >= min_conf and looks_like_indian_plate(normalise_plate(text))
            and letters_from_digits(text) <= max_digits)


def score(ocr: PlateOCR, rows: list[dict], imgs: list, min_conf: float,
          max_digits: int) -> tuple[list[dict], list, float]:
    ocr.read_many(imgs[:BATCH])   # warm-up: the first ONNX call pays for allocation
    reads, ms = [], 0.0
    for i in range(0, len(imgs), BATCH):
        t0 = time.perf_counter()
        reads += ocr.read_many(imgs[i:i + BATCH])
        ms += (time.perf_counter() - t0) * 1000
    recs = []
    for r, (text, conf) in zip(rows, reads):
        norm, truth = normalise_plate(text), r["true_plate"]
        gate = passes(text, conf, min_conf, max_digits)
        d = lev(norm, truth)
        exact = bool(truth) and norm == truth
        recs.append({"group": r["group"], "layout": r["layout"], "font": r.get("font", ""), "one": 1, "gate": int(gate),
                     "exact": int(exact), "raw": int(bool(truth) and text == truth), "within1": int(bool(truth) and d <= 1),
                     "chars": len(truth), "char_ok": max(0, len(truth) - d) if truth else 0,
                     "gate_wrong": int(gate and not exact), "gate_exact": int(gate and exact)})
    return recs, reads, ms / max(1, len(imgs))


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def by_group(recs: list[dict], key: str, groups: list[str]) -> np.ndarray:
    idx = {g: i for i, g in enumerate(groups)}
    out = np.zeros(len(groups))
    for r in recs:
        out[idx[r["group"]]] += r[key]
    return out


def boot_ci(num: list[np.ndarray], den: list[np.ndarray], sign: list[int], rng) -> list[float] | None:
    """Group bootstrap: resample whole groups (a vehicle seen many times counts once per draw). With several
    (num, den) pairs, the statistic is their signed sum, e.g. candidate rate minus baseline rate."""
    g = len(num[0])
    draw = rng.integers(0, g, size=(BOOT, g))
    with np.errstate(invalid="ignore", divide="ignore"):
        stat = sum(s * n[draw].sum(1) / d[draw].sum(1) for n, d, s in zip(num, den, sign))
    stat = stat[np.isfinite(stat)]
    return [round(float(np.percentile(stat, 2.5)), 4), round(float(np.percentile(stat, 97.5)), 4)] if stat.size else None


def summarise(recs: list[dict], names: tuple, rng) -> dict:
    groups = sorted({r["group"] for r in recs})
    out = {}
    for m in names:
        _, num, den = METRICS[m]
        k, n = sum(r[num] for r in recs), sum(r[den] for r in recs)
        out[m] = {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n),
                  "group_boot95": boot_ci([by_group(recs, num, groups)], [by_group(recs, den, groups)], [1], rng)}
    return out


def mcnemar(b: int, c: int) -> float:
    n = b + c
    return 1.0 if not n else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def compare(base: list[dict], cand: list[dict], names: tuple, rng) -> dict:
    groups = sorted({r["group"] for r in base})
    out = {}
    for m in names:
        _, num, den = METRICS[m]
        nb, db, nc, dc = (by_group(x, k, groups) for x, k in ((base, num), (base, den), (cand, num), (cand, den)))
        rb, rc = nb.sum() / db.sum() if db.sum() else float("nan"), nc.sum() / dc.sum() if dc.sum() else float("nan")
        diff = float(rc - rb)
        out[m] = {"diff": None if math.isnan(diff) else round(diff, 4),
                  "group_boot95": boot_ci([nc, nb], [dc, db], [1, -1], rng)}
    key = PAIRED["passes_gate" if names == REJECT else "exact"]
    fixes = sum(1 for b, c in zip(base, cand) if (b[key], c[key]) == ((1, 0) if names == REJECT else (0, 1)))
    breaks = sum(1 for b, c in zip(base, cand) if (b[key], c[key]) == ((0, 1) if names == REJECT else (1, 0)))
    out["paired"] = {"on": "passes_gate (lower is better)" if names == REJECT else "exact",
                     "fixes": fixes, "breaks": breaks, "mcnemar_exact_p": round(mcnemar(fixes, breaks), 4)}
    if names != REJECT:
        out["by"] = {k: paired_by(base, cand, k) for k in ("layout", "font") if any(r[k] for r in base)}
    return out


def paired_by(base: list[dict], cand: list[dict], key: str) -> dict:
    """Fixes and breaks on exact within each layout or font: Gate 2 asks about the held-out font and two-line plates
    taken alone, where a gain overall could hide a loss."""
    out = {}
    for v in sorted({r[key] for r in base}):
        pairs = [(b["exact"], c["exact"]) for b, c in zip(base, cand) if b[key] == v]
        fixes, breaks = pairs.count((0, 1)), pairs.count((1, 0))
        out[v] = {"n": len(pairs), "baseline": sum(b for b, _ in pairs), "candidate": sum(c for _, c in pairs),
                  "fixes": fixes, "breaks": breaks, "mcnemar_exact_p": round(mcnemar(fixes, breaks), 4)}
    return out


def stored_read(rows: list[dict], recs_by: list[list[dict]], reads_by: list[list], labels: list[str], rng) -> dict:
    """The stored read, scored as a crop is, and paired with each model's single re-read of the same crop. A reviewer
    who typed a look-alike where the plate format fixes the kind of character (a 1 in the series letters) disagrees with
    every normalised read; `truth_normalised` says how much that moves the rates."""
    recs = [{"group": r["group"], "one": 1, "exact": int(normalise_plate(r["stored"]) == r["true_plate"])} for r in rows]
    out = {"exact": summarise(recs, ("exact",), rng)["exact"], "paired": {}, "truth_normalised": {}}
    norm_truth = [normalise_plate(r["true_plate"]) for r in rows]
    out["truth_normalised"]["stored read"] = sum(normalise_plate(r["stored"]) == t for r, t in zip(rows, norm_truth))
    for label, cand, reads in zip(labels, recs_by, reads_by):
        b = sum(s["exact"] and not c["exact"] for s, c in zip(recs, cand))
        c_ = sum(c["exact"] and not s["exact"] for s, c in zip(recs, cand))
        out["paired"][label] = {"stored_only": b, "crop_only": c_, "mcnemar_exact_p": round(mcnemar(b, c_), 4)}
        out["truth_normalised"][label] = sum(normalise_plate(text) == t for (text, _), t in zip(reads, norm_truth))
    if "ocr_conf" in rows[0]:
        hi = [i for i, r in enumerate(rows) if r["ocr_conf"] and float(r["ocr_conf"]) >= STORED_CONF]
        out["confident"] = {"n": len(hi), "stored read": sum(recs[i]["exact"] for i in hi),
                            **{label: sum(cand[i]["exact"] for i in hi) for label, cand in zip(labels, recs_by)}}
    return out


def pct(x: dict) -> str:
    if x["rate"] is None:
        return "n/a"
    w, b = x["wilson95"], x["group_boot95"]
    boot = f"{b[0]:.1%}–{b[1]:.1%}" if b else "n/a"
    return f"{x['k']}/{x['n']} = {x['rate']:.1%} (Wilson {w[0]:.1%}–{w[1]:.1%}; groups {boot})"


def markdown(res: dict) -> str:
    c = res["conditions"]
    lines = [f"# Plate OCR A/B: {res['name']}", "",
             f"Generated {res['generated']} by `bench/ocr_ab.py`. fast-plate-ocr {c['fast_plate_ocr']}, onnxruntime "
             f"{c['onnxruntime']}, CPU only, {c['threads']} ONNX threads, batches of {c['batch']}. Each crop goes through "
             f"`PlateOCR.read_many` (ocr.py), `normalise_plate`, and the worker gate (confidence >= {c['min_ocr_conf']} on the "
             f"weakest character, `looks_like_indian_plate`, and at most {c.get('max_letters_from_digits', '(not applied)')} "
             "letters made from digits, as `worker.check_read`). Counts and rates only: no plate text is written here.", "",
             "Intervals: Wilson treats every crop as independent; `groups` is a bootstrap over groups (one vehicle seen "
             f"many times, or crops close in time, form one group; {BOOT} draws). Trust the group interval when groups are few.", ""]
    for s in res["sets"]:
        lines += [f"## {s['set']}", "",
                  f"{s['n']} crops in {s['groups']} groups; layout {s['layouts']}. {s['note']}", ""]
        if s.get("canonical") is not None and s["canonical"] < s["n"]:
            lines += [f"{s['n'] - s['canonical']} of the {s['n']} true plates are not in the form `normalise_plate` "
                      f"gives, so no normalised read (a model's or the stored one) can match them: exact is at most "
                      f"{s['canonical']}/{s['n']} here.", ""]
        models = list(s["models"])
        lines += ["| Metric | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
        for m in s["models"][models[0]]["metrics"]:
            lines.append(f"| {METRICS[m][0]} | " + " | ".join(pct(s["models"][x]["metrics"][m]) for x in models) + " |")
        lines.append("| ms per crop | " + " | ".join(f"{s['models'][x]['ms_per_crop']:.2f}" for x in models) + " |")
        if "exact" in s["models"][models[0]]["metrics"]:
            for x in models:
                lay = s["models"][x]["by_layout"]
                lines.append(f"\n{x}, exact by layout: " + "; ".join(f"{k} {v['k']}/{v['n']}" for k, v in lay.items()))
                if "by_font" in s["models"][x]:
                    lines.append(f"\n{x}, exact by font: " + "; ".join(f"{k} {v['k']}/{v['n']}"
                                                                        for k, v in s["models"][x]["by_font"].items()))
        if "stored" in s:
            st = s["stored"]
            lines += ["", "**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for "
                          "the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's "
                          "best-confidence read, and the table above re-reads that one crop.", "",
                      f"- Stored read, exact after normalise: {pct(st['exact'])}."]
            for x, p in st["paired"].items():
                lines.append(f"- Stored read against {x} on the single crop, paired on exact: stored right and crop wrong "
                             f"{p['stored_only']}, crop right and stored wrong {p['crop_only']} (exact McNemar p = "
                             f"{p['mcnemar_exact_p']:.4f}).")
            if "confident" in st:
                c = st["confident"]
                lines.append(f"- Sightings Sentinel stored with confidence >= {STORED_CONF}: {c['n']} of {s['n']}. Exact among "
                             "them: " + "; ".join(f"{k} {v}/{c['n']}" for k, v in c.items() if k != "n") + ".")
            lines.append("- With the true plate also put through `normalise_plate` (a look-alike typed where the format "
                         "fixes a letter or a digit then counts as agreeing), exact: "
                         + "; ".join(f"{k} {v}/{s['n']}" for k, v in st["truth_normalised"].items()) + ".")
        if "compare" in s:
            p = s["compare"]["paired"]
            lines += ["", f"Candidate vs baseline, paired on {p['on']}: {p['fixes']} fixed, {p['breaks']} broken, "
                          f"exact McNemar p = {p['mcnemar_exact_p']:.4f}.", ""]
            for m, d in s["compare"].items():
                if m in METRICS and d["diff"] is not None:
                    ci = d["group_boot95"]
                    lines.append(f"- {METRICS[m][0]}: {d['diff']:+.1%} (groups 95% {ci[0]:+.1%} to {ci[1]:+.1%})" if ci
                                 else f"- {METRICS[m][0]}: {d['diff']:+.1%}")
            for key, by in s["compare"].get("by", {}).items():
                lines.append(f"- paired on exact, by {key}: " + "; ".join(
                    f"{v} baseline {g['baseline']}/{g['n']}, candidate {g['candidate']}/{g['n']}, {g['fixes']} fixed, "
                    f"{g['breaks']} broken, p = {g['mcnemar_exact_p']:.4f}" for v, g in by.items()))
        lines.append("")
    run = {s["set"] for s in res["sets"]}
    lines += ["## Caveats", "",
              "- The crops are the stored evidence crops: the worker's padded plate crop, saved as JPEG (quality 85). "
              "The worker read the raw crop; this reads the JPEG.",
              "- A crop is scored as one read. The stored sighting is a track's vote over several reads, so the model "
              "rates are per read, not per sighting; only the stored-read lines are per sighting."]
    lines += [f"- {text}" for sets, text in CAVEATS if run & set(sets)]
    lines += ["- ms per crop is wall time for `read_many` on a laptop shared with a live worker: compare models within "
              "one run, not across runs.", ""]
    return "\n".join(lines)


CAVEATS = [
    (("ownfeed-v1",), "ownfeed-v1 is labelled by matching the stored read to a painted plate within 2 edits, so crops the "
     "product misread worse than that are not in it: its rates favour the model that made the stored reads (the "
     "baseline). Its plates are synthetic, painted onto Pexels stock footage."),
    (("sandbox-v1", "reject-v1"), "sandbox-v1 and reject-v1 are real sandbox crops labelled against each crop by our AI "
     "coding assistant, with the stored read in view: not blind, not a person (`sandbox_eye.md`). They are a frozen test "
     "set and are never used for training."),
    (("sandbox-blind-v1",), "sandbox-blind-v1 is real sandbox plates that Sentinel stored and a team member then read "
     "blind on the Plate review page, typing the plate without seeing Sentinel's read. Their reading is taken as the "
     "answer; on our own plates, where the truth is known, the same reviewer was right 222 times in 226 "
     "(`review_truth.md`), so a few answers here may be wrong. Only stored sightings are in it: a plate Sentinel never "
     "stored cannot be, so the set says nothing about plates missed. Its crops include every sandbox-v1 crop. It is a "
     "frozen test set and is never used for training."),
    (("ocr-train-test",), "ocr-train-test is synthetic: plates drawn by `bench/plategen.py`, the generator that made the "
     "fine-tune's training data, with registrations kept out of training and a third in a held-out font. A gain there "
     "shows the candidate learned the generator's plates; only the real sets say anything about real plates."),
]


NOTES = {
    "sandbox-v1": ("Real sandbox crops, labelled by our AI coding assistant, not blind (exact, one_off or wrong "
                   "verdicts)."),
    "reject-v1": ("Real sandbox crops our AI coding assistant judged not a plate (the sandbox stored every one as a "
                  "sighting): each that passes the gate goes on to the tracker as a plate read."),
    "ownfeed-v1": "AMD-TRAF-001/002 crops, synthetic plates painted on stock footage, labelled from the painted list.",
    "sandbox-blind-v1": ("Real sandbox plates (CAM06, CAM07, CAM12) from sightings Sentinel stored, each read blind by a "
                         "team member on the Plate review page; their reading is the true plate. Vehicle plates only."),
    "ocr-train-test": ("Held-out synthetic plates from `bench/plategen.py` (`data/ocr-train/test.csv`), never trained on; "
                       "about a third in Tahoma Bold, a font kept out of training. Each plate is drawn on its own, so "
                       "each crop is its own group."),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", required=True, help="manifest.csv (repeatable)")
    ap.add_argument("--baseline", default=get_settings().ocr_model)
    ap.add_argument("--baseline-config", help="plate config yaml when --baseline is an .onnx path")
    ap.add_argument("--candidate", help="hub name or .onnx path")
    ap.add_argument("--candidate-config")
    ap.add_argument("--threads", type=int, default=2, choices=(1, 2))
    ap.add_argument("--out", required=True, help="bench/results/<name>.md (a .json is written beside it)")
    a = ap.parse_args()
    cv2.setNumThreads(1)
    min_conf, max_digits = get_settings().min_ocr_conf, get_settings().max_letters_from_digits
    models = [load_model(a.baseline, a.baseline_config, a.threads)]
    if a.candidate:
        ocr, label = load_model(a.candidate, a.candidate_config, a.threads)
        models.append((ocr, label if label != models[0][1] else f"{label} (candidate)"))
    out = Path(a.out)
    rng = np.random.default_rng(0)
    res = {"name": out.stem, "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
           "conditions": {"fast_plate_ocr": version("fast-plate-ocr"), "onnxruntime": version("onnxruntime"),
                          "threads": a.threads, "batch": BATCH, "min_ocr_conf": min_conf,
                          "max_letters_from_digits": max_digits,
                          "baseline": models[0][1], "candidate": models[1][1] if a.candidate else None}, "sets": []}
    RUNS.mkdir(parents=True, exist_ok=True)
    for m in a.set:
        manifest = Path(m)
        rows, imgs = load_set(manifest)
        name = manifest.parent.name if manifest.name == "manifest.csv" else f"{manifest.parent.name}-{manifest.stem}"
        names = REJECT if not any(r["true_plate"] for r in rows) else tuple(METRICS)
        s = {"set": name, "n": len(rows), "groups": len({r["group"] for r in rows}),
             "layouts": {k: sum(r["layout"] == k for r in rows) for k in sorted({r["layout"] for r in rows})},
             "note": NOTES.get(name, ""), "models": {},
             "canonical": None if names == REJECT else sum(normalise_plate(r["true_plate"]) == r["true_plate"] for r in rows)}
        recs_by, reads_by = [], []
        for ocr, label in models:
            recs, reads, ms = score(ocr, rows, imgs, min_conf, max_digits)
            recs_by.append(recs)
            reads_by.append(reads)
            s["models"][label] = {"metrics": summarise(recs, names, rng), "ms_per_crop": round(ms, 3),
                                  "by_layout": {k: {"k": sum(r["exact"] for r in recs if r["layout"] == k),
                                                    "n": sum(r["layout"] == k for r in recs)} for k in s["layouts"]}}
            if any(r["font"] for r in recs):
                s["models"][label]["by_font"] = {k: {"k": sum(r["exact"] for r in recs if r["font"] == k),
                                                     "n": sum(r["font"] == k for r in recs)}
                                                 for k in sorted({r["font"] for r in recs})}
            with open(RUNS / f"{out.stem}__{name}__{Path(label).stem}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id", "true_plate", "read", "conf", "norm", "gate"])
                for r, (text, conf), rec in zip(rows, reads, recs):
                    w.writerow([r["id"], r["true_plate"], text, f"{conf:.3f}", normalise_plate(text), rec["gate"]])
            print(f"{name} / {label}: " + ", ".join(f"{k} {v['k']}/{v['n']}" for k, v in s["models"][label]["metrics"].items())
                  + f", {ms:.2f} ms/crop")
        if names != REJECT and "stored" in rows[0]:
            # its own draws, so the model intervals match runs made before the stored read was scored
            s["stored"] = stored_read(rows, recs_by, reads_by, [label for _, label in models], np.random.default_rng(0))
            print(f"{name} / stored read: exact {s['stored']['exact']['k']}/{s['stored']['exact']['n']}")
        if len(recs_by) == 2:
            s["compare"] = compare(recs_by[0], recs_by[1], names if names == REJECT else ("exact", "within_one", "char_acc",
                                                                                            "passes_wrong"), rng)
        res["sets"].append(s)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(res), encoding="utf-8")
    print("wrote", out.with_suffix(".md"), "and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
