"""Vehicle type and colour for a plate read.

Type. A plate is bound to the smallest COCO vehicle box that contains it (containment, not
IoU: a plate is ~1/45 of a car's area, so IoU with a perfect parent is ~0.02). Rules:
  - at least 80% of the plate lies inside the vehicle box
  - plate width is 5-70% of the vehicle's width, the plate is not in the top quarter, and its
    centre is within 30% of the vehicle's width from the vehicle's centre
  - two plausible parents of different classes and similar size -> no answer
  - a smaller vehicle wins only when its box sits inside the larger one (a car in front of a
    bus); two vehicles side by side with the plate in their overlap -> no answer
  - no parent -> no answer. That is the normal case for auto-rickshaws (not a COCO class),
    occluded vehicles and synthetic scenes; the sighting keeps a NULL, not a guess.
Bicycles are not candidates: they carry no registration plate.

Colour. A heuristic, not a model: hue/value statistics over the flat body panels of the
bound vehicle (glass, plate, tyres, box margins and textured pixels are masked out), mapped
to a closed palette. It abstains when the frame is monochrome (IR / night mode), the panel
is blown out or crushed, the box is too small, or the vehicle is a two-wheeler (the pixels
would be the rider's clothes). Confidence is a hand-tuned score, not a probability.

Measured on real traffic (stock footage, eye-labelled vehicle views): the first version,
tuned on flat test colours, was right 48% of the time; sky reflections read as blue and
dark glass pulled white cars to black. This version needs strong saturation before calling
a colour (S >= 90), judges lightness on the brighter pixels, and reports white and silver as
one class, because telling them apart needs an exposure reference a CCTV frame does not
have. It was right on 22 of 27 held-out views (81%): about half the same vehicles as the
tuning set, so not an independent estimate, and nothing is measured on Gujarat footage yet.

Per-read answers are voted across the whole plate track in the tracker; see tracker.pick().
"""
from __future__ import annotations

import cv2
import numpy as np

from .objects import COLOURED, Obj

PLATED = ("car", "motorcycle", "bus", "truck")
MIN_PARENT_W = 64                       # px; below this the panel sample is too small
MONO_RANGE = 12                         # p95 channel spread under which a frame is IR/greyscale
PALETTE = ("white/silver", "grey", "black", "red", "maroon", "orange", "yellow", "beige",
           "brown", "green", "blue", "violet")

Rect = tuple[int, int, int, int]        # x, y, w, h


def _area(r: Rect) -> int:
    return max(0, r[2]) * max(0, r[3])


def containment(inner: Rect, outer: Rect) -> float:
    """Share of `inner` that lies inside `outer`."""
    ix = max(0, min(inner[0] + inner[2], outer[0] + outer[2]) - max(inner[0], outer[0]))
    iy = max(0, min(inner[1] + inner[3], outer[1] + outer[3]) - max(inner[1], outer[1]))
    a = _area(inner)
    return ix * iy / a if a else 0.0


def bind_parent(plate: Rect, objs: list[Obj] | None) -> Obj | None:
    if not objs:
        return None
    cands = []
    for o in objs:
        if o.label not in PLATED or containment(plate, o.box) < 0.8:
            continue
        if not 0.05 <= plate[2] / max(1, o.box[2]) <= 0.7:
            continue
        if plate[1] + plate[3] / 2 < o.box[1] + 0.25 * o.box[3]:
            continue
        if abs(plate[0] + plate[2] / 2 - (o.box[0] + o.box[2] / 2)) > 0.3 * o.box[2]:
            continue             # plates sit near the middle of the vehicle, not at its edge
        cands.append(o)
    if not cands:
        return None
    cands.sort(key=lambda o: _area(o.box))
    best = cands[0]
    for other in cands[1:]:
        if other.label == best.label:
            continue
        if _area(other.box) < 1.5 * _area(best.box):
            return None          # e.g. one vehicle boxed as both car and truck: refuse to pick
        if containment(best.box, other.box) < 0.7:
            return None          # two vehicles side by side, plate in the overlap: ambiguous
    return best                  # smaller vehicle in front of a larger one: its plate is the visible one


def frame_has_colour(img: np.ndarray) -> bool:
    """False for IR / night-mode / greyscale frames, where any colour name would be invented."""
    sub = img[::16, ::16].astype(np.int16)
    return float(np.percentile(sub.max(axis=2) - sub.min(axis=2), 95)) >= MONO_RANGE


def body_pixels(img: np.ndarray, parent: Rect, plate: Rect) -> np.ndarray | None:
    """Flat body-panel pixels of the vehicle, as an N x 3 BGR array."""
    H, W = img.shape[:2]
    x0, y0 = max(0, parent[0]), max(0, parent[1])
    x1, y1 = min(W, parent[0] + parent[2]), min(H, parent[1] + parent[3])
    if x1 - x0 < MIN_PARENT_W or y1 - y0 < 24:
        return None
    roi = img[y0:y1, x0:x1]
    scale = 192.0 / roi.shape[1] if roi.shape[1] > 192 else 1.0
    if scale != 1.0:
        roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = roi.shape[:2]
    mask = np.zeros((h, w), bool)
    mask[int(h * 0.30): int(h * 0.88), int(w * 0.08): int(w * 0.92)] = True   # no glass, tyres, edges
    pad = plate[3] * 0.5
    px0, py0 = int((plate[0] - x0 - pad) * scale), int((plate[1] - y0 - pad) * scale)
    px1, py1 = int((plate[0] + plate[2] - x0 + pad) * scale), int((plate[1] + plate[3] - y0 + pad) * scale)
    mask[max(0, py0): max(0, py1), max(0, px0): max(0, px1)] = False
    if mask.sum() < 150:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    texture = cv2.blur(np.abs(cv2.Laplacian(gray, cv2.CV_16S)).astype(np.float32), (5, 5))
    mask &= texture <= np.percentile(texture[mask], 60)                          # flat panels only
    return roi[mask]


def classify_colour(bgr: np.ndarray) -> tuple[str | None, float]:
    """(palette name, confidence) for N x 3 BGR panel pixels; (None, 0) when it should abstain."""
    if bgr is None or len(bgr) < 150:
        return None, 0.0
    hsv = cv2.cvtColor(bgr.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    H, S, V = (hsv[:, i].astype(np.float32) for i in range(3))
    chroma = (S >= 90) & (V >= 55)       # sky reflections on silver paint reach S~60-80; paint is higher.
    frac = float(chroma.mean())          # No upper V bound: a yellow taxi in sun is V=255.
    v75 = float(np.percentile(V, 75))    # lightness from the brighter pixels: shade and glass pull down
    if v75 > 245 or v75 < 22:
        return None, 0.0                 # blown out or crushed
    if frac < 0.35:
        name = "black" if v75 < 70 else "grey" if v75 < 120 else "white/silver"
        margin = min(abs(v75 - c) for c in (70, 120))        # distance from the nearest cut
        return name, min(0.85, 0.35 + 0.02 * margin)
    h, s, v = H[chroma], S[chroma], V[chroma]
    bins = np.bincount((h / 5).astype(np.int32), weights=(s / 255.0) * (v / 255.0), minlength=36)[:36]
    smooth = np.convolve(np.concatenate([bins[-2:], bins, bins[:2]]), np.ones(3), mode="same")[2:-2]
    peak = int(np.argmax(smooth))
    total = float(smooth.sum())
    purity = float(smooth[(peak - 1) % 36] + smooth[peak] + smooth[(peak + 1) % 36]) / total if total else 0.0
    hue = peak * 5 + 2.5                 # OpenCV hue, 0-180
    med_v, med_s = float(np.median(v)), float(np.median(s))
    if hue >= 160 or hue < 6:
        name = "maroon" if med_v < 120 else "red"
    elif hue < 34:
        name = ("brown" if med_v < 145 else "beige" if med_s < 110
                else "yellow" if hue >= 22 else "orange")
    elif hue < 85:
        name = "green"
    elif hue < 135:
        name = "blue"
    else:
        name = "violet"
    return name, min(0.9, 0.10 + 0.55 * purity + 0.20 * min(1.0, len(h) / 1200))


def vehicle_colour(img: np.ndarray, parent: Obj, plate: Rect) -> tuple[str, float] | None:
    if parent.label not in COLOURED:
        return None
    name, conf = classify_colour(body_pixels(img, parent.box, plate))
    return (name, conf) if name else None
