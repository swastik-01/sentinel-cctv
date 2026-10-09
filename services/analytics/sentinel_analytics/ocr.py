"""Plate OCR. fast-plate-ocr's global CCT v2 model (10 character slots, so 10-char Indian
plates fit) on CPU. All candidate crops from a detector batch go through one batched
call, and ONNX Runtime is capped to a couple of threads so OCR never starves the
stream decoders — on a small host, thread oversubscription costs more than inference."""
from __future__ import annotations

import logging

import cv2
import numpy as np

from .config import get_settings

log = logging.getLogger("sentinel.ocr")


class PlateOCR:
    def __init__(self) -> None:
        s = get_settings()
        self.rec = None
        self.rgb = True
        try:
            import onnxruntime as ort
            from fast_plate_ocr import LicensePlateRecognizer
            so = ort.SessionOptions()
            so.intra_op_num_threads = s.ocr_threads
            so.inter_op_num_threads = 1
            self.rec = LicensePlateRecognizer(s.ocr_model, device="cpu", sess_options=so)
            cfg = getattr(self.rec, "config", None)
            self.rgb = getattr(cfg, "image_color_mode", "rgb") == "rgb"
            log.info("OCR loaded: %s (%s, %d slots, %d threads)", s.ocr_model,
                     "rgb" if self.rgb else "grayscale", getattr(cfg, "max_plate_slots", 0), s.ocr_threads)
        except Exception as e:  # noqa: BLE001
            log.error("OCR unavailable (%s); plates cannot be read", e)

    def _prep(self, crop: np.ndarray) -> np.ndarray | None:
        if crop is None or crop.size == 0:
            return None
        h, w = crop.shape[:2]
        if h < 12 or w < 40:
            return None
        return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB if self.rgb else cv2.COLOR_BGR2GRAY)

    def read_many(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        """(text, confidence) per crop, in order. Confidence is the weakest character's
        probability: one bad character is what breaks a watchlist match."""
        out: list[tuple[str, float]] = [("", 0.0)] * len(crops)
        if self.rec is None or not crops:
            return out
        idx, imgs = [], []
        for i, c in enumerate(crops):
            img = self._prep(c)
            if img is not None:
                idx.append(i)
                imgs.append(img)
        if not imgs:
            return out
        try:
            preds = self.rec.run(imgs, return_confidence=True)
        except Exception as e:  # noqa: BLE001
            log.debug("ocr batch failed: %s", e)
            return out
        for i, pred in zip(idx, preds):
            text = str(pred.plate).replace("_", "").strip()
            probs = np.asarray(pred.char_probs, dtype=float).ravel() if pred.char_probs is not None else None
            conf = float(probs[: max(1, len(text))].min()) if probs is not None and probs.size else 0.5
            out[i] = (text, conf)
        return out

    def read(self, crop: np.ndarray) -> tuple[str, float]:
        return self.read_many([crop])[0]
