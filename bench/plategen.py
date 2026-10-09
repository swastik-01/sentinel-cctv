"""Synthetic Indian number plates for fine-tuning the plate OCR (fast-plate-ocr CCT).

Plates are drawn on feedsim/realclip.py's masters (520x112 one-row, 360x220 two-row, text fitted
to the plate), set on a vehicle-like background, shrunk to the size a CCTV camera sees them,
degraded at that size, and cropped the way the worker crops them (worker.py: the plate box plus
15% of its height). Two rules keep the benchmarks clean: no registration the simulator, the
sandbox or the frozen eval sets have shown is ever drawn, and no DejaVu font is used (the
simulator's own plates are drawn in it). Real sandbox crops are never trained on; the QA step
reads only their summary statistics. Tahoma Bold is held out for a third of the test split.

    PYTHONUTF8=1 uv run --no-sync python bench/plategen.py              # val, test, train, then QA
    PYTHONUTF8=1 uv run --no-sync python bench/plategen.py --qa-only

Writes data/ocr-train/{split}/*.png, {split}.csv (image_path relative to the CSV, which is what
the fast-plate-ocr trainer expects), {split}_meta.csv, summary.json, qa.md and sheet_val.jpg.
Prints counts only.
"""
from __future__ import annotations

import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")   # a live worker owns the GPU
os.environ.setdefault("OMP_NUM_THREADS", "2")

import argparse
import csv
import json
import random
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sentinel_common import looks_like_indian_plate, normalise_plate
from sentinel_common.plates import STATE_CODES

cv2.setNumThreads(1)
ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "gov-sandbox" / "eye" / "labels.csv"
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
FONTS = {   # key: (file, variation)
    "bahn-bold-semicond": ("bahnschrift.ttf", "Bold SemiCondensed"),
    "bahn-bold-cond": ("bahnschrift.ttf", "Bold Condensed"),
    "arial-narrow-bold": ("ARIALNB.TTF", None),
    "arial-bold": ("arialbd.ttf", None),
    "impact": ("impact.ttf", None),
    "tahoma-bold": ("tahomabd.ttf", None),
}
TEST_FONT = "tahoma-bold"                     # held out: test split only
DROPPED = ("impact",)                         # the current model misreads it even clean (qa.md); widening did not help
TRAIN_FONTS = [k for k in FONTS if k != TEST_FONT and k not in DROPPED]
SERIES = "ABCDEFGHJKLMNPRSTUVWXYZ"            # no I or O, as in realclip.py
COMMERCIAL = "TUVWXYZ"
GJ_RTO = [f"{i:02d}" for i in [*range(1, 28), *range(30, 41)]]
OTHER_STATES = sorted(STATE_CODES - {"GJ"})
BANDS = [("50-110", 50, 110, 0.50), ("110-200", 110, 200, 0.35), ("40-50", 40, 50, 0.15)]
PAINT = [(235, 235, 235), (180, 180, 175), (110, 110, 110), (25, 25, 25), (30, 30, 170),
         (140, 70, 30), (40, 20, 90), (170, 200, 215), (40, 190, 230), (60, 120, 40)]   # BGR


@lru_cache(maxsize=None)
def font(key: str, size: int) -> ImageFont.FreeTypeFont:
    file, variation = FONTS[key]
    f = ImageFont.truetype(str(FONT_DIR / file), size)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:  # noqa: BLE001  (no variation support: plain Bahnschrift)
            pass
    return f


def valid(label: str) -> bool:
    return len(label) <= 10 and normalise_plate(label) == label and looks_like_indian_plate(label)


def forbidden_plates() -> set[str]:
    """Every registration the simulator, the sandbox or the eval sets have shown. Never drawn, never printed."""
    texts = [(ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8")]
    paths = [*(ROOT / "feedsim" / "media").glob("*.plates.json"), *(ROOT / "data").glob("ocr-eval/*/manifest.csv"),
             ROOT / "data" / "edge-watchlist.json", LABELS]
    texts += [p.read_text(encoding="utf-8") for p in paths if p.exists()]
    texts.append(" ".join(p.stem for p in (ROOT / "data" / "crops").glob("*/*.jpg")))   # names carry the read
    out = set()
    if LABELS.exists():
        with open(LABELS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out |= {normalise_plate(r.get(k) or "") for k in ("stored", "true_plate")}
    for t in texts:
        out |= {normalise_plate(tok) for tok in re.findall(r"[A-Z0-9]{8,11}", t.upper())}
    return {p for p in out if looks_like_indian_plate(p)}


def registration(rng: random.Random, kind: str, yellow: bool) -> list[str]:
    """The groups as printed, e.g. state, RTO, series, number."""
    num = f"{rng.randint(1, 9999):04d}"
    if kind == "BH":
        return [str(rng.randint(21, 26)), "BH", num, "".join(rng.choice(SERIES) for _ in range(rng.choice((1, 2))))]
    state, rto = ("GJ", rng.choice(GJ_RTO)) if kind == "GJ" else (rng.choice(OTHER_STATES), f"{rng.randint(1, 60):02d}")
    first = rng.choice(COMMERCIAL) if yellow and rng.random() < 0.85 else rng.choice(SERIES)
    series = first + (rng.choice(SERIES) if rng.random() < 0.85 else "")
    return [state, rto, series, num]


def pick_style(rng: random.Random) -> tuple[list[str], dict]:
    r = rng.random()
    kind = "GJ" if r < 0.80 else "BH" if r < 0.88 else "other"
    if kind == "BH":
        colour = "white" if rng.random() < 0.85 else "green"
    else:   # weights chosen so the whole set lands near 55/30/10/5 with BH included
        colour = rng.choices(["white", "yellow", "green", "other"], [52, 33, 10, 5])[0]
    groups = registration(rng, kind, colour == "yellow")
    style = {"kind": kind, "colour": colour, "two_rows": rng.random() < 0.30, "ind": rng.random() < 0.80,
             "sep": rng.choices(["", " ", "-"], [50, 40, 10])[0]}
    return groups, style


def plate_colours(colour: str, rng: random.Random) -> tuple[tuple, tuple]:
    """(background, text) in RGB, with some fading."""
    j = lambda lo, hi: rng.randint(lo, hi)  # noqa: E731
    dark = (j(5, 40),) * 3
    if colour == "white":
        v = j(205, 250)
        return (v, v - j(0, 8), v - j(0, 15)), dark
    if colour == "yellow":
        return (j(220, 255), j(175, 215), j(0, 50)), dark
    if colour == "green":
        return (j(0, 30), j(105, 150), j(55, 100)), ((j(225, 255),) * 3 if rng.random() < 0.7 else (245, 205, 20))
    bg = (j(10, 35),) * 3                     # rental: yellow on black, or old white on black
    return bg, ((245, j(195, 220), j(0, 40)) if rng.random() < 0.7 else (j(220, 250),) * 3)


def text_mask(text: str, f: ImageFont.FreeTypeFont, stroke: int) -> Image.Image:
    b = f.getbbox(text, stroke_width=stroke)
    m = Image.new("L", (b[2] - b[0], b[3] - b[1]), 0)
    ImageDraw.Draw(m).text((-b[0], -b[1]), text, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
    return m


def draw_plate(groups: list[str], style: dict, font_key: str, rng: random.Random) -> np.ndarray:
    """Master plate, BGR. Sizes and layout follow realclip._plate_master."""
    two = style["two_rows"]
    W, H = (360, 220) if two else (520, 112)
    W = int(W * rng.uniform(0.94, 1.06))
    u = 1.5 if two else 1.0
    bg, fg = plate_colours(style["colour"], rng)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    inset, bw = int(rng.randint(2, 6) * u), int(rng.randint(3, 6) * u)
    if rng.random() < 0.85:
        d.rounded_rectangle([inset, inset, W - 1 - inset, H - 1 - inset], radius=rng.randint(0, 12),
                            outline=fg, width=bw)
    x0, x1 = inset + bw + int(3 * u), W - inset - bw - int(3 * u)
    if style["ind"]:
        sw = int(W * (0.11 if two else 0.07) * rng.uniform(0.8, 1.2))
        top, bot = inset + bw + int(2 * u), H - inset - bw - int(2 * u)
        strip = rng.random() < 0.5
        ink = (255, 255, 255) if strip else (20, 60, 170)
        if strip:
            d.rectangle([x0, top, x0 + sw, bot], fill=(20, rng.randint(50, 90), rng.randint(150, 200)))
        r = int(sw * 0.3)
        d.ellipse([x0 + sw // 2 - r, top + 3, x0 + sw // 2 + r, top + 3 + 2 * r], outline=ink, width=max(1, r // 3))
        size = max(6, int(sw * 0.6))          # "IND" reads upwards and must fit under the ring
        while size > 6 and d.textlength("IND", font=font("arial-bold", size)) > 0.9 * (bot - top - 2 * r - 10):
            size -= 1
        tag = text_mask("IND", font("arial-bold", size), 0).rotate(90, expand=True)
        tx, ty = x0 + (sw - tag.width) // 2, bot - tag.height - 2
        im.paste(ink, (tx, ty, tx + tag.width, ty + tag.height), tag)
        x0 += sw + int(4 * u)
    sep = style["sep"]
    cut = 2 if style["kind"] == "BH" else 3
    lines = [sep.join(groups[:cut]), sep.join(groups[cut:])] if two else [sep.join(groups)]
    stroke = rng.choice((0, 0, 1))
    aw, ah = (x1 - x0) * rng.uniform(0.86, 0.97), H * rng.uniform(0.76, 0.90)
    # Shrink-to-fit as in realclip, but as tall as the plate allows and then condensed to the width,
    # the way plate lettering is: a wide face on a two-row plate otherwise comes out tiny.
    boxes = [d.textbbox((0, 0), ln, font=font(font_key, 100), stroke_width=stroke) for ln in lines]
    tw, th = max(b[2] - b[0] for b in boxes), sum(b[3] - b[1] for b in boxes) * 1.25
    size = 100 * ah / th
    hs = min(rng.uniform(0.85, 1.05), aw / (tw * size / 100))
    if hs < 0.7:
        size, hs = size * hs / 0.7, 0.7
    masks = [text_mask(ln, font(font_key, max(8, int(size))), stroke) for ln in lines]
    masks = [m.resize((max(1, round(m.width * hs)), m.height), Image.LANCZOS) for m in masks]
    y = (H - sum(m.height for m in masks) - 0.25 * sum(m.height for m in masks[:-1])) / 2
    for m in masks:
        x = int(x0 + (x1 - x0 - m.width) / 2)
        im.paste(fg, (x, int(y), x + m.width, int(y) + m.height), m)
        y += m.height * 1.25
    if rng.random() < 0.15:                   # rivets
        for fx in (0.3, 0.7):
            cx, r = int(W * fx), int(3 * u)
            d.ellipse([cx - r, inset + bw + 2, cx + r, inset + bw + 2 + 2 * r], fill=(120, 120, 120))
    return np.asarray(im)[:, :, ::-1].copy()


def scene(plate: np.ndarray, rng: random.Random, nrng: np.random.Generator, clean: bool):
    """The plate on a bumper-like background with a little tilt and yaw. Returns the canvas and plate corners."""
    h, w = plate.shape[:2]
    mx, my = int(0.12 * w + 0.3 * h) + 4, int(0.5 * h + 0.1 * w) + 4   # room for tilt, pad and jitter
    Wc, Hc = w + 2 * mx, h + 2 * my
    base = np.array(rng.choice(PAINT), np.float32) * rng.uniform(0.7, 1.1)
    shade = cv2.resize(nrng.normal(1, 0.12, (4, 8)).astype(np.float32), (Wc, Hc), interpolation=cv2.INTER_LINEAR)
    shade *= np.linspace(rng.uniform(0.8, 1.1), rng.uniform(0.8, 1.1), Hc, dtype=np.float32)[:, None]
    canvas = base * shade[..., None]
    for _ in range(rng.randint(0, 3)):        # bumper lines, grille bars
        y = rng.randint(0, Hc - 1)
        canvas[y: y + rng.randint(1, int(0.15 * h) + 2)] *= rng.uniform(0.2, 0.7)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    c = np.float32([Wc / 2, Hc / 2])
    q = src - np.float32([w / 2, h / 2])
    if not clean:
        yaw = rng.uniform(-0.08, 0.08)        # the nearer side looks taller
        q[:, 1] *= np.where(q[:, 0] < 0, 1 + yaw, 1 - yaw)
        q[:, 0] += q[:, 1] * rng.uniform(-0.05, 0.05)
        a = np.deg2rad(float(np.clip(nrng.normal(0, 1.5), -5, 5)))
        q = q @ np.float32([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    dst = (q + c).astype(np.float32)
    if rng.random() < 0.6:                    # dark plate holder
        e = rng.uniform(1.03, 1.12)
        cv2.fillConvexPoly(canvas, ((dst - c) * e + c).astype(np.int32), (rng.uniform(10, 50),) * 3)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(plate, M, (Wc, Hc), flags=cv2.INTER_LINEAR).astype(np.float32)
    mask = cv2.warpPerspective(np.full((h, w), 1, np.float32), M, (Wc, Hc))[..., None]
    canvas = warped * mask + canvas * (1 - mask)
    return np.clip(canvas, 0, 255).astype(np.uint8), dst


def jpeg(img: np.ndarray, q: int) -> np.ndarray:
    return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)


def motion_kernel(n: int, angle: float) -> np.ndarray:
    k = np.zeros((n, n), np.float32)
    k[n // 2, :] = 1
    k = cv2.warpAffine(k, cv2.getRotationMatrix2D(((n - 1) / 2, (n - 1) / 2), angle, 1), (n, n))
    return k / max(float(k.sum()), 1e-6)


def degrade(img: np.ndarray, rng: random.Random, nrng: np.random.Generator, text_h: float) -> tuple[np.ndarray, bool]:
    """Camera and codec damage at the plate's native size."""
    f = img.astype(np.float32)
    # A 6 px character under sigma 1.2 is unreadable, and a label on an unreadable crop teaches invention.
    s = rng.uniform(0, min(1.2, 0.12 * text_h))
    if rng.random() < 0.2:                    # motion blur, on top of mild focus blur only: both at once is mush
        s = min(s, 0.6)
        n = rng.randint(2, max(2, min(5, int(0.35 * text_h))))
        f = cv2.filter2D(f, -1, motion_kernel(n, rng.uniform(0, 180)))
    if s > 0.25:
        f = cv2.GaussianBlur(f, (0, 0), s)
    if rng.random() < 0.7:                    # CCTV edge enhancement: the sandbox crops show its halos
        k = rng.uniform(0.5, 2.0)
        f = f * (1 + k) - cv2.GaussianBlur(f, (0, 0), rng.uniform(0.8, 1.5)) * k
    f = np.clip(f, 0, 255)
    luma = f.mean(axis=2, keepdims=True)
    f = luma + (f - luma) * rng.uniform(0.35, 1.0)   # CCTV colour is washed out
    if rng.random() < 0.25:                   # low light: darker, flatter, noisier
        f = 255 * (f / 255) ** rng.uniform(1.2, 2.0) * rng.uniform(0.45, 0.8)
        sigma = rng.uniform(4, 12)
    else:                                     # auto exposure and a contrasty tone curve
        m = float(f.mean())
        f = (f - m) * rng.uniform(1.1, 1.8) + m * rng.uniform(0.9, 1.15)
        sigma = rng.uniform(0, 4)
    f = f + nrng.normal(0, sigma, f.shape[:2]).astype(np.float32)[..., None] \
        + nrng.normal(0, sigma / 3, f.shape).astype(np.float32)
    out = np.clip(f, 0, 255).astype(np.uint8)
    grey = rng.random() < 0.15               # IR at night
    if grey:
        out = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return jpeg(out, rng.randint(30, 80)), grey


def worker_crop(img: np.ndarray, box, rng: random.Random, jitter: float) -> np.ndarray:
    x, y, w, h = box
    x, y = x + rng.uniform(-jitter, jitter) * w, y + rng.uniform(-jitter, jitter) * h
    w, h = w * (1 + rng.uniform(-jitter, jitter)), h * (1 + rng.uniform(-jitter, jitter))
    x, y, w, h = (int(round(v)) for v in (x, y, w, h))
    pad = int(h * 0.15)                       # worker.py
    return img[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad]


def render(groups, style, font_key, rng, nrng, width: float, clean: bool = False):
    """One crop as the worker would hand it to OCR, or None when the worker would drop it."""
    plate = draw_plate(groups, style, font_key, rng)
    k = min(1.0, 3 * width / plate.shape[1])  # compose at 3x the final size: same anti-aliasing, far less work
    if k < 1:
        plate = cv2.resize(plate, (round(plate.shape[1] * k), round(plate.shape[0] * k)), interpolation=cv2.INTER_AREA)
    canvas, quad = scene(plate, rng, nrng, clean)
    bx, by, bw, bh = cv2.boundingRect(quad.astype(np.int32))
    sx = width / bw
    sy = sx if clean else sx * rng.uniform(0.95, 1.3)   # seen from the side: the width foreshortens
    small = cv2.resize(canvas, (max(1, round(canvas.shape[1] * sx)), max(1, round(canvas.shape[0] * sy))),
                       interpolation=cv2.INTER_AREA)
    grey = False
    if not clean:
        small, grey = degrade(small, rng, nrng, bh * sy * (0.33 if style["two_rows"] else 0.65))
    crop = worker_crop(small, (bx * sx, by * sy, bw * sx, bh * sy), rng, 0.0 if clean else 0.05)
    if crop.shape[1] < 40 or crop.shape[0] < 12:
        return None, grey
    if not clean and rng.random() < 0.5:
        crop = jpeg(crop, 85)
    return crop, grey


def read_labels(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [r["plate_text"] for r in csv.DictReader(f)]


def make_split(name: str, n: int, seed: int, avoid: set[str], out: Path) -> dict:
    rng, nrng = random.Random(seed), np.random.default_rng(seed)
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    for p in folder.glob("*.png"):
        p.unlink()
    seen, rows, meta, dropped = set(avoid), [], [], 0
    while len(rows) < n:
        i = len(rows)
        font_key = TEST_FONT if name == "test" and i % 3 == 0 else rng.choice(TRAIN_FONTS)
        groups, style = pick_style(rng)
        label = "".join(groups)
        assert valid(label)
        if label in seen:
            continue
        band, lo, hi, _ = rng.choices(BANDS, [b[3] for b in BANDS])[0]
        width = rng.uniform(lo, hi)
        crop, grey = render(groups, style, font_key, rng, nrng, width)
        if crop is None:
            dropped += 1
            continue
        seen.add(label)
        rel = f"{name}/{i:06d}.png"
        cv2.imwrite(str(out / rel), crop)
        rows.append((rel, label))
        meta.append((rel, font_key, "two" if style["two_rows"] else "one", style["colour"], style["kind"],
                     int(style["ind"]), band, round(width, 1), crop.shape[1], crop.shape[0], int(grey)))
        if len(rows) % 1000 == 0:
            print(f"[plategen] {name}: {len(rows)}/{n}", flush=True)
    with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_path", "plate_text"])
        w.writerows(rows)
    with open(out / f"{name}_meta.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_path", "font", "layout", "colour", "kind", "ind", "band", "plate_w", "crop_w", "crop_h",
                    "grey"])
        w.writerows(meta)
    return {"n": n, "seed": seed, "dropped_small": dropped}


def crop_stats(img: np.ndarray) -> list[float]:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return [img.shape[1], img.shape[0], float(g.mean()), float(g.std()), float(cv2.Laplacian(g, cv2.CV_64F).var())]


def qa(out: Path, forbidden: set[str], seed: int, per_font: int) -> None:
    from collections import Counter
    md = [f"# Synthetic plate set: QA ({date.today().isoformat()})", "",
          "Made by `bench/plategen.py`. Counts and statistics only: no plate text appears here.", ""]
    splits = {s: read_labels(out / f"{s}.csv") for s in ("train", "val", "test")}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8")) if (out / "summary.json").exists() else {}

    md += ["## (i) Labels", "", "| split | rows | invalid | over 10 chars | duplicates | in forbidden set | "
           "missing image | dropped as too small |", "|---|---|---|---|---|---|---|---|"]
    for s, labels in splits.items():
        paths = []
        if labels:
            with open(out / f"{s}.csv", encoding="utf-8") as f:
                paths = [r["image_path"] for r in csv.DictReader(f)]
        info = summary.get(s, {})
        md.append(f"| {s} | {len(labels)} | {sum(not valid(x) for x in labels)} | {sum(len(x) > 10 for x in labels)} | "
                  f"{len(labels) - len(set(labels))} | {len(set(labels) & forbidden)} | "
                  f"{sum(not (out / p).exists() for p in paths)} | {info.get('dropped_small', '-')} |")
    sets = {s: set(v) for s, v in splits.items()}
    md += ["", f"Overlap between splits: train-val {len(sets['train'] & sets['val'])}, train-test "
           f"{len(sets['train'] & sets['test'])}, val-test {len(sets['val'] & sets['test'])}. "
           f"Forbidden set (simulator, sandbox, eval-set and crop-name registrations): {len(forbidden)}.", ""]
    for s in splits:
        mp = out / f"{s}_meta.csv"
        if not mp.exists():
            continue
        with open(mp, encoding="utf-8") as f:
            m = list(csv.DictReader(f))
        md.append(f"**{s} mix** ({len(m)}): " + "; ".join(
            f"{col}: " + ", ".join(f"{k} {v / len(m):.0%}" for k, v in sorted(Counter(r[col] for r in m).items()))
            for col in ("kind", "colour", "layout", "ind", "grey", "band", "font")))
        md.append("")

    # (ii) the current model on clean, easy renders, per font
    import onnxruntime as ort
    from fast_plate_ocr import LicensePlateRecognizer
    so = ort.SessionOptions()
    so.intra_op_num_threads, so.inter_op_num_threads = 2, 1
    rec = LicensePlateRecognizer("cct-xs-v2-global-model", device="cpu", sess_options=so)
    md += ["## (ii) Current model on clean renders", "",
           f"`cct-xs-v2-global-model` (CPU), {per_font} renders per font, plate box 150-250 px wide, no degradation, "
           "no tilt, worker crop without jitter. Exact after `normalise_plate`. Gate: 90% per font.", "",
           "| font | exact | one-row | two-row | gate |", "|---|---|---|---|---|"]
    rng, nrng = random.Random(seed + 100), np.random.default_rng(seed + 100)
    for key in FONTS:
        crops, labels, layouts = [], [], []
        while len(crops) < per_font:
            groups, style = pick_style(rng)
            if "".join(groups) in forbidden:
                continue
            crop, _ = render(groups, style, key, rng, nrng, rng.uniform(150, 250), clean=True)
            crops.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            labels.append("".join(groups))
            layouts.append(style["two_rows"])
        preds = [normalise_plate(str(p.plate).replace("_", "")) for p in rec.run(crops)]
        ok = [p == t for p, t in zip(preds, labels)]
        one = [o for o, two in zip(ok, layouts) if not two]
        two = [o for o, two in zip(ok, layouts) if two]
        rate = sum(ok) / len(ok)
        note = ' (test only)' if key == TEST_FONT else ' (dropped: not used)' if key in DROPPED else ''
        md.append(f"| {key}{note} | {sum(ok)}/{len(ok)} ({rate:.0%}) | "
                  f"{sum(one)}/{len(one)} | {sum(two)}/{len(two)} | {'pass' if rate >= 0.9 else 'FAIL'} |")
        print(f"[plategen] qa font {key}: {rate:.0%}", flush=True)

    # (iii) the 50-110 px band against the labelled real sandbox crops
    with open(LABELS, encoding="utf-8") as f:
        real_paths = [ROOT / "data" / r["crop"].lstrip("/") for r in csv.DictReader(f)
                      if r["verdict"] in ("exact", "wrong", "one_off")]
    real = np.array([crop_stats(cv2.imread(str(p))) for p in real_paths if p.exists()])
    with open(out / "val_meta.csv", encoding="utf-8") as f:
        band = [r for r in csv.DictReader(f) if r["band"] == "50-110"]
    syn = np.array([crop_stats(cv2.imread(str(out / r["image_path"]))) for r in band])
    near = np.array([crop_stats(cv2.imread(str(out / r["image_path"]))) for r in band if float(r["plate_w"]) >= 90])
    md += ["", "## (iii) Realism: 50-110 px band against labelled real sandbox crops", "",
           f"Medians. Real: {len(real)} crops labelled exact, wrong or one_off in the sandbox review (one camera). "
           f"Synthetic: {len(syn)} val crops in the 50-110 px band; the last column is the {len(near)} of them with a "
           "plate box 90-110 px wide, nearer the real plates' size, for context. Within: the band's ratio.", "",
           "| statistic | real | synthetic 50-110 | ratio | within | synthetic 90-110 |", "|---|---|---|---|---|---|"]
    for i, name in enumerate(["crop width px", "crop height px", "grey mean", "grey std", "Laplacian variance"]):
        r, s = float(np.median(real[:, i])), float(np.median(syn[:, i]))
        dev = abs(s / r - 1)
        md.append(f"| {name} | {r:.1f} | {s:.1f} | {s / r:.2f} | "
                  f"{'15%' if dev <= 0.15 else '30%' if dev <= 0.30 else 'outside 30%'} | "
                  f"{float(np.median(near[:, i])) if len(near) else float('nan'):.1f} |")

    # (iv) contact sheet of val crops, labels are synthetic
    with open(out / "val.csv", encoding="utf-8") as f:
        first = list(csv.DictReader(f))[:48]
    cw, ch, cols = 240, 110, 6
    sheet = np.zeros((ch * 8, cw * cols, 3), np.uint8)
    for k, r in enumerate(first):
        img = cv2.imread(str(out / r["image_path"]))
        f_ = min((cw - 20) / img.shape[1], (ch - 34) / img.shape[0])
        img = cv2.resize(img, (max(1, int(img.shape[1] * f_)), max(1, int(img.shape[0] * f_))),
                         interpolation=cv2.INTER_NEAREST)   # nearest: show the real pixels
        y0, x0 = (k // cols) * ch + 6, (k % cols) * cw + 10
        sheet[y0: y0 + img.shape[0], x0: x0 + img.shape[1]] = img
        cv2.putText(sheet, r["plate_text"], (x0, (k // cols) * ch + ch - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out / "sheet_val.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    md += ["", "## (iv) Contact sheet", "", "`sheet_val.jpg`: the first 48 val crops (nearest-neighbour upscaled) "
           "with their synthetic labels.", ""]
    (out / "qa.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[plategen] wrote {out / 'qa.md'}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "ocr-train"))
    ap.add_argument("--n-train", type=int, default=40000)
    ap.add_argument("--n-val", type=int, default=2000)
    ap.add_argument("--n-test", type=int, default=3000)
    ap.add_argument("--splits", default="val,test,train")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--qa-per-font", type=int, default=200)
    ap.add_argument("--qa-only", action="store_true")
    ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    forbidden = forbidden_plates()
    print(f"[plategen] forbidden registrations: {len(forbidden)}", flush=True)
    if not a.qa_only:
        sizes = {"train": a.n_train, "val": a.n_val, "test": a.n_test}
        seeds = {"val": a.seed + 1, "test": a.seed + 2, "train": a.seed + 3}
        sp = out / "summary.json"
        summary = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
        for name in a.splits.split(","):
            others = set().union(*(read_labels(out / f"{s}.csv") for s in sizes if s != name))
            summary[name] = make_split(name, sizes[name], seeds[name], forbidden | others, out)
            sp.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            print(f"[plategen] {name}: {summary[name]}", flush=True)
    if not a.no_qa:
        qa(out, forbidden, a.seed, a.qa_per_font)


if __name__ == "__main__":
    main()
