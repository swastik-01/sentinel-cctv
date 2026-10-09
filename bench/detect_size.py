"""Plate detector input size on our own clips: how many painted plates would the product read at 640, 960 or 1280?

Why: the worker runs the plate detector at imgsz=640 on every camera (detect.py). A 1920x1080 frame is shrunk three
times, so a plate 55 px wide in the stream (AMD-TRAF-001's median) reaches the detector 18 px wide. The clips' plates
were found and painted by the same detector at 1280 on native-resolution tiles (feedsim/realclip.py), so the plates
are there to be found; the question is what the product's size loses, and what a larger size would cost.

Each size runs the product's path on the same sampled frames: the YOLO plate detector at that size (conf
MIN_PLATE_CONF), the classical text-line finder unioned in as DETECTOR=both does, the worker's padded crop,
PlateOCR (ocr.py) and the worker's gate (check_read). A read is exact when it equals a plate painted in that frame
(`<CODE>.plates.json`, first_frame to last_frame). Capture here is per sampled frame and per plate, not per stored
sighting: no tracker, no vote. Clips are our own feeds (Pexels stock footage with synthetic registrations painted on).

CPU only, 2 threads, and the process lowers its own priority below normal: a live worker owns the GPU and must not
slow (its threads run at normal priority and come first).
Times are CPU times on a shared laptop: compare sizes within one run only.

    PYTHONUTF8=1 uv run --no-sync python bench/detect_size.py [--every 25] [--out bench/results/detect_size.md]
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # a live worker owns the GPU
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import ctypes  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import defaultdict  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from sentinel_analytics.config import get_settings  # noqa: E402
from sentinel_analytics.detect import _iou, classical_candidates  # noqa: E402
from sentinel_analytics.ocr import PlateOCR  # noqa: E402
from sentinel_analytics.worker import check_read  # noqa: E402
from sentinel_common import normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
MEDIA = ROOT / "feedsim" / "media"
CAMS = ("AMD-TRAF-001", "AMD-TRAF-002")
SIZES = (640, 960, 1280)
_spec = importlib.util.spec_from_file_location("anpr_eval", ROOT / "scripts" / "anpr_eval.py")
anpr_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anpr_eval)


def lower_priority() -> None:
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
    else:
        os.nice(10)


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=25, help="analyse every N-th frame of the 25 fps clip (25 = 1 per s)")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "detect_size.md"))
    a = ap.parse_args()
    lower_priority()
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(2)
    s = get_settings()
    model = YOLO(str(ROOT / s.plate_model))
    ocr = PlateOCR()
    cams = {c["code"]: c for c in yaml.safe_load((ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]}

    res: dict = defaultdict(lambda: defaultdict(float))            # (cam, size) -> counters
    caught: dict = defaultdict(set)                                  # (cam, size) -> painted plates read exactly
    widths: dict = defaultdict(list)                                 # (cam, size) -> plate box width of exact reads
    shown_s: dict = {}
    for cam in CAMS:
        gt = json.loads((MEDIA / f"{cam}.plates.json").read_text(encoding="utf-8"))
        truth = anpr_eval.load_truth(cams[cam])
        shown_s[cam] = truth["plates"]          # plate -> seconds painted on screen
        painted = [(normalise_plate(p["plate"]), p["first_frame"], p["last_frame"]) for p in gt["plates"]]
        cap = cv2.VideoCapture(str(MEDIA / f"{cam}.mp4"))
        idx = -1
        while True:
            ok = cap.grab()
            if not ok:
                break
            idx += 1
            if idx % a.every:
                continue
            ok, img = cap.retrieve()
            if not ok:
                continue
            here = {p for p, f0, f1 in painted if f0 <= idx <= f1}
            classical = classical_candidates(img)
            for size in SIZES:
                t0 = time.perf_counter()
                r = model.predict([img], conf=s.min_plate_conf, imgsz=size, verbose=False, device="cpu")[0]
                dt = time.perf_counter() - t0
                boxes = [(int(x1), int(y1), int(x2 - x1), int(y2 - y1), float(b.conf[0]))
                         for b in r.boxes for x1, y1, x2, y2 in [b.xyxy[0].tolist()]]
                yolo_n = len(boxes)
                boxes += [c for c in classical if not any(_iou(c, d) > 0.4 for d in boxes[:yolo_n])]
                crops = []
                for x, y, w, h, _ in boxes:
                    pad = int(h * 0.15)
                    crops.append(img[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad])
                k = res[(cam, size)]
                k["frames"] += 1
                k["ms"] += dt * 1000
                k["painted"] += len(here)
                k["yolo boxes"] += yolo_n
                k["boxes"] += len(boxes)
                for i, ((text, conf), box) in enumerate(zip(ocr.read_many(crops), boxes)):
                    if check_read(text, conf, s.min_ocr_conf, s.max_letters_from_digits) != "ok":
                        continue
                    norm = normalise_plate(text)
                    src = "yolo" if i < yolo_n else "classical"
                    k["reads"] += 1
                    if norm in here:
                        k["exact"] += 1
                        k[f"exact from {src}"] += 1
                        caught[(cam, size)].add(norm)
                        widths[(cam, size)].append(box[2])
                    elif here and min(anpr_eval.edits(norm, p) for p in here) <= 2:
                        k["near"] += 1
        cap.release()

    L = ["# Plate detector input size on our own clips", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/detect_size.py`: every {a.every}th frame of the "
         f"60 s clips `feedsim/media/AMD-TRAF-001.mp4` and `AMD-TRAF-002.mp4` (1920x1080, 25 fps; Pexels stock footage "
         "with synthetic registrations painted on, not real Gujarat plates), through the product's plate path at each "
         "detector size: YOLO plate detector (conf "
         f"{s.min_plate_conf:g}) plus the classical finder, padded crop, `PlateOCR`, the worker's gate. CPU only, 2 threads, "
         "below-normal priority, on the laptop while a live worker used the GPU. No tracker or vote: counts are per sampled "
         "frame. Counts and rates only.", "",
         "| Camera | Detector size | Frames | Painted plates in those frames | YOLO boxes | Gated reads | Exact reads "
         "(of a plate painted in that frame) | Exact from YOLO / classical | Near (1-2 edits) | Other gated reads | "
         "Exact of gated reads | Painted plates read exactly at least once, of plates shown >= 1 s | Median box width "
         "of exact reads (px) | YOLO CPU ms per frame |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cam in CAMS:
        long_ = {p for p, sec in shown_s[cam].items() if sec >= 1.0}
        for size in SIZES:
            k = res[(cam, size)]
            got = caught[(cam, size)] & long_
            w = widths[(cam, size)]
            L.append(f"| {cam} | {size} | {int(k['frames'])} | {int(k['painted'])} | {int(k['yolo boxes'])} | "
                     f"{int(k['reads'])} | {pct(int(k['exact']), int(k['painted']))} | "
                     f"{int(k['exact from yolo'])} / {int(k['exact from classical'])} | {int(k['near'])} | "
                     f"{int(k['reads'] - k['exact'] - k['near'])} | {pct(int(k['exact']), int(k['reads']))} | "
                     f"{pct(len(got), len(long_))} | {np.median(w) if w else float('nan'):.0f} | "
                     f"{k['ms'] / max(1, k['frames']):.0f} |")
    L += ["", "## Reading it", "",
          "- Exact reads over painted plates in the sampled frames is a per-frame read rate: a plate painted far away "
          "or half hidden counts in the denominator, so it is far below 100% at any size.",
          "- Capture here is whether a single frame, sampled once a second, reads the plate; the product analyses about "
          "4.5 frames a second and votes, so its capture (`anpr_eval_current.md`) is higher. Compare sizes, not levels.",
          "- Other gated reads match no plate painted in that frame by 2 edits or fewer: a real plate the painter missed "
          "(its characters are unlabelled), a painted plate outside its logged frames, or text that is not a plate. The "
          "product's tracker needs 2 reads (or one confident read on a slow camera) before it stores any of them.",
          "- The classical finder runs on a 960 px copy whatever the detector size; it is unioned in as in the product.",
          "- CPU milliseconds are only for comparing sizes; on the GPU the cost ratio is similar (about the square of "
          "the size ratio) but the absolute time is far smaller.", ""]
    text = "\n".join(L)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
