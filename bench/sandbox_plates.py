"""Can plates be read on the sandbox cameras at all? Runs the worker's own stages on live frames read through
Sentinel's relay: YOLO plate boxes (at the worker's 640 px and at 1280 px), the classical candidates, OCR, the
OCR confidence floor and the Indian-plate check. Frames are held in memory only; nothing is recorded.
Writes bench/results/sandbox_plates.md.

    uv run --no-sync python bench/sandbox_plates.py                       # all 30 cameras, 20 frames each
    uv run --no-sync python bench/sandbox_plates.py --frames 40 CAM12 CAM14
"""
from __future__ import annotations

import argparse
import os
import statistics
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import cv2  # noqa: E402

from sentinel_analytics.config import get_settings  # noqa: E402
from sentinel_analytics.detect import PlateDetector, classical_candidates  # noqa: E402
from sentinel_analytics.ocr import PlateOCR  # noqa: E402
from sentinel_common import looks_like_indian_plate, normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
SIZES = (640, 1280)


def grab(code: str, n: int, every: float = 0.5, limit: float = 90.0) -> list:
    """n frames about `every` s apart, read live through the relay (retrying once if an idle on-demand
    relay is still starting)."""
    for _ in range(2):
        cap = cv2.VideoCapture(f"rtsp://localhost:8554/{code}", cv2.CAP_FFMPEG)
        frames, t_next, t0 = [], 0.0, time.monotonic()
        while len(frames) < n and time.monotonic() - t0 < limit:
            if not cap.grab():
                if not cap.isOpened():
                    break
                continue
            if time.monotonic() >= t_next:
                ok, img = cap.retrieve()
                if ok and img is not None and img.size:
                    frames.append(img)
                    t_next = time.monotonic() + every
        cap.release()
        if frames:
            return frames
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cameras", nargs="*")
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "sandbox_plates.md"))
    a = ap.parse_args()
    cams = a.cameras or [f"CAM{i:02d}" for i in range(1, 31)]
    s = get_settings()
    det, ocr = PlateDetector(), PlateOCR()
    rows, reads_all = [], []
    started = datetime.now(IST)
    for code in cams:
        frames = grab(code, a.frames)
        if not frames:
            rows.append((code, 0, "", {}, [], None))
            print(f"{code}: no frames", flush=True)
            continue
        h, w = frames[0].shape[:2]
        lum = statistics.mean(float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()) for f in frames)
        stats: dict[int, Counter] = {}
        widths: dict[int, list[int]] = {}
        valid_reads = []
        for size in SIZES:
            c, ws = Counter(), []
            results = det.model.predict(frames, conf=s.min_plate_conf, imgsz=size, verbose=False, device=det.device) \
                if det.model else [None] * len(frames)
            for img, r in zip(frames, results):
                boxes = []
                if r is not None:
                    for b in r.boxes:
                        x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
                        boxes.append((x1, y1, x2 - x1, y2 - y1))
                        ws.append(x2 - x1)
                if size == SIZES[0]:
                    boxes += [(x, y, bw, bh) for (x, y, bw, bh, _) in classical_candidates(img)]
                crops = [img[max(0, y - int(bh * .15)): y + bh + int(bh * .15), max(0, x - int(bh * .15)): x + bw + int(bh * .15)]
                         for (x, y, bw, bh) in boxes]
                c["candidates"] += len(boxes)
                for (text, conf) in (ocr.read_many(crops) if crops else []):
                    norm = normalise_plate(text or "")
                    if text and conf >= s.min_ocr_conf:
                        c["ocr_ok"] += 1
                        if looks_like_indian_plate(norm):
                            c["valid"] += 1
                            valid_reads.append((code, size, norm, round(conf, 2)))
            stats[size], widths[size] = c, ws
        rows.append((code, len(frames), f"{w}x{h}", {k: (stats[k], widths[k]) for k in SIZES}, valid_reads, lum))
        reads_all += valid_reads
        print(f"{code}: {len(frames)} frames {w}x{h} brightness {lum:.0f} | " + " | ".join(
            f"{k}px: {len(widths[k])} plate boxes, median width {int(statistics.median(widths[k])) if widths[k] else 0} px, "
            f"{stats[k]['valid']} valid reads" for k in SIZES), flush=True)

    L = ["# Sandbox cameras: can plates be read?", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/sandbox_plates.py`; frames read live "
         f"{started:%Y-%m-%d %H:%M}–{datetime.now(IST):%H:%M} IST through Sentinel's relay, {a.frames} per camera about "
         "0.5 s apart, held in memory only. The sandbox replays fixed recorded clips, each camera's from one time of "
         "day and looping, so the light a camera shows is its clip's, whatever the time of this run; the traffic "
         "depends on where its loop is.", "",
         f"Stages as the worker runs them: YOLO plate detector at confidence ≥ {s.min_plate_conf} (the worker uses 640 px; "
         f"1280 px shown for comparison), plus the classical text-line candidates at 640 px; OCR (`{s.ocr_model}`) at "
         f"confidence ≥ {s.min_ocr_conf}; then the Indian-plate format check.", "",
         "Brightness is the mean grey level (0–255) of the frames read. It describes the camera's clip, not the time of "
         "day of this run: roughly, under 60 is a clip recorded at night.", "",
         "| Camera | Frames | Frame size | Brightness | Plate boxes 640 px | Median width 640 (px) | Plate boxes 1280 px | "
         "Median width 1280 (px) | OCR ≥ floor (640 / 1280) | Valid Indian plates (640 / 1280) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for code, n, size, st, _, lum in rows:
        if not n:
            L.append(f"| {code} | 0 | | | | | | | | |")
            continue
        (c6, w6), (c12, w12) = st[640], st[1280]
        L.append(f"| {code} | {n} | {size} | {lum:.0f} | {len(w6)} | {int(statistics.median(w6)) if w6 else '—'} | {len(w12)} | "
                 f"{int(statistics.median(w12)) if w12 else '—'} | {c6['ocr_ok']} / {c12['ocr_ok']} | "
                 f"{c6['valid']} / {c12['valid']} |")
    per_cam = Counter(c for c, _, _, _ in reads_all)          # counts only: reads can be real registrations
    L += ["", f"Valid reads: {len(reads_all)}" + (" (" + ", ".join(f"{c} {n}" for c, n in sorted(per_cam.items())) + ")"
                                                    if reads_all else "."),
          "", "A valid read here is one frame's OCR output that passes the format check, before the worker's vote across "
              "a vehicle's reads; it is not checked against the true plate (the sandbox gives no ground truth)."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
