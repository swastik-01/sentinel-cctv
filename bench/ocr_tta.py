"""Offline fix trials for plate OCR: does a cheap change to how one crop is read get more real plates right, without
training anything, breaking our own feeds or letting the hoarding through?

The blind check found the shipped OCR exact on 88 of 120 stored sandbox crops read one at a time
(bench/results/ocr_baseline_blind.md). Before a fine-tune, this tries five changes that need no training:

1. test-time augmentation: the crop plus K variants (K = 3, 5, 8, in the order of VARIANTS), combined three ways: a vote
   per character slot weighted by each read's confidence, the mean of the slot probabilities, and the tracker's own
   vote over the reads that pass the gate (as if the variants were extra frames);
2. contrast normalisation alone (CLAHE, auto-gamma);
3. the other fast-plate-ocr hub models alone, and two ensembles with the shipped one (slot vote);
4. two-line handling: a tall crop (h/w > 0.45) is also read as its top and bottom halves, joined; the read with the
   higher confidence is kept;
5. a crop under 128 px wide upscaled (cubic, Lanczos) before the model's own resize.

Every candidate reads through the product's path: fast-plate-ocr's resize, PlateOCR's decode and weakest-character
confidence (ocr.py; the plain read is checked against PlateOCR.read_many crop by crop), normalise_plate, and the
worker's check_read gate, letters-from-digits rule included. The candidates and the decision rule (VERDICT below) were
fixed before any candidate was scored. The real set is small (120 crops, 55 vehicle groups), so the best of 25
candidates looks better on it than it is: the report adds Holm-adjusted p values and a cross-selection estimate (choose
the best on half the groups, score it on the other half). The blind set is a test set under bench/ocr_gates.md, which
forbids tuning on it, so a fix chosen here needs fresh blind-read plates before it is claimed.

    PYTHONUTF8=1 uv run --no-sync python bench/ocr_tta.py [--out bench/results/ocr_fix_trials.md] [--reuse]

CPU only, 2 threads, batches of 8. Counts and rates only in bench/results; per-crop reads and the slot probabilities go
to data/ocr-eval/runs (gitignored). `--reuse` re-scores cached probabilities without reading again. It replaces an
earlier, narrower version of this script (three reads, own feeds only), whose tracker-vote rule is kept as rule (1c).
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # a live worker owns the GPU
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import csv  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime  # noqa: E402
from importlib.metadata import version  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402
from fast_plate_ocr.core.process import preprocess_image  # noqa: E402
from fast_plate_ocr.inference.hub import AVAILABLE_ONNX_MODELS  # noqa: E402
from fast_plate_ocr.inference.plate_recognizer import _load_image_from_source  # noqa: E402

from sentinel_analytics.config import get_settings  # noqa: E402
from sentinel_analytics.tracker import vote  # noqa: E402
from sentinel_analytics.worker import check_read  # noqa: E402
from sentinel_common import looks_like_indian_plate, normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "ocr-eval"
RUNS = EVAL / "runs"
_spec = importlib.util.spec_from_file_location("ocr_ab", ROOT / "bench" / "ocr_ab.py")
ocr_ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ocr_ab)

SETS = ["sandbox-blind-v1", "sandbox-v1", "reject-v1", "ownfeed-v1"]
REAL = "sandbox-blind-v1"
BATCH = 8
ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"   # every hub model's alphabet; '_' pads
SLOTS = 10
TALL = 0.45            # h/w above this is a two-line plate crop (a one-line crop is about 0.27)
UPSCALE_W = 128        # the model's input width
SPLITS = 1000          # cross-selection draws
LABELLED = ("exact", "within_one", "passes_gate", "passes_wrong", "exact_of_passed")
COMPARED = ("exact", "within_one", "passes_wrong")


def box_h(img: np.ndarray) -> float:
    """The plate box height: the worker pads 0.15 x box height above and below (worker.py), so a crop is 1.3 boxes."""
    return img.shape[0] / 1.3


def pad(frac: float):
    """The worker's padding changed by `frac` of the box height on every side (its own unit): -0.05 trims, +0.10 adds
    a replicated border, since the stored crop holds nothing beyond its own padding."""
    def f(img: np.ndarray) -> np.ndarray:
        t = max(1, round(abs(frac) * box_h(img)))
        if frac > 0:
            return cv2.copyMakeBorder(img, t, t, t, t, cv2.BORDER_REPLICATE)
        return img[t:-t, t:-t] if min(img.shape[:2]) > 2 * t + 8 else img
    return f


def affine(dx: float = 0, dy: float = 0, angle: float = 0.0, scale: float = 1.0):
    def f(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
        m[:, 2] += (dx, dy)
        return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return f


def clahe(img: np.ndarray) -> np.ndarray:
    """Local contrast on lightness only, in plate-shaped tiles (4 across, 2 down), so colours are left alone."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 2)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def gamma(img: np.ndarray) -> np.ndarray:
    """Gamma that brings the crop's mean grey to the middle: night crops brighten, glare darkens (0.5 to 2)."""
    m = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) / 255
    g = float(np.clip(np.log(0.5) / np.log(min(max(m, 0.02), 0.98)), 0.5, 2.0))
    return cv2.LUT(img, (255 * (np.arange(256) / 255) ** g).round().astype(np.uint8))


def upscale(interp: int):
    def f(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        return img if w >= UPSCALE_W else cv2.resize(img, (UPSCALE_W, max(1, round(h * UPSCALE_W / w))),
                                                     interpolation=interp)
    return f


def half(top: bool):
    def f(img: np.ndarray) -> np.ndarray | None:
        h, w = img.shape[:2]
        if h / w <= TALL:
            return None
        return img[: h // 2] if top else img[h // 2:]
    return f


# The TTA order was fixed before scoring: framing and lighting first (the likeliest faults on the sandbox), then
# shifts, then zoom and rotation. K=8 leaves out scale 0.9, which zooms out like pad +10% does.
VARIANTS = {"pad -5%": pad(-0.05), "pad +10%": pad(0.10), "CLAHE": clahe, "shift +2 px": affine(2, 2),
            "shift -2 px": affine(-2, -2), "scale 1.1": affine(scale=1.1), "rotate +3 deg": affine(angle=3.0),
            "rotate -3 deg": affine(angle=-3.0), "scale 0.9": affine(scale=0.9)}
VIEWS = {"as stored": lambda im: im, **VARIANTS, "gamma": gamma, "upscale cubic": upscale(cv2.INTER_CUBIC),
         "upscale Lanczos": upscale(cv2.INTER_LANCZOS4), "top half": half(True), "bottom half": half(False)}
ENSEMBLES = {"ensemble: shipped + cct-s-v2": ["cct-s-v2-global-model"],
             "ensemble: shipped + cct-s-v2 + global mobile-vit-v2": ["cct-s-v2-global-model",
                                                                    "global-plates-mobile-vit-v2-model"]}
MODEL_NOTES = {   # from the package README and each model's plate config
    "cct-s-v2-global-model": "CCT S, v2 global; the README's recommended default",
    "cct-xs-v2-global-model": "CCT XS, v2 global; shipped",
    "cct-s-v1-global-model": "CCT S, v1 global",
    "cct-xs-v1-global-model": "CCT XS, v1 global",
    "cct-s-relu-v1-global-model": "CCT S, v1 global, ReLU",
    "cct-xs-relu-v1-global-model": "CCT XS, v1 global, ReLU",
    "argentinian-plates-cnn-model": "CNN, Argentinian plates",
    "argentinian-plates-cnn-synth-model": "CNN, Argentinian plates, real and synthetic data",
    "european-plates-mobile-vit-v2-model": "MobileViT-2, European plates",
    "global-plates-mobile-vit-v2-model": "MobileViT-2, global (65+ countries)",
}


class Reader:
    """One hub model read the product's way, keeping every slot's probabilities so reads can be voted."""

    def __init__(self, name: str, threads: int) -> None:
        self.ocr, self.name = ocr_ab.load_model(name, None, threads)   # PlateOCR with this model in place
        self.cfg = self.ocr.rec.config
        self.slots = self.cfg.max_plate_slots
        assert self.cfg.alphabet == ALPHA and self.slots <= SLOTS, name
        dim = self.ocr.rec.model.get_inputs()[0].shape[0]
        self.batch = dim if isinstance(dim, int) else BATCH   # one hub model is exported for a batch of exactly 1

    def probs(self, crops: list) -> np.ndarray:
        """(N, SLOTS, len(ALPHA)) slot probabilities. NaN for a crop PlateOCR would not read (missing or too small)
        and for slots past this model's last."""
        out = np.full((len(crops), SLOTS, len(ALPHA)), np.nan, np.float32)
        for i in range(0, len(crops), self.batch):
            idx, imgs = [], []
            for j, c in enumerate(crops[i:i + self.batch]):
                im = self.ocr._prep(c)
                if im is not None:
                    idx.append(i + j)
                    imgs.append(im)
            if imgs:
                x = preprocess_image(_load_image_from_source(imgs, self.cfg))
                y = self.ocr.rec.model.run([self.ocr.rec.plate_output_name], {"input": x})[0]
                out[idx, :self.slots] = y.reshape(len(imgs), self.slots, len(ALPHA))
        return out


def finish(chars: list[str], conf: list[float]) -> tuple[str, float]:
    """ocr.py's reading of slot characters: pads dropped, confidence the weakest character's."""
    text = "".join(chars).rstrip("_").replace("_", "").strip()
    return text, float(min(conf[: max(1, len(text))])) if conf else 0.0


def decode(p: np.ndarray) -> tuple[str, float]:
    have = ~np.isnan(p[:, 0])
    if not have.any():
        return "", 0.0
    p = p[have]
    return finish([ALPHA[k] for k in p.argmax(1)], p.max(1).tolist())


def slot_vote(ps: list[np.ndarray]) -> tuple[str, float]:
    """Per slot, each read's top character scores its probability and the highest total wins. The slot's confidence is
    the reads' mean probability for the winner, the same scale as one read's, so the 0.35 gate keeps its meaning."""
    P = np.stack(ps)
    chars, conf = [], []
    for s in range(SLOTS):
        rs = np.flatnonzero(~np.isnan(P[:, s, 0]))
        if not rs.size:
            break
        top = P[rs, s].argmax(1)
        c = int(np.bincount(top, weights=P[rs, s, top], minlength=len(ALPHA)).argmax())
        chars.append(ALPHA[c])
        conf.append(float(P[rs, s, c].mean()))
    return finish(chars, conf) if chars else ("", 0.0)


def mean_vote(ps: list[np.ndarray]) -> tuple[str, float]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # slots no read has
        m = np.nanmean(np.stack(ps), axis=0)
    return decode(m)


def tracker_rule(reads: list[tuple[str, float]], gate) -> tuple[str, float]:
    """The reads handed to the tracker as one track's reads: its vote over those that pass the gate, or the best single
    read when the vote is not a valid plate (tracker.harvest). With none passing, the plain read stands (and fails)."""
    ok = [(normalise_plate(t), c) for t, c in reads if gate(t, c)]
    if not ok:
        return reads[0]
    voted = normalise_plate(vote(ok)[0])
    best = max(ok, key=lambda x: x[1])
    return (voted, best[1]) if looks_like_indian_plate(voted) else best


def two_line(whole: tuple[str, float], top: tuple[str, float], bottom: tuple[str, float]) -> tuple[str, float]:
    joined = (top[0] + bottom[0], min(top[1], bottom[1])) if top[0] and bottom[0] else ("", 0.0)
    return joined if joined[1] > whole[1] else whole


def candidates(P: dict, M: dict, gate) -> dict[str, dict]:
    """Every candidate's (text, conf) per crop, from the shipped model's views P and the other models' plain reads M.
    `views` and `models` say what each one reads, for its CPU cost; `family` marks the 25 pre-specified candidates."""
    n = len(P["as stored"])
    one = {v: [decode(p) for p in P[v]] for v in P}
    out = {"shipped model, as stored": {"trial": "baseline", "reads": one["as stored"], "views": ["as stored"]}}

    def add(name, trial, fn, views=(), models=(), family=True):
        t0 = time.perf_counter()
        reads = [fn(i) for i in range(n)]
        out[name] = {"trial": trial, "reads": reads, "views": list(views), "models": list(models), "family": family,
                     "combine_ms": (time.perf_counter() - t0) * 1000}

    for k in (3, 5, 8):
        vs = ["as stored", *list(VARIANTS)[:k]]
        add(f"TTA K={k}, slot vote", "1 TTA", lambda i, vs=vs: slot_vote([P[v][i] for v in vs]), vs)
        add(f"TTA K={k}, mean probabilities", "1 TTA", lambda i, vs=vs: mean_vote([P[v][i] for v in vs]), vs)
        add(f"TTA K={k}, tracker vote", "1 TTA", lambda i, vs=vs: tracker_rule([one[v][i] for v in vs], gate), vs)
    for v in ("CLAHE", "gamma"):
        add(v, "2 contrast", lambda i, v=v: one[v][i], [v])
    for m in M:
        add(m, "3 other model", lambda i, m=m: decode(M[m][i]), models=[m])
    for name, ms in ENSEMBLES.items():
        add(name, "3 ensemble", lambda i, ms=ms: slot_vote([P["as stored"][i], *(M[m][i] for m in ms)]),
            ["as stored"], ms)
    add("two-line halves", "4 two-line",   # a crop that is not tall has no halves, so its plain read stands
        lambda i: two_line(one["as stored"][i], one["top half"][i], one["bottom half"][i]),
        ["as stored", "top half", "bottom half"])
    for v in ("upscale cubic", "upscale Lanczos"):
        add(v, "5 upscale", lambda i, v=v: one[v][i], [v])
    for v in VARIANTS:   # descriptive: each variant alone (CLAHE is already a candidate)
        if v != "CLAHE":
            add(f"variant alone: {v}", "variant", lambda i, v=v: one[v][i], [v], family=False)
    return out


def records(rows: list[dict], reads: list[tuple[str, float]], gate) -> list[dict]:
    """ocr_ab.score's per-crop record, with the worker's check_read as the gate."""
    recs = []
    for r, (text, conf) in zip(rows, reads):
        norm, truth = normalise_plate(text), r["true_plate"]
        ok = gate(text, conf)
        d = ocr_ab.lev(norm, truth)
        exact = bool(truth) and norm == truth
        recs.append({"group": r["group"], "layout": r["layout"], "font": r.get("font", ""), "camera": r["camera"],
                     "one": 1, "gate": int(ok), "exact": int(exact), "raw": int(bool(truth) and text == truth),
                     "within1": int(bool(truth) and d <= 1), "chars": len(truth),
                     "char_ok": max(0, len(truth) - d) if truth else 0, "gate_wrong": int(ok and not exact),
                     "gate_exact": int(ok and exact)})
    return recs


def length_split(P: dict, views: list[str], base: list[dict], cand: list[dict]) -> dict:
    """Fixes and breaks split by whether the reads being combined agree on length (post hoc, added after the slot vote
    was seen to break two-line plates). A slot vote lines characters up by slot, so one read that drops or adds a
    character shifts every slot after it; the tracker votes only over reads of the modal length."""
    out = {k: {"n": 0, "fixes": 0, "breaks": 0} for k in ("mixed", "same")}
    for i, (b, c) in enumerate(zip(base, cand)):
        k = "mixed" if len({len(decode(P[v][i])[0]) for v in views}) > 1 else "same"
        out[k]["n"] += 1
        out[k]["fixes"] += c["exact"] > b["exact"]
        out[k]["breaks"] += b["exact"] > c["exact"]
    return out


def holm(ps: dict[str, float]) -> dict[str, float]:
    out, run = {}, 0.0
    for i, k in enumerate(sorted(ps, key=ps.get)):
        run = max(run, min(1.0, (len(ps) - i) * ps[k]))
        out[k] = round(run, 4)
    return out


def cross_select(base: list[dict], fam: dict[str, list[dict]], rng) -> dict:
    """How much of the best candidate's gain survives the choosing: pick the candidate with the most net fixes (fixes
    minus breaks, none if no candidate is ahead) on a random half of the groups, score it on the other half, and the
    other way round. The best of many candidates on one small set looks better than it is; the held-out net does not."""
    names = list(fam)
    b = np.array([r["exact"] for r in base])
    D = np.stack([np.array([r["exact"] for r in fam[n]]) - b for n in names])
    gids = sorted({r["group"] for r in base})
    gi = np.array([gids.index(r["group"]) for r in base])
    held, picks = [], Counter()
    for _ in range(SPLITS):
        mask = np.zeros(len(gids), bool)
        mask[rng.permutation(len(gids))[: len(gids) // 2]] = True
        a, tot = mask[gi], 0
        for pick_on, score_on in ((a, ~a), (~a, a)):
            net = D[:, pick_on].sum(1)
            k = int(net.argmax())
            if net[k] > 0:
                tot += int(D[k, score_on].sum())
                picks[names[k]] += 1
        held.append(tot)
    held = np.array(held)
    best = int(D.sum(1).argmax())
    return {"apparent_best": names[best], "apparent_net": int(D.sum(1)[best]),
            "held_out_net_mean": round(float(held.mean()), 2),
            "held_out_net_95": [float(np.percentile(held, 2.5)), float(np.percentile(held, 97.5))],
            "share_positive": round(float((held > 0).mean()), 3), "share_negative": round(float((held < 0).mean()), 3),
            "most_picked": picks.most_common(3), "splits": SPLITS}


def verdict(name: str, res: dict, ratio: float | None) -> dict:
    """The pre-specified reading of a candidate. Non-inferior: Gate 1 of bench/ocr_gates.md on every set run (breaks
    <= fixes and passes-and-wrong no higher on the real sets; no more reject crops passing; ownfeed-v1's exact lower
    bound above -1 point and passes-and-wrong upper bound below +0.5 point). A gain on real plates: also fixes > breaks,
    Holm-adjusted McNemar p < 0.05 and a group-bootstrap lower bound above 0 on sandbox-blind-v1."""
    fails = []
    for s, d in res.items():
        c = d["cands"].get(name)
        if c is None:        # not run on this set: no plate here fits its slots
            continue
        if s == "reject-v1":
            if c["metrics"]["passes_gate"]["k"] > d["cands"][BASE]["metrics"]["passes_gate"]["k"]:
                fails.append("reject-v1 passes")
        elif s == "ownfeed-v1":
            ex, pw = c["compare"]["exact"]["group_boot95"], c["compare"]["passes_wrong"]["group_boot95"]
            if ex and ex[0] <= -0.01:
                fails.append("ownfeed-v1 exact")
            if pw and pw[1] >= 0.005:
                fails.append("ownfeed-v1 passes-and-wrong")
        else:
            p = c["compare"]["paired"]
            if p["breaks"] > p["fixes"]:
                fails.append(f"{s} breaks")
            if c["metrics"]["passes_wrong"]["k"] > d["cands"][BASE]["metrics"]["passes_wrong"]["k"]:
                fails.append(f"{s} passes-and-wrong")
    out = {"fails": fails, "cpu_ratio": ratio, "gate0_cpu": ratio is not None and ratio <= 1.25}
    blind = res.get(REAL, {}).get("cands", {}).get(name)
    if blind:
        p, ci = blind["compare"]["paired"], blind["compare"]["exact"]["group_boot95"]
        out["gain"] = (not fails and p["fixes"] > p["breaks"] and blind.get("holm_p", 1.0) < 0.05
                       and ci is not None and ci[0] > 0)
    out["reading"] = ("gain on real plates" if out.get("gain") else "non-inferior" if not fails
                      else "fails: " + ", ".join(fails))
    return out


BASE = "shipped model, as stored"


def cpu_ratio(res: dict, n: str) -> float | None:
    """CPU per crop against the shipped read in the same run, from the largest set that ran the candidate."""
    for s in ("ownfeed-v1", REAL, *res):
        if s in res and n in res[s]["cands"]:
            c = res[s]["cands"]
            return round(c[n]["ms_per_crop"] / c[BASE]["ms_per_crop"], 2)
    return None


def load_or_read(name: str, rows: list[dict], imgs: list, shipped: Reader, others: dict[str, Reader],
                 reuse: bool) -> tuple[dict, dict, dict]:
    """The shipped model's reads of every view and the other models' plain reads, with wall ms per view (making the
    view included). Cached as probabilities under data/ so the report can be re-scored without reading again."""
    cache = RUNS / f"ocr_fix_trials__{name}.npz"
    key = json.dumps({"views": list(VIEWS), "models": list(others), "ids": [r["id"] for r in rows]})
    if reuse and cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["key"]) == key:
            ms = json.loads(str(z["ms"]))
            return ({v: z[f"v{i}"] for i, v in enumerate(VIEWS)}, {m: z[f"m{i}"] for i, m in enumerate(others)}, ms)
        print(f"{name}: cache is for other views, models or crops; reading again")
    P = {v: np.full((len(imgs), SLOTS, len(ALPHA)), np.nan, np.float32) for v in VIEWS}
    ms = dict.fromkeys(VIEWS, 0.0)
    shipped.probs(imgs[:BATCH])   # warm-up: the first ONNX call pays for allocation
    # every view in turn on each batch, so a busy laptop slows them all alike and the cost ratios hold
    for i in range(0, len(imgs), BATCH):
        chunk = imgs[i:i + BATCH]
        for v, f in VIEWS.items():
            t0 = time.perf_counter()
            P[v][i:i + BATCH] = shipped.probs([f(im) for im in chunk])
            ms[v] += (time.perf_counter() - t0) * 1000
        if i and i % 800 == 0:
            print(f"{name}: {i}/{len(imgs)} crops read", flush=True)
    M = {}
    for m, rd in others.items():   # one after another: interleaved sessions would contend for the same cores
        rd.probs(imgs[:BATCH])
        t0 = time.perf_counter()
        M[m] = rd.probs(imgs)
        ms[m] = (time.perf_counter() - t0) * 1000
    print(f"{name}: ms/crop " + ", ".join(f"{k} {v / len(imgs):.2f}" for k, v in ms.items()), flush=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, key=key, ms=json.dumps(ms), **{f"v{i}": P[v] for i, v in enumerate(VIEWS)},
                        **{f"m{i}": M[m] for i, m in enumerate(others)})
    return P, M, ms


def parity(shipped: Reader, imgs: list, P: np.ndarray) -> dict:
    """The plain read here against PlateOCR.read_many on the same crops: the harness must read as the worker does."""
    ref = [r for i in range(0, len(imgs), BATCH) for r in shipped.ocr.read_many(imgs[i:i + BATCH])]
    mine = [decode(p) for p in P]
    same = sum(a[0] == b[0] and abs(a[1] - b[1]) < 1e-4 for a, b in zip(ref, mine))
    return {"identical": same, "n": len(imgs), "max_conf_diff": round(max((abs(a[1] - b[1]) for a, b in zip(ref, mine)),
                                                                          default=0.0), 6)}


def fmt_ci(ci) -> str:
    return f"{ci[0]:+.1%} to {ci[1]:+.1%}" if ci else "n/a"


def summary(out: dict, fam: list[str]) -> list[str]:
    """The headline lines, computed from the results so they cannot drift from the tables."""
    res, v = out["sets"], out["verdicts"]
    blind, own, rej = res.get(REAL), res.get("ownfeed-v1"), res.get("reject-v1")
    L = ["## Summary", ""]
    if blind:
        on = [n for n in fam if n in blind["cands"]]
        gains = [n for n in on if v.get(n, {}).get("gain")]
        L.append("- A gain on real plates by the pre-specified rule (fixed > broken, Holm-adjusted McNemar p < 0.05, group "
                 "lower bound above 0, and non-inferior on every other set): "
                 + (", ".join(gains) if gains else f"none of the {len(on)} candidates") + ".")
        net = {n: blind["cands"][n]["compare"]["paired"]["fixes"] - blind["cands"][n]["compare"]["paired"]["breaks"]
               for n in on}
        best = max(on, key=net.get)
        p = blind["cands"][best]["compare"]["paired"]
        L.append(f"- Most net fixes on `{REAL}`: {best}, exact {blind['cands'][best]['metrics']['exact']['k']}/{blind['n']} "
                 f"against {blind['cands'][BASE]['metrics']['exact']['k']}/{blind['n']} (fixed {p['fixes']}, broken "
                 f"{p['breaks']}, McNemar p = {p['mcnemar_exact_p']:.3f}, Holm p = {blind['cands'][best]['holm_p']:.3f}); "
                 f"over all sets: {v[best]['reading']}; CPU {v[best]['cpu_ratio']}x the shipped read.")
        worse = [n for n in on if net[n] < 0]
        L.append(f"- More broken than fixed on `{REAL}`: {len(worse)} of {len(on)} candidates.")
    ok = [n for n in fam if v.get(n) and not v[n]["fails"]]

    def brief(n: str) -> str:
        parts = []
        if blind and n in blind["cands"]:
            p = blind["cands"][n]["compare"]["paired"]
            parts.append(f"`{REAL}` {blind['cands'][n]['metrics']['exact']['k']}/{blind['n']}, fixed {p['fixes']}, "
                         f"broken {p['breaks']}")
        if own and n in own["cands"]:
            c = own["cands"][n]["compare"]["exact"]
            parts.append(f"`ownfeed-v1` {c['diff']:+.2%} (groups {fmt_ci(c['group_boot95'])})")
        return f"{n} ({'; '.join(parts)}; CPU {v[n]['cpu_ratio']}x)"
    L.append("- Non-inferior on every set run: " + ("; ".join(brief(n) for n in ok) if ok else "none") + ".")
    if rej:
        more = [n for n in fam if n in rej["cands"] and rej["cands"][n]["metrics"]["passes_gate"]["k"]
                > rej["cands"][BASE]["metrics"]["passes_gate"]["k"]]
        L.append(f"- `reject-v1` (hoarding text): the shipped read lets {rej['cands'][BASE]['metrics']['passes_gate']['k']}"
                 f"/{rej['n']} through the gate; candidates letting more through: " + (", ".join(more) or "none") + ".")
    return L + [""]


def markdown(out: dict) -> str:
    c, res, cands = out["conditions"], out["sets"], out["candidates"]
    fam = [n for n, d in cands.items() if d["family"]]
    desc = [n for n, d in cands.items() if not d["family"] and n != BASE]
    L = [f"# Plate OCR fix trials: {len(fam)} changes to how a crop is read, no training", "",
         f"Generated {out['generated']} by `bench/ocr_tta.py`. fast-plate-ocr {c['fast_plate_ocr']}, onnxruntime "
         f"{c['onnxruntime']}, CPU only, {c['threads']} ONNX threads, batches of {BATCH}. Every candidate reads through the "
         "product's path: fast-plate-ocr's resize, `PlateOCR`'s decode and weakest-character confidence (`ocr.py`), "
         f"`normalise_plate`, and the worker's `check_read` gate (weakest character >= {c['min_ocr_conf']}, "
         f"`looks_like_indian_plate`, and at most {c['max_letters_from_digits']} digit turned into a letter). The shipped "
         f"model is `{c['shipped']}`. Counts and rates only: no plate text is written here.", "",
         "The candidates, their order and the reading rule below were fixed before any candidate was scored. Intervals are "
         f"group bootstraps ({ocr_ab.BOOT} draws over vehicle groups) of the candidate's rate minus the shipped model's; "
         "fixed / broken are crops the candidate gets right that the shipped model gets wrong, and the reverse; McNemar is "
         f"exact and two-sided; Holm adjusts it for the {len(fam)} candidates tried on the real set.", ""]
    for s, d in res.items():
        skip = out["skipped"].get(s)
        L.append(f"- `{s}`: {d['n']} crops in {d['groups']} groups. Plain read against `PlateOCR.read_many`: "
                 f"{d['parity']['identical']}/{d['n']} identical (largest confidence difference "
                 f"{d['parity']['max_conf_diff']})." + (f" Not run here, since none of this set's plates fits their "
                                                       f"slots (exact is 0 by construction): {len(skip)} models, "
                                                       + ", ".join(f"`{m}`" for m in skip) + "." if skip else ""))
    L += ["", "A smoke run on the first 24 crops of each set checked the harness before this run. No candidate, variant, "
          "combining rule or reading rule was changed after it; only the harness changed (a model exported for batches "
          "of one, timing order, and skipping a model none of a set's plates fits). The length split near the end was "
          "added after this run, as a diagnosis.", ""]
    L += summary(out, fam)
    L += ["## What was tried", "",
          "1. **Test-time augmentation.** The crop plus K variants, in this fixed order: "
          + ", ".join(f"{v}" for v in VARIANTS) + ". K=3 takes the first three, K=5 the first five, K=8 the first eight. "
          "Padding is changed in the worker's own unit (0.15 x the plate box height on each side): -5% trims 0.05 box "
          "heights, +10% adds a replicated 0.10. Shifts move the picture 2 px on both axes; scale and rotation turn about "
          "the centre. The reads are combined three ways: a vote per character slot weighted by each read's confidence "
          "(the slot's confidence is then the reads' mean probability for the winner); the mean of the slot "
          "probabilities; and the tracker's own vote over the reads that pass the gate, as if the variants were extra "
          "frames.",
          "2. **Contrast alone.** CLAHE on lightness (clip 2.0, 4 x 2 tiles); gamma that brings the mean grey to the middle "
          "(0.5 to 2).",
          "3. **Other hub models**, alone and in two ensembles with the shipped model (slot vote). The models, all from "
          "the fast-plate-ocr author's `arg-plates` release (the repository is MIT; the README gives no separate model "
          "licence and does not document the training data; the v2 region lists do not include India):", ""]
    L += ["| Model | Slots | Input | Colour | Note |", "|---|---|---|---|---|"]
    for m, info in out["models"].items():
        L.append(f"| `{m}` | {info['slots']} | {info['w']} x {info['h']} | {info['colour']} | {MODEL_NOTES.get(m, '')} |")
    L += ["", "   A model with fewer than 10 slots cannot read a 10-character plate, the common Gujarat form.",
          f"4. **Two-line halves.** A crop with h/w > {TALL} is also read as its top and bottom halves (each resized by the "
          "model as a one-line plate), joined; the joined read replaces the whole-crop read when its confidence (the "
          "weaker half's) is higher.",
          f"5. **Upscaling.** A crop under {UPSCALE_W} px wide is enlarged to {UPSCALE_W} px wide (cubic, or Lanczos) "
          "before the model's own linear resize.", ""]
    blind = res.get(REAL)
    if blind:
        b = blind["cands"][BASE]["metrics"]
        L += [f"## {REAL} (real sandbox plates, read blind by a team member)", "",
              f"Shipped model on the single crop: exact {ocr_ab.pct(b['exact'])}; within one character "
              f"{b['within_one']['k']}/{b['within_one']['n']}; passes the gate {b['passes_gate']['k']}/{b['passes_gate']['n']}"
              f", passes and is wrong {b['passes_wrong']['k']}/{b['passes_wrong']['n']}. For context, the stored sighting "
              f"(the track's vote over several frames) is exact on {blind['stored_exact']}/{blind['n']}.", "",
              "| Candidate | Trial | Exact | Change, groups 95% | Fixed / broken | McNemar p | Holm p | Within one | "
              "Passes and wrong | Two-line exact | By camera, fixed / broken | CPU ms per crop (x shipped) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in [BASE, *fam]:
            if n in blind["cands"]:
                L.append(row_blind(n, cands[n], blind))
        own = res.get("ownfeed-v1")
        L += ["", "Each variant read alone (not candidates; they show what the votes are made of):", "",
              f"| Variant | {REAL} exact | Fixed / broken | Passes and wrong | ownfeed-v1 exact | Fixed / broken | "
              "CPU ms per crop |", "|---|---|---|---|---|---|---|"]
        for n in desc:
            x = blind["cands"][n]
            p = x["compare"]["paired"]
            o = own["cands"].get(n) if own else None
            ocells = (f"{o['metrics']['exact']['k']}/{own['n']} | {o['compare']['paired']['fixes']} / "
                      f"{o['compare']['paired']['breaks']}") if o else "n/a | n/a"
            L.append(f"| {n.removeprefix('variant alone: ')} | {x['metrics']['exact']['k']}/{blind['n']} | "
                     f"{p['fixes']} / {p['breaks']} | {x['metrics']['passes_wrong']['k']} | {ocells} | "
                     f"{x['ms_per_crop']:.2f} |")
        cs = out["cross_selection"]
        L += ["", "**Choosing the best is part of the result.** The best candidate here, "
              f"{cs['apparent_best']}, is {cs['apparent_net']:+d} net (fixed minus broken) on all {blind['n']} crops. "
              f"Chosen on a random half of the {blind['groups']} groups and scored on the other half (both ways, "
              f"{cs['splits']} splits), the chosen candidate's net is {cs['held_out_net_mean']:+.2f} on average (95% of "
              f"splits {cs['held_out_net_95'][0]:+.0f} to {cs['held_out_net_95'][1]:+.0f}); above zero in "
              f"{cs['share_positive']:.0%} of splits and below zero in {cs['share_negative']:.0%}. Most often chosen: "
              + ("; ".join(f"{n} ({k} of {2 * cs['splits']} halves)" for n, k in cs["most_picked"]) or "none") + ".", ""]
    L += ["## Other sets: non-inferiority", "",
          "Gate 1 of `bench/ocr_gates.md`, applied to each candidate as if it were a model candidate: on the real sets, "
          "broken <= fixed and no more crops passing wrong; on `reject-v1` (real non-plate text), no more crops passing "
          "the gate; on `ownfeed-v1` (synthetic plates on stock footage), the exact change's lower bound above -1 point "
          "and the passes-and-wrong change's upper bound below +0.5 point. Gate 0 also asks for CPU time at most 1.25x.", "",
          "| Candidate | ownfeed-v1 exact | Change, groups 95% | ownfeed-v1 passes and wrong, change (95%) | "
          "ownfeed-v1 two-line fixed / broken | sandbox-v1 fixed / broken | reject-v1 passing | CPU x shipped | Reading |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n in [BASE, *fam]:
        L.append(row_other(n, res, out["verdicts"].get(n)))
    tta = [n for n in fam if cands[n]["trial"] == "1 TTA"]
    lab = [s for s, d in res.items() if any("length_split" in d["cands"].get(n, {}) for n in tta)]
    if tta and lab:
        L += ["", "## Why the slot vote breaks two-line plates (post hoc)", "",
              "Added after the slot vote was seen to break two-line plates on `ownfeed-v1`; a diagnosis, not a candidate. "
              "Each TTA candidate's fixes and breaks, split by whether the reads it combines agree on length. A slot vote "
              "lines characters up by position, so one variant that drops or adds a character shifts every slot after it; "
              "the tracker votes only over the reads of the most common length.", "",
              "| Candidate | " + " | ".join(f"{s}: mixed lengths, crops / fixed / broken | {s}: one length, fixed / broken"
                                         for s in lab) + " |", "|---|" + "---|---|" * len(lab)]
        for n in tta:
            cells = []
            for s in lab:
                ls = res[s]["cands"][n]["length_split"]
                cells += [f"{ls['mixed']['n']} / {ls['mixed']['fixes']} / {ls['mixed']['breaks']}",
                          f"{ls['same']['fixes']} / {ls['same']['breaks']}"]
            L.append(f"| {n} | " + " | ".join(cells) + " |")
    L += ["", "## Caveats", "",
          f"- `{REAL}` is a test set under `bench/ocr_gates.md` (Addendum 1), which forbids tuning on it. Choosing a fix "
          "from this table is tuning, so the winner's number here is optimistic (see the cross-selection line), and a "
          "fix chosen from it needs fresh blind-read plates (new sightings, not in the set) before any gain is claimed.",
          f"- The real set is {blind['n'] if blind else 'small'} crops of stored sightings: only plates Sentinel already "
          "stored, read by the shipped model, so it leans towards the shipped model. It says nothing about plates missed.",
          "- The true plate is one team member's blind reading, right 222 times in 226 on our own plates "
          "(`review_truth.md`); 9 of the 120 are not in `normalise_plate`'s form, so no candidate can match them.",
          "- The crops are the stored evidence crops (JPEG quality 85, already the track's best-confidence read). Variants "
          "of one crop share its blur, angle and light, so TTA is a floor on what more frames would give.",
          "- `ownfeed-v1` was labelled by matching the stored read within 2 edits, so it favours the shipped model; its "
          "plates are synthetic, painted on Pexels stock footage. `sandbox-v1` and `reject-v1` were labelled by our AI "
          "coding assistant, not blind; `sandbox-v1`'s 28 crops are all inside the blind set.",
          "- CPU ms is wall time on a laptop shared with live workers (GPU) and other CPU jobs, making the view included: "
          "compare within this run only. It is per crop read once; the worker reads each crop once per frame.", ""]
    return "\n".join(L)


def row_blind(n: str, cand: dict, blind: dict) -> str:
    x = blind["cands"][n]
    m = x["metrics"]
    lay = x["by_layout"].get("two-line", {})
    cpu = f"{x['ms_per_crop']:.2f} ({x['ms_per_crop'] / blind['cands'][BASE]['ms_per_crop']:.1f}x)"
    if n == BASE:
        return (f"| {n} | baseline | {m['exact']['k']}/{blind['n']} | | | | | {m['within_one']['k']} | "
                f"{m['passes_wrong']['k']} | {lay.get('k', 0)}/{lay.get('n', 0)} | | {cpu} |")
    cmp_, p = x["compare"], x["compare"]["paired"]
    cams = "; ".join(f"{k.removeprefix('CAM')} {v['fixes']}/{v['breaks']}" for k, v in x["by_camera"].items()
                     if v["fixes"] or v["breaks"]) or "none"
    return (f"| {n} | {cand['trial']} | {m['exact']['k']}/{blind['n']} | {cmp_['exact']['diff']:+.1%} "
            f"({fmt_ci(cmp_['exact']['group_boot95'])}) | {p['fixes']} / {p['breaks']} | {p['mcnemar_exact_p']:.3f} | "
            f"{x.get('holm_p', 1.0):.3f} | {m['within_one']['k']} | {m['passes_wrong']['k']} | "
            f"{lay.get('k', 0)}/{lay.get('n', 0)} | {cams} | {cpu} |")


def row_other(n: str, res: dict, v: dict | None) -> str:
    cells = []
    own = res.get("ownfeed-v1")
    if own and n not in own["cands"]:
        cells += ["not run: no plate here fits its slots (0 by construction)", "", "", ""]
    elif own:
        x = own["cands"][n]
        cells.append(f"{x['metrics']['exact']['k']}/{own['n']}")
        if n == BASE:
            cells += ["", f"{x['metrics']['passes_wrong']['k']}/{own['n']}", ""]
        else:
            c = x["compare"]
            two = c.get("by", {}).get("layout", {}).get("two-line", {})
            cells += [f"{c['exact']['diff']:+.2%} ({fmt_ci(c['exact']['group_boot95'])})",
                      f"{c['passes_wrong']['diff']:+.2%} ({fmt_ci(c['passes_wrong']['group_boot95'])})",
                      f"{two.get('fixes', 0)} / {two.get('breaks', 0)}"]
    else:
        cells += ["n/a"] * 4
    s1 = res.get("sandbox-v1")
    if s1 and n in s1["cands"]:
        x = s1["cands"][n]
        cells.append(f"exact {x['metrics']['exact']['k']}/{s1['n']}" if n == BASE else
                     f"{x['compare']['paired']['fixes']} / {x['compare']['paired']['breaks']}")
    else:
        cells.append("n/a")
    rj = res.get("reject-v1")
    cells.append(f"{rj['cands'][n]['metrics']['passes_gate']['k']}/{rj['n']}" if rj and n in rj["cands"] else "n/a")
    r = cpu_ratio(res, n)
    cells.append(f"{r:.1f}x" if r is not None else "n/a")
    cells.append("baseline" if n == BASE else v["reading"] if v else "")
    return f"| {n} | " + " | ".join(cells) + " |"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", help=f"frozen set name under data/ocr-eval (default: {', '.join(SETS)})")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "ocr_fix_trials.md"))
    ap.add_argument("--threads", type=int, default=2, choices=(1, 2))
    ap.add_argument("--reuse", action="store_true", help="re-score cached probabilities (data/ocr-eval/runs)")
    ap.add_argument("--limit", type=int, help="first N crops per set: a smoke test, never a result")
    a = ap.parse_args()
    cv2.setNumThreads(1)
    ort.set_default_logger_severity(3)   # the older exports warn on every shape merge; errors still show
    s = get_settings()
    min_conf, max_digits = s.min_ocr_conf, s.max_letters_from_digits

    def gate(text: str, conf: float) -> bool:
        return check_read(text, conf, min_conf, max_digits) == "ok"

    shipped = Reader(s.ocr_model, a.threads)
    others = {m: Reader(m, a.threads) for m in AVAILABLE_ONNX_MODELS if m != s.ocr_model}
    models = {m: {"slots": r.slots, "w": r.cfg.img_width, "h": r.cfg.img_height, "colour": r.cfg.image_color_mode}
              for m, r in {s.ocr_model: shipped, **others}.items()}
    out_path = Path(a.out)
    res, cand_meta, per_set, skipped = {}, {}, {}, {}
    for name in a.set or SETS:
        rows, imgs = ocr_ab.load_set(EVAL / name / "manifest.csv")
        if a.limit:
            rows, imgs = rows[: a.limit], imgs[: a.limit]
        labelled = any(r["true_plate"] for r in rows)
        names = LABELLED if labelled else ocr_ab.REJECT
        # a model none of whose slots can hold any plate here scores 0 exact by construction; ownfeed-v1 (all 10
        # characters) would spend an hour of CPU showing it, so it is skipped unless an ensemble needs it
        need = {m for ms_ in ENSEMBLES.values() for m in ms_}
        run = {m: rd for m, rd in others.items()
               if not labelled or m in need or any(len(r["true_plate"]) <= rd.slots for r in rows)}
        skipped[name] = sorted(set(others) - set(run))
        P, M, ms = load_or_read(name if not a.limit else f"{name}-limit{a.limit}", rows, imgs, shipped, run, a.reuse)
        C = candidates(P, M, gate)
        rng = np.random.default_rng(0)
        base = records(rows, C[BASE]["reads"], gate)
        d = {"n": len(rows), "groups": len({r["group"] for r in rows}), "parity": parity(shipped, imgs, P["as stored"]),
             "cands": {}}
        if "stored" in rows[0] and labelled:
            d["stored_exact"] = sum(normalise_plate(r["stored"]) == r["true_plate"] for r in rows)
        per_set[name] = {"rows": rows, "recs": {}}
        for n, cand in C.items():
            recs = records(rows, cand["reads"], gate)
            per_set[name]["recs"][n] = recs
            cost = sum(ms[v] for v in cand["views"]) + sum(ms[m] for m in cand.get("models", [])) \
                + cand.get("combine_ms", 0.0)
            x = {"metrics": ocr_ab.summarise(recs, names, rng), "ms_per_crop": round(cost / len(rows), 3),
                 "by_layout": {k: {"k": sum(r["exact"] for r in recs if r["layout"] == k),
                                   "n": sum(r["layout"] == k for r in recs)} for k in sorted({r["layout"] for r in rows})}}
            if n != BASE:
                x["compare"] = ocr_ab.compare(base, recs, COMPARED if labelled else ocr_ab.REJECT, rng)
                if labelled and cand["trial"] == "1 TTA":
                    x["length_split"] = length_split(P, cand["views"], base, recs)
                if labelled:
                    x["by_camera"] = {cam: {"fixes": sum(b["exact"] < c["exact"] for b, c in zip(base, recs)
                                                         if b["camera"] == cam),
                                            "breaks": sum(b["exact"] > c["exact"] for b, c in zip(base, recs)
                                                          if b["camera"] == cam)}
                                      for cam in sorted({r["camera"] for r in rows})}
            d["cands"][n] = x
            cand_meta[n] = {"trial": cand["trial"], "family": cand.get("family", False), "views": cand["views"],
                            "models": cand.get("models", [])}
        res[name] = d
        with open(RUNS / f"ocr_fix_trials__{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "true_plate", *(f"{n} | {k}" for n in C for k in ("read", "conf", "gate"))])
            for i, r in enumerate(rows):
                w.writerow([r["id"], r["true_plate"],
                            *(x for n in C for x in (C[n]["reads"][i][0], f"{C[n]['reads'][i][1]:.3f}",
                                                    per_set[name]["recs"][n][i]["gate"]))])
        b = d["cands"][BASE]["metrics"]
        print(f"{name}: shipped " + ", ".join(f"{k} {v['k']}/{v['n']}" for k, v in b.items())
              + f"; parity {d['parity']['identical']}/{d['n']}", flush=True)
    fam = [n for n, m in cand_meta.items() if m["family"]]
    out = {"name": out_path.stem, "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
           "conditions": {"fast_plate_ocr": version("fast-plate-ocr"), "onnxruntime": version("onnxruntime"),
                          "threads": a.threads, "batch": BATCH, "min_ocr_conf": min_conf,
                          "max_letters_from_digits": max_digits, "shipped": s.ocr_model, "limit": a.limit},
           "models": models, "candidates": cand_meta, "sets": res, "skipped": skipped}
    if REAL in res:
        fam = [n for n in fam if n in res[REAL]["cands"]]
        hp = holm({n: res[REAL]["cands"][n]["compare"]["paired"]["mcnemar_exact_p"] for n in fam})
        for n, p in hp.items():
            res[REAL]["cands"][n]["holm_p"] = p
        out["cross_selection"] = cross_select(per_set[REAL]["recs"][BASE], {n: per_set[REAL]["recs"][n] for n in fam},
                                              np.random.default_rng(1))
    out["verdicts"] = {n: verdict(n, res, cpu_ratio(res, n)) for n in fam}
    out_path.with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    out_path.with_suffix(".md").write_text(markdown(out), encoding="utf-8")
    print("wrote", out_path.with_suffix(".md"), "and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
