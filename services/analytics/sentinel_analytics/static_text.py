"""Fixed text is not a vehicle.

On the organisers' sandbox (25 Sep) a phone number on a hoarding, "75750 83008", passes the Indian-plate
check as TS75OB3008 and was stored seven times in 80 s: the plate detector and the classical text-line
finder both accept any plate-like text, and the repeat filter only compares consecutive tracks.

A vehicle does not pass the same spot of a camera's picture again minutes later showing the same text.
Fixed text does, and so does a vehicle parked in view. So a sighting whose text is similar to one stored
at the same place (boxes overlapping) within `window_s` is dropped, and similar text there stays muted
until it has gone unread for `mute_s`. Different vehicles stopping at one spot (a toll booth, a stop
line) carry different plates, so they are still stored. Similarity (difflib ratio 0.8) allows for OCR
reading the same hoarding a little differently from pass to pass (its two reads score 0.84), but not for
two plates of one RTO series: at 0.6, 30% of such pairs counted as the same text, and on 25 Sep a CAM06
plate was dropped 44 s after a different one; at 0.8 it is 0.2%.
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher

from sentinel_common import mask_plate

log = logging.getLogger("sentinel.static")
Box = tuple[int, int, int, int]      # x, y, w, h in pixels


def iou(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def similar(a: str, b: str, ratio: float = 0.8) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= ratio


class StaticText:
    def __init__(self, camera: str, window_s: float = 600.0, mute_s: float = 1800.0, min_iou: float = 0.5):
        self.camera, self.window_s, self.mute_s, self.min_iou = camera, window_s, mute_s, min_iou
        self._stored: list[tuple[str, Box, float]] = []    # recent sightings let through: text, box, time
        self._muted: list[list] = []                        # [text, box, muted until]
        self.dropped = 0

    def allow(self, plate: str, box, ts: float) -> bool:
        """True if this sighting should be stored. `ts` is the sighting's time in seconds."""
        if self.window_s <= 0:
            return True
        box = tuple(int(v) for v in box)
        self._stored = [s for s in self._stored if ts - s[2] <= self.window_s]
        self._muted = [m for m in self._muted if m[2] > ts]
        for m in self._muted:
            if iou(m[1], box) >= self.min_iou and similar(m[0], plate):
                m[2] = ts + self.mute_s            # still being read there: keep it muted
                self.dropped += 1
                return False
        for text, b, t in self._stored:
            if iou(b, box) >= self.min_iou and similar(text, plate):
                self._muted.append([plate, box, ts + self.mute_s])
                self.dropped += 1
                log.warning("%s: %s read again where %s was stored %.0f s ago: fixed text or a parked vehicle, "
                            "not stored; similar text there is muted until unread for %.0f min",
                            self.camera, mask_plate(plate), mask_plate(text), ts - t, self.mute_s / 60)
                return False
        self._stored.append((plate, box, ts))
        return True
