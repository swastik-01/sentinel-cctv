"""Plate localisation.

Two candidate sources, unioned:
  1. A YOLO plate detector (GPU). Loaded from `models/` or pulled once from Hugging Face.
  2. A classical finder: bright, high-contrast rectangles with plate-like aspect ratio and
     dense internal edges. Cheap on CPU, works on footage the detector has never seen
     (including synthetic feeds), and is the safety net when a model is unavailable.

Every candidate still has to survive OCR + Indian-plate validation, so a loose
candidate set costs a little OCR time and nothing in precision.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np

from .config import get_settings

log = logging.getLogger("sentinel.detect")

Box = tuple[int, int, int, int, float]  # x, y, w, h, conf


def half_ok(device: str) -> bool:
    """FP16 unless the card is a GTX 16xx: Turing cards without tensor cores return NaN
    boxes in half precision (a long-standing cuDNN issue), which silently kills detection.
    Shared by every detector the worker loads, so a second model cannot NaN on its own."""
    s = get_settings()
    if device != "cuda" or s.fp16 is False:
        return False
    import torch
    name = torch.cuda.get_device_name(0)
    return s.fp16 is True or "GTX 16" not in name


class PlateDetector:
    def __init__(self) -> None:
        s = get_settings()
        self.model = None
        self.half = False
        self.device = s.device
        path = Path(s.plate_model)
        if s.detector == "classical":
            log.info("detector mode: classical text-line finder only")
            return
        try:
            if not path.exists() and s.plate_model_hf:
                path = self._download(s.plate_model_hf, s.plate_model_hf_file, path)
            if path.exists():
                from ultralytics import YOLO
                self.model = YOLO(str(path))
                import torch
                if self.device == "cuda" and not torch.cuda.is_available():
                    log.warning("CUDA requested but unavailable; using CPU")
                    self.device = "cpu"
                self.model.to(self.device)
                self.half = half_ok(self.device)
                t0 = time.perf_counter()
                self.model.predict([np.zeros((720, 1280, 3), np.uint8)] * 2, imgsz=640, verbose=False,
                                   device=self.device, **({"half": True} if self.half else {}))
                log.info("plate detector loaded: %s on %s (fp16=%s, warm-up %.1fs)", path, self.device,
                         self.half, time.perf_counter() - t0)
        except Exception as e:  # noqa: BLE001
            log.warning("plate detector unavailable (%s); classical candidates only", e)
            self.model = None

    @staticmethod
    def _download(repo: str, filename: str, dest: Path) -> Path:
        import shutil
        from huggingface_hub import hf_hub_download
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hf_hub_download(repo_id=repo, filename=filename), dest)  # copy: keep HF cache intact
        return dest

    # ------------------------------------------------------------------ inference
    def detect_batch(self, frames: list[np.ndarray]) -> list[list[Box]]:
        """Plate boxes per frame. Batched so N cameras cost one GPU round-trip."""
        s = get_settings()
        out: list[list[Box]] = [[] for _ in frames]
        if self.model is not None and frames:
            try:
                extra = {"half": True} if self.half else {}   # passing half=False trips a deprecation warning
                results = self.model.predict(frames, conf=s.min_plate_conf, imgsz=640, verbose=False,
                                             device=self.device, **extra)
                for i, r in enumerate(results):
                    for b in r.boxes:
                        x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
                        out[i].append((x1, y1, x2 - x1, y2 - y1, float(b.conf[0])))
            except Exception as e:  # noqa: BLE001
                log.warning("detector batch failed: %s", e)
        if s.detector in ("classical", "both"):
            for i, f in enumerate(frames):
                for c in classical_candidates(f):
                    if not any(_iou(c, d) > 0.4 for d in out[i]):
                        out[i].append(c)
        return out


def classical_candidates(img: np.ndarray, max_candidates: int = 6) -> list[Box]:
    """Text-line finder: dark strokes on a bright background, joined horizontally.

    Black-hat morphology lifts dark text off a light plate; closing merges characters
    into one line; each line must have plate-like aspect and sit on a bright field.
    Unlike a brightness threshold this is indifferent to the vehicle's colour, which
    is what breaks naive approaches on light cars and white walls.
    Runs on a 960px-wide copy: cheap, and the kernels are then in known units.
    """
    h, w = img.shape[:2]
    scale = 960.0 / w if w > 960 else 1.0
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1.0 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sh, sw = gray.shape
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 9)))
    _, strokes = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    line = cv2.morphologyEx(strokes, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (29, 5)))
    line = cv2.morphologyEx(line, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(line, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cands: list[Box] = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < 36 or bh < 9 or bw > sw * 0.4 or bh > sh * 0.15:
            continue
        if not 2.2 <= bw / bh <= 9.0:
            continue
        # the text line should sit on a bright field (the plate), padded a little
        px, py = int(bw * 0.08) + 3, int(bh * 0.3) + 3
        x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(sw, x + bw + px), min(sh, y + bh + py)
        field = gray[y0:y1, x0:x1]
        if field.size == 0 or float(np.percentile(field, 75)) < 150:
            continue
        dark = float((field < 110).mean())
        if not 0.04 <= dark <= 0.5:
            continue
        conf = min(0.9, 0.45 + dark)
        inv = 1.0 / scale
        cands.append((int(x0 * inv), int(y0 * inv), int((x1 - x0) * inv), int((y1 - y0) * inv), conf))
    cands.sort(key=lambda b: -b[4])
    return cands[:max_candidates]


def _iou(a: Box, b: Box) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0, min(ax2, bx2) - max(a[0], b[0])), max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0
