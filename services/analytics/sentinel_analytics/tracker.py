"""Per-camera plate tracks with a short confirmation window and character voting.

A vehicle crossing a camera yields many reads at 5 fps. Emitting the first read is
fast but needlessly error-prone; waiting for the whole pass adds seconds of alert
latency. Middle ground: hold a new track for `confirm_s` (or until `confirm_reads`
reads), then emit once.

The hold runs on the wall clock (when the read arrived), never on frame time: when
decoding falls behind, frame times lag the wall clock, and a frame-time window would
close before a second read could arrive. It also stretches with the camera's achieved
analysis rate (at least 2.5 analysis intervals), so a camera analysed at 0.3 fps, as
happens when one machine takes many feeds, still gets its chance at a second read.
Below `slow_fps`, one confident read is accepted on its own: a vehicle in view for four
seconds may only ever be analysed once.

What gets emitted is a per-character, confidence-weighted vote across every read of
the track that has the modal length. Random OCR errors (a 0 read as 8 in one frame)
are outvoted; a read that dropped a character joins the track (edit distance <= 2)
but does not get a vote. The evidence crop is the single best-confidence read.

The same plate on the same camera is then suppressed for `window_s`, extended while
it stays in view.

Vehicle type and colour ride along the same way: every read that could be bound to a
vehicle box contributes a (value, confidence) vote, the first read included, and the
track's answer is decided once at emission by pick(). A thin or split vote is NULL.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sentinel_common import looks_like_indian_plate, normalise_plate

from .objects import COLOURED


@dataclass
class Read:
    plate_norm: str
    plate_text: str
    ocr_conf: float
    det_conf: float
    bbox: tuple[int, int, int, int]
    ts: float               # unix seconds (frame time) of the best read
    first_ts: float
    track_id: str
    seen_at: float = 0.0    # wall clock when the track's first read arrived
    crop: object = None
    count: int = 1
    votes: list[tuple[str, float]] = field(default_factory=list)   # (plate_norm, ocr_conf) per read
    types: list[tuple[str, float]] = field(default_factory=list)   # (vehicle class, det conf) per bound read
    colours: list[tuple[str, float]] = field(default_factory=list) # (colour, heuristic conf) per read
    vehicle_type: str | None = None
    vehicle_color: str | None = None
    agreement: float = 1.0  # the vote's weakest position's winning share (vote()); 1.0 for a single read


def pick(votes: list[tuple[str, float]], min_weight: float, min_share: float = 0.6) -> str | None:
    """Confidence-weighted winner, or None when the evidence is thin (total weight of the
    winner below `min_weight`) or split (winner below `min_share` of all weight)."""
    if not votes:
        return None
    weights: dict[str, float] = defaultdict(float)
    for v, c in votes:
        weights[v] += c
    winner, w = max(weights.items(), key=lambda kv: kv[1])
    return winner if w >= min_weight and w / sum(weights.values()) >= min_share else None


def levenshtein(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def vote(reads: list[tuple[str, float]]) -> tuple[str, float]:
    """Confidence-weighted per-position vote over reads of the modal length.
    Returns (plate, agreement) where agreement is the weakest position's winning share."""
    if not reads:
        return "", 0.0
    modal_len = Counter(len(p) for p, _ in reads).most_common(1)[0][0]
    same = [(p, c) for p, c in reads if len(p) == modal_len]
    out, agreement = [], 1.0
    for i in range(modal_len):
        weights: dict[str, float] = defaultdict(float)
        for p, c in same:
            weights[p[i]] += max(c, 0.05)
        ch, w = max(weights.items(), key=lambda kv: kv[1])
        out.append(ch)
        agreement = min(agreement, w / sum(weights.values()))
    return "".join(out), agreement


class PlateDeduper:
    def __init__(self, camera: str, window_s: float, confirm_s: float = 1.0, confirm_reads: int = 3,
                 min_reads: int = 2, slow_fps: float = 2.0, single_read_conf: float = 0.6):
        self.camera = camera
        self.min_reads = min_reads   # a track seen once is usually a mis-detection, not a vehicle
        self.window = window_s
        self.confirm_s = confirm_s
        self.confirm_reads = confirm_reads
        self.slow_fps = slow_fps
        self.single_read_conf = single_read_conf
        self.interval = 0.0          # achieved seconds between analysed frames (EMA), set by the worker
        self.single_reads = 0        # sightings emitted on one read because the camera is slow
        self.track_log = None        # optional callable(dict): every harvested track, for offline evaluation
        self._pending: dict[str, Read] = {}   # track key -> track being confirmed
        self._emitted: dict[str, float] = {}  # plate_norm -> last time seen after emission

    def observe_interval(self, gap: float) -> None:
        gap = min(gap, 30.0)         # a reconnect is not the analysis rate
        self.interval = gap if self.interval == 0.0 else 0.8 * self.interval + 0.2 * gap

    @property
    def hold_s(self) -> float:
        return max(self.confirm_s, 2.5 * self.interval)

    @property
    def slow(self) -> bool:
        return self.interval > 0 and 1.0 / self.interval < self.slow_fps

    def _key_for(self, norm: str) -> str:
        if norm in self._pending:
            return norm
        best, dist = norm, 3
        for k in self._pending:
            d = levenshtein(k, norm, cap=2)
            if d <= 2 and d < dist:
                best, dist = k, d
        return best

    def offer(self, text: str, ocr_conf: float, det_conf: float, bbox, ts: float, crop,
              vtype: tuple[str, float] | None = None, vcolour: tuple[str, float] | None = None,
              arrival: float | None = None) -> None:
        norm = normalise_plate(text)
        if not norm:
            return
        key = self._key_for(norm)
        cur = self._pending.get(key)
        if cur is None:
            cur = self._pending[norm] = Read(norm, text, ocr_conf, det_conf, tuple(bbox), ts, ts,
                                             track_id=f"{self.camera}-{norm}-{int(ts)}",
                                             seen_at=time.time() if arrival is None else arrival,
                                             crop=crop, votes=[(norm, ocr_conf)])
            cur.types += [vtype] if vtype else []
            cur.colours += [vcolour] if vcolour else []
            return
        cur.count += 1
        cur.votes.append((norm, ocr_conf))
        cur.types += [vtype] if vtype else []
        cur.colours += [vcolour] if vcolour else []
        if ocr_conf > cur.ocr_conf:
            cur.plate_text, cur.ocr_conf, cur.det_conf, cur.bbox, cur.crop, cur.ts = \
                text, ocr_conf, det_conf, tuple(bbox), crop, ts

    def harvest(self, now: float) -> list[Read]:
        """Tracks whose confirmation window has closed. Emits each plate once per window."""
        out: list[Read] = []
        hold = self.hold_s
        for key, r in list(self._pending.items()):
            if now - r.seen_at < hold and r.count < self.confirm_reads:
                continue
            self._pending.pop(key)
            if r.count < self.min_reads:
                if not (self.slow and r.count == 1 and r.ocr_conf >= self.single_read_conf):
                    continue
                self.single_reads += 1
            voted, agreement = vote(r.votes)
            voted = normalise_plate(voted)
            r.agreement = agreement
            if self.track_log is not None:
                self.track_log({"camera": self.camera, "ts": r.ts, "reads": r.votes, "voted": voted,
                                "agreement": round(agreement, 3), "best": normalise_plate(r.plate_text),
                                "best_conf": r.ocr_conf})
            if looks_like_indian_plate(voted):
                r.plate_norm = voted
                # a unanimous vote over several reads is stronger evidence than any single read
                if r.count >= 3 and agreement >= 0.99:
                    r.ocr_conf = max(r.ocr_conf, min(0.99, 0.6 + 0.1 * r.count))
            else:                                  # no valid consensus: fall back to the best single read
                r.plate_norm = normalise_plate(r.plate_text)
            r.vehicle_type = pick(r.types, min_weight=0.5)
            # a colour only describes a vehicle we are sure of, and never a two-wheeler's rider
            r.vehicle_color = pick(r.colours, min_weight=0.45) if r.vehicle_type in COLOURED else None
            # A one-character variant of a plate this camera emitted within the window is the same
            # vehicle misread, not a new one: without this, a consistent misread slips past the
            # repeat filter on every pass while the correct plate is (rightly) suppressed, and
            # misreads end up over-represented among stored sightings.
            key = r.plate_norm
            if key not in self._emitted:
                key = next((p for p, t in self._emitted.items() if len(p) == len(key)
                            and r.first_ts - t <= self.window and levenshtein(p, key, cap=1) <= 1), key)
            last = self._emitted.get(key)
            if last is None or r.first_ts - last > self.window:
                out.append(r)
            self._emitted[key] = max(last or 0.0, r.ts)
        return out

    def gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self._pending.items() if now - v.seen_at > max(30.0, 3 * self.hold_s)]:
            self._pending.pop(k, None)
        for k in [k for k, t in self._emitted.items() if now - t > 3600]:
            self._emitted.pop(k, None)
