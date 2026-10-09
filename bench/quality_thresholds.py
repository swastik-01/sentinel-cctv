"""Where to cut blur, light and contrast in capture_quality.py, from our own feed's crops only.

Our own feed is the two stock-footage cameras, AMD-TRAF-001/002: real traffic from Pexels with a synthetic
registration painted over every plate (feedsim/realclip.py), so no real registration is involved. Every
evidence crop the worker stored for them (data/crops/<camera>/) is measured with the product's own
capture_quality.assess(); the plate box is recovered from the crop by undoing the worker's padding.

Two things are measured:
  1. Percentiles of each metric over the crops that pass the size guidance.
  2. A degradation sweep: a fixed sample of those crops is blurred, darkened, flattened or veiled in steps,
     re-encoded as the worker stores crops (JPEG 85), measured again and read by the product's reader
     (sentinel_analytics.ocr.PlateOCR, CPU). A read "survives" when it still equals the reader's read of the
     untouched crop. The cut-off is the metric's value where fewer than SURVIVE of the reads survive.

The cut-offs come from (2). The painted plates are pure black on pure white, so a low percentile of (1) sits
at an ideal no ordinary plate reaches (their p5 contrast is near the largest possible grey spread); where
our reader stops reading them is a level any plate below it will struggle at. The sandbox crops and the
blind reviews are deliberately not used: the grades are compared with them.

    PYTHONUTF8=1 uv run --no-sync python bench/quality_thresholds.py [--sample 400] \
        [--out bench/results/quality_thresholds.md]

Counts, percentiles and rates only: no plate text and no crop file name is printed or written (the names
carry the plate).
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # a live worker owns the GPU
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import random  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from sentinel_analytics.ocr import PlateOCR  # noqa: E402
from sentinel_api import capture_quality as cq  # noqa: E402
from sentinel_common import looks_like_indian_plate, normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAMERAS = ("AMD-TRAF-001", "AMD-TRAF-002")
PCTS = (1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99)
FIELDS = ("plate_w", "char_h", "ratio", "sharpness", "brightness", "contrast", "clipped")
SURVIVE = 0.8        # a cut-off is where fewer than 80% of the reads survive
NOISE = 2.0          # grey levels of sensor noise added with darkening and flattening
SEED = 7
LEVELS = {
    # kind: (metric, worse when the metric is lower?, constant, steps)
    "blur": ("sharpness", True, "BLUR_BELOW",
             (0.004, 0.008, 0.012, 0.016, 0.02, 0.025, 0.03, 0.04, 0.06)),       # sigma as a share of plate h
    "dark": ("brightness", True, "DARK_BELOW", (0.7, 0.5, 0.35, 0.25, 0.18, 0.12, 0.08, 0.05)),   # grey x k
    "flat": ("contrast", True, "FLAT_BELOW", (0.7, 0.5, 0.35, 0.25, 0.18, 0.12, 0.08, 0.05)),     # spread x k
    "veil": ("brightness", False, "GLARE_ABOVE", (30, 60, 90, 120, 150, 180, 210, 230)),          # grey + a
}


def load(camera: str) -> list[tuple[np.ndarray, dict]]:
    out = []
    for f in sorted((ROOT / "data" / "crops" / camera).glob("*.jpg")):
        img = cv2.imread(str(f), cv2.IMREAD_COLOR)
        if img is not None and img.size:
            m = cq.assess(img)
            m["ratio"] = m["plate_h"] / m["plate_w"]
            m["sized"] = m["char_h"] >= cq.CHAR_MIN and m["plate_w"] >= cq.WIDTH_MIN
            out.append((img, m))
    return out


def degrade(img: np.ndarray, m: dict, kind: str, step: float, rng: np.random.Generator) -> np.ndarray:
    x = img.astype(np.float32)
    if kind == "blur" and step:
        x = cv2.GaussianBlur(x, (0, 0), step * m["plate_h"])
    elif kind == "dark" and step:
        x = x * step + rng.normal(0, NOISE, x.shape)
    elif kind == "flat" and step:
        x = x.mean() + (x - x.mean()) * step + rng.normal(0, NOISE, x.shape)
    elif kind == "veil":
        x = x + step
    x = np.clip(x, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", x, [cv2.IMWRITE_JPEG_QUALITY, 85])     # as sink.save_crop stores it
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def reads(ocr: PlateOCR, imgs: list[np.ndarray]) -> list[tuple[str, float]]:
    out = []
    for i in range(0, len(imgs), 64):
        out += [(normalise_plate(t), c) for t, c in ocr.read_many(imgs[i:i + 64])]
    return out


def sweep(ocr: PlateOCR, sample: list[tuple[np.ndarray, dict]]) -> tuple[dict, int]:
    """Per kind: [(step, median metric, survival)]. Step 0 is the control: the crop only re-encoded."""
    base = reads(ocr, [img for img, _ in sample])
    keep = [(img, m, r) for (img, m), (r, c) in zip(sample, base)
            if r and c >= cq.LOW_CONF and looks_like_indian_plate(r)]
    rng = np.random.default_rng(SEED)
    result = {}
    for kind, (metric, _, _, steps) in LEVELS.items():
        rows = []
        for step in (0, *steps):
            imgs = [degrade(img, m, kind, step, rng) for img, m, _ in keep]
            got = reads(ocr, imgs)
            values = [cq.assess(d)[metric] for d in imgs]
            alive = sum(g == r for (g, _), (_, _, r) in zip(got, keep)) / len(keep)
            rows.append((step, float(np.median(values)), alive))
        result[kind] = rows
    return result, len(keep)


def crossing(rows: list[tuple[float, float, float]]) -> tuple[float, bool]:
    """The metric where survival falls through SURVIVE, interpolated between the two steps around it;
    (last step's metric, False) when the reader kept SURVIVE of its reads at every step."""
    for (_, m0, s0), (_, m1, s1) in zip(rows, rows[1:]):
        if s1 < SURVIVE <= s0:
            t = (s0 - SURVIVE) / (s0 - s1)
            return m0 + t * (m1 - m0), True
    return rows[-1][1], False


def table(title: str, rows: list[dict]) -> list[str]:
    out = [f"### {title} ({len(rows)} crops)", "",
           "| metric | " + " | ".join(f"p{p}" for p in PCTS) + " |",
           "|---|" + "---|" * len(PCTS)]
    for k in FIELDS:
        v = np.array([r[k] for r in rows], dtype=float)
        out.append(f"| {k} | " + " | ".join(f"{np.percentile(v, p):.3g}" for p in PCTS) + " |")
    return out + [""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", type=int, default=400, help="crops in the degradation sweep")
    ap.add_argument("--out", type=Path, help="write the markdown results here")
    args = ap.parse_args()

    per_cam = {c: load(c) for c in CAMERAS}
    crops = [x for c in CAMERAS for x in per_cam[c]]
    rows = [m for _, m in crops]
    sized = [x for x in crops if x[1]["sized"]]
    if not sized:
        print("no crops found under data/crops for", ", ".join(CAMERAS))
        return 1
    sample = random.Random(SEED).sample(sized, min(args.sample, len(sized)))
    ocr = PlateOCR()
    if ocr.rec is None:
        print("the plate reader did not load")
        return 1
    curves, kept = sweep(ocr, sample)
    cuts = {kind: crossing(curves[kind]) for kind in LEVELS}
    layouts = {k: sum(r["layout"] == k for r in rows) for k in ("one-line", "two-line")}

    lines = ["# Capture-quality cut-offs from our own feed", "",
             f"Measured {datetime.now():%Y-%m-%d %H:%M} by `bench/quality_thresholds.py` on the stored evidence "
             f"crops of {', '.join(CAMERAS)} (Pexels stock footage with synthetic plates painted on by "
             "`feedsim/realclip.py`; no real registration). Metrics from `capture_quality.assess()`: the plate "
             "box is recovered by undoing the worker's 15% padding; sharpness is the variance of the Laplacian "
             f"with the plate resized to {cq.SHARP_H} px high, divided by the plate's grey variance; brightness "
             "(mean grey), contrast (grey standard deviation) and the clipped share (pixels at 5 or less or 250 "
             "or more) are on the plate, not the padding. The sandbox crops and the blind reviews were not used.",
             "",
             f"- Crops: {len(rows)} ({', '.join(f'{c} {len(per_cam[c])}' for c in CAMERAS)}); "
             f"{len(sized)} pass the size guidance (characters >= {cq.CHAR_MIN} px, plate >= {cq.WIDTH_MIN} px).",
             f"- Layout by box shape: {layouts['one-line']} one-line, {layouts['two-line']} two-line; "
             f"{sum(r['oblique'] for r in rows)} oblique by the box-shape rule.",
             f"- Degradation sweep: {len(sample)} of the sized crops sampled (seed {SEED}); {kept} of them read "
             f"as a valid Indian plate at confidence >= {cq.LOW_CONF} by `PlateOCR` (CPU) and were swept. A read "
             "survives a step when it equals the reader's read of the untouched crop. Each degraded crop is "
             f"re-encoded as JPEG 85, as the worker stores crops (step 0 is that re-encoding alone, the control); "
             f"darkening and flattening add {NOISE:g} grey levels of noise. Glare is judged on brightness: a veil "
             "of added grey washes the characters out, and the painted plates' white is already at 255, so the "
             "share of saturated pixels would start at an ideal real plates do not share.", "",
             f"## Cut-offs: where fewer than {SURVIVE:.0%} of reads survive", "",
             "| constant | degradation | value | reached |", "|---|---|---|---|"]
    for kind, (metric, lower_worse, const, _) in LEVELS.items():
        v, reached = cuts[kind]
        lines.append(f"| {const} | {kind} ({metric} {'below' if lower_worse else 'above'}) | {v:.3g} | "
                     f"{'yes' if reached else 'no: the reader kept its reads at every step; the last step is used'} |")
    lines += ["", "Survival by step (step 0 is the control, re-encoded only; blur steps are sigma as a share of the plate "
              "height, dark and flat steps multiply the grey or its spread, veil steps add grey levels):", ""]
    for kind, (metric, _, _, _) in LEVELS.items():
        lines += [f"**{kind}**", "", f"| step | median {metric} | reads surviving |", "|---|---|---|"]
        lines += [f"| {s:g} | {m:.3g} | {a:.1%} |" for s, m, a in curves[kind]]
        lines.append("")
    lines += ["## Percentiles", "",
              "For reference. A low percentile here would be a cut-off at the painted plates' ideal: their p5 "
              "contrast is close to the largest grey spread an image can have (127.5), which ordinary plates "
              "under CCTV do not reach, so the cut-offs above come from the sweep instead.", ""]
    lines += table("Crops that pass the size guidance", [m for _, m in sized])
    lines += table("All crops", rows)
    for c in CAMERAS:
        lines += table(c, [m for _, m in per_cam[c]])
    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
