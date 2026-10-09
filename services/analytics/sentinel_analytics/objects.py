"""Vehicle and person detection: counts per camera, and the boxes plate attribution binds to.

The plate detector is a single-class model (License_Plate) — it cannot say what a plate is
mounted on. This is a second, stock COCO detector run on the frames the plate path has
already pulled, so it never competes with ANPR for frames (RtspSource hands each frame out
once). Six classes are kept: person, bicycle, car, motorcycle, bus, truck.

Counts are aggregated, not stored per detection. Each camera gets one row per window:
  value  = frames analysed in the window (the denominator)
  detail = detections per class, peak per class in a single frame, window length, model
Numerator and denominator live in the same row, so "analysed, nothing there" and "not
analysed" can never be confused. A detection is a box in one frame, not a unique vehicle
or person: there is no cross-frame identity here, and none is stored. Person rows carry a
class count only: no box, no crop, no track id.
"""
from __future__ import annotations

import logging
import shutil
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import get_settings
from .detect import half_ok

log = logging.getLogger("sentinel.objects")

CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
VEHICLES = ("bicycle", "car", "motorcycle", "bus", "truck")
COLOURED = ("car", "bus", "truck")      # a two-wheeler's "colour" would be its rider's clothes


@dataclass(frozen=True)
class Obj:
    label: str
    box: tuple[int, int, int, int]   # x, y, w, h in source pixels
    conf: float


class ObjectDetector:
    def __init__(self) -> None:
        s = get_settings()
        self.model = None
        self.half = False
        self.device = s.device
        self.name = Path(s.object_model).stem
        if not s.object_detection:
            log.info("object detection disabled (OBJECT_DETECTION=false): no counts, no vehicle attribution")
            return
        path = Path(s.object_model)
        try:
            from ultralytics import YOLO
            if path.exists():
                self.model = YOLO(str(path))
            else:
                # Stock COCO weights: ultralytics fetches them by basename from its release assets.
                log.warning("%s not found; fetching %s from the ultralytics release assets", path, path.name)
                self.model = YOLO(path.name)
                if Path(path.name).exists() and not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(path.name, path)
            import torch
            if self.device == "cuda" and not torch.cuda.is_available():
                self.device = "cpu"
            self.model.to(self.device)
            self.half = half_ok(self.device)
            t0 = time.perf_counter()
            self.detect_batch([np.zeros((720, 1280, 3), np.uint8)] * 2)
            log.info("object detector loaded: %s on %s (fp16=%s, warm-up %.1fs)", self.name, self.device,
                     self.half, time.perf_counter() - t0)
        except Exception as e:  # noqa: BLE001
            log.warning("object detector unavailable (%s): no counts or vehicle attribution will be written", e)
            self.model = None

    @property
    def ready(self) -> bool:
        return self.model is not None

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[Obj]]:
        s = get_settings()
        out: list[list[Obj]] = [[] for _ in frames]
        if self.model is None or not frames:
            return out
        try:
            extra = {"half": True} if self.half else {}
            results = self.model.predict(frames, conf=s.min_object_conf, classes=list(CLASSES),
                                         imgsz=s.object_imgsz, verbose=False, device=self.device, **extra)
            for i, r in enumerate(results):
                for b in r.boxes:
                    x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
                    out[i].append(Obj(CLASSES[int(b.cls[0])], (x1, y1, x2 - x1, y2 - y1), float(b.conf[0])))
        except Exception as e:  # noqa: BLE001
            log.warning("object batch failed: %s", e)
        return out


class CountWindow:
    """Frames analysed, detections per class and the per-frame peak, for one camera over one
    wall-clock window. Event time is the frame clock (stream PTS), never arrival time."""

    def __init__(self, camera: str, window_s: float, started: float):
        self.camera, self.window_s, self.started = camera, window_s, started
        self.frames = 0
        self.detections: Counter[str] = Counter()
        self.peak: Counter[str] = Counter()
        self.peak_vehicles = 0           # all vehicle classes together, in one frame
        self.first_ts: float | None = None
        self.last_ts: float | None = None

    def add(self, objs: list[Obj], frame_ts: float) -> None:
        self.frames += 1
        here = Counter(o.label for o in objs)
        self.detections.update(here)
        for k, v in here.items():
            self.peak[k] = max(self.peak[k], v)
        self.peak_vehicles = max(self.peak_vehicles, sum(here[v] for v in VEHICLES))
        self.first_ts = frame_ts if self.first_ts is None else self.first_ts
        self.last_ts = frame_ts

    def due(self, now: float) -> bool:
        return now - self.started >= self.window_s

    def to_event(self, now: float, model: str) -> dict:
        ts = self.last_ts if self.last_ts is not None else now
        detail: dict = {"window_s": round(now - self.started, 1), "frames": self.frames,
                        "detections": dict(self.detections), "peak": dict(self.peak),
                        "peak_vehicles": self.peak_vehicles, "model": model}
        if self.first_ts is not None:
            detail["first_frame_ts"] = datetime.fromtimestamp(self.first_ts, tz=timezone.utc).isoformat()
        if not self.frames:
            detail["reason"] = "no frames analysed (stream down or stalled)"
        return {"camera_code": self.camera, "event_type": "object_counts", "value": self.frames,
                "event_ts": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "detail": detail}
