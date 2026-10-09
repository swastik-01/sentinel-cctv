"""Per-capture plate quality: is this evidence crop good enough to read a registration from?

Each stored sighting's crop is measured (size, sharpness, light, angle) and graded good, marginal or
poor with its reasons, so a camera can be judged by what it captures and not only by what the reader
made of it. camera_quality.py rolls the grades up per camera into a tier and recommendations.

Size cut-offs are published guidance, collected in docs/commercial-anpr.md ("Pixels on the plate"):
Adaptive Recognition wants characters at least 10 px tall, best 20-60 px; Axis wants 100-150 px across
the plate and at least 75 px. Blur, light and contrast cut-offs come from our own feed's crops (see the
constants below), never from the sandbox crops or the blind reviews the grades are compared with.

OpenCV and NumPy come with the analytics worker in the workspace environment; sentinel-api does not
declare them, so without them nothing is graded and the rest of the API is unaffected.
"""
from __future__ import annotations

from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:     # an API-only install: no grading
    cv2 = np = None

AVAILABLE = cv2 is not None

PAD = 0.15              # worker.py pads the plate box by int(0.15 * h) on every side before cropping
TWO_LINE_RATIO = 0.45   # plate box height / width above this: two rows of characters
CHAR_SHARE = {"one-line": 0.7, "two-line": 0.35}   # character height as a share of the plate box height
# HSRP plates seen head-on (mm): one-line 500 x 120, two-line 340 x 200.
EXPECTED_RATIO = {"one-line": 120 / 500, "two-line": 200 / 340}
# Oblique: a plate turned by t from the camera looks 1/cos(t) taller for its width (Axis keeps the total
# angle under 30 degrees, docs/commercial-anpr.md). From the box alone a turned one-line plate cannot be told
# from a two-line one, so only shapes no head-on plate gives are called oblique: taller than a two-line plate
# turned about 45 degrees with a loose box (x1.4), or squashed below half a one-line plate's height (a camera
# looking steeply down).
OBLIQUE_MAX = EXPECTED_RATIO["two-line"] * 1.4
OBLIQUE_MIN = EXPECTED_RATIO["one-line"] * 0.5
# Sharpness: variance of the Laplacian with the plate resized to the reader's input height (fast-plate-ocr
# cct-xs-v2 reads 64 x 128), so it is judged at the size the reader sees and a big plate does not score
# sharper for being big; divided by the plate's grey variance, so a high-contrast plate does not either.
SHARP_H = 64

# Size: published guidance (docs/commercial-anpr.md, "Pixels on the plate").
CHAR_MIN, CHAR_OK = 10, 16      # Adaptive Recognition: characters >= 10 px tall, best 20-60
WIDTH_MIN, WIDTH_OK = 75, 100   # Axis: 100-150 px across the plate, >= 75 px at the least
LOW_CONF = 0.6                  # the worker accepts a lone read at or above this (SINGLE_READ_CONF, tracker.py)

# Blur, light and contrast: from our own feed's crops only (AMD-TRAF-001/002: stock footage with synthetic
# plates painted on), by bench/quality_thresholds.py on 26 Sep 2026 (bench/results/quality_thresholds.md).
# 377 crops our reader read were blurred, darkened, flattened or veiled in steps; each cut-off is the metric
# where fewer than 80% of the reads stayed the same. Not low percentiles of those crops: the painted plates
# are pure black on white (p5 contrast 99 of a possible 127), so a percentile would fail ordinary plates.
BLUR_BELOW = 0.057      # sharpness; untouched crops median 0.31
DARK_BELOW = 57.0       # mean grey of the plate; untouched median 155
FLAT_BELOW = 45.0       # grey standard deviation of the plate; untouched median 110
GLARE_ABOVE = 217.0     # mean grey of the plate washed out by a veil of light

IMAGE_PROBLEMS = ("blurred", "dark", "glare", "low_contrast", "oblique")
REASONS = ("too_small", "small", *IMAGE_PROBLEMS, "two_line", "low_confidence")


def plate_box(crop_h: int, crop_w: int, bbox=None) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the plate inside the crop. From the stored plate box when there is one (it is the
    box the crop was cut around, in the same pixels); otherwise by undoing the worker's padding, which
    under-reads a plate cut short by the frame edge."""
    if bbox is not None and len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0:
        x, y, w, h = (int(v) for v in bbox)
        pad = int(h * PAD)
        ox, oy = min(max(x, 0), pad), min(max(y, 0), pad)
    else:
        h = min(range(max(1, int(crop_h / (1 + 2 * PAD)) - 2), int(crop_h / (1 + 2 * PAD)) + 3),
                key=lambda k: abs(k + 2 * int(k * PAD) - crop_h))
        pad = int(h * PAD)
        ox, oy, w = pad, pad, crop_w - 2 * pad
    w, h = max(1, min(w, crop_w - ox)), max(1, min(h, crop_h - oy))
    return ox, oy, w, h


def assess(crop_bgr, bbox=None) -> dict:
    """Measurements of one evidence crop. Sizes are in stream pixels; light and contrast are on the
    plate itself, not the padding around it."""
    ch, cw = crop_bgr.shape[:2]
    x, y, w, h = plate_box(ch, cw, bbox)
    grey = crop_bgr if crop_bgr.ndim == 2 else cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    plate = grey[y:y + h, x:x + w]
    ratio = h / w
    layout = "two-line" if ratio > TWO_LINE_RATIO else "one-line"
    scale = SHARP_H / plate.shape[0]
    sized = cv2.resize(plate, (max(1, round(plate.shape[1] * scale)), SHARP_H),
                       interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    return {
        "plate_w": int(w), "plate_h": int(h), "layout": layout,
        "char_h": int(round(h * CHAR_SHARE[layout])),
        "sharpness": round(float(cv2.Laplacian(sized, cv2.CV_64F).var() / max(float(sized.var()), 25.0)), 3),
        "brightness": round(float(plate.mean()), 1),
        "contrast": round(float(plate.std()), 1),
        "clipped": round(float(np.count_nonzero((plate <= 5) | (plate >= 250)) / plate.size), 3),
        "oblique": bool(ratio > OBLIQUE_MAX or ratio < OBLIQUE_MIN),
    }


def classify(m: dict, ocr_conf: float | None = None) -> tuple[str, list[str]]:
    """(quality, reasons). Poor: too small to read, or two or more image problems at once. Marginal: any
    single problem, a two-line plate (the reader's weak layout) or a low-confidence read. Good: none."""
    reasons = []
    if m["char_h"] < CHAR_MIN or m["plate_w"] < WIDTH_MIN:
        reasons.append("too_small")
    elif m["char_h"] < CHAR_OK or m["plate_w"] < WIDTH_OK:
        reasons.append("small")
    if m["sharpness"] < BLUR_BELOW:
        reasons.append("blurred")
    if m["brightness"] < DARK_BELOW:
        reasons.append("dark")
    if m["brightness"] > GLARE_ABOVE:
        reasons.append("glare")
    if m["contrast"] < FLAT_BELOW:
        reasons.append("low_contrast")
    if m["oblique"]:
        reasons.append("oblique")
    if m["layout"] == "two-line":
        reasons.append("two_line")
    if ocr_conf is not None and ocr_conf < LOW_CONF:
        reasons.append("low_confidence")
    problems = sum(r in IMAGE_PROBLEMS for r in reasons)
    quality = "poor" if "too_small" in reasons or problems >= 2 else "marginal" if reasons else "good"
    return quality, reasons


def grade_file(path: Path, bbox=None, ocr_conf: float | None = None) -> dict | None:
    """Metrics plus grade for a crop on disk; None when it cannot be read (or OpenCV is missing)."""
    if not AVAILABLE:
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    m = assess(img, bbox)
    m["quality"], m["reasons"] = classify(m, ocr_conf)
    return m
