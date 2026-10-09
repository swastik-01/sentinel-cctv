"""Intrusion zones: people (or vehicles) inside a drawn polygon, while the zone is armed,
for at least `min_dwell_s`.

The detections that feed the per-camera counts are tested against each zone: a box is in
the zone when its ground point (bottom centre: where a person stands, where a vehicle's
wheels are) lies inside the polygon. Polygons are in normalised frame coordinates (0-1),
so they survive a resolution change.

Nothing about the person leaves the worker: the event is the zone, the class, how many
were inside at most, for how long, and when. No box, crop or track. The operator opens
the live view to see who it is.

Presence tolerates missed frames: at a few analysed frames per second a person standing
still is missed now and then, so occupancy only ends after the zone has looked empty for
a gap (at least 2.5 analysis intervals). One occupancy raises one event.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

log = logging.getLogger("sentinel.zones")
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    polygon: tuple[tuple[float, float], ...]
    classes: tuple[str, ...] = ("person",)
    min_dwell_s: float = 3.0
    armed_from: str | None = None     # "HH:MM" IST; None = always armed
    armed_to: str | None = None
    severity: str = "high"

    @staticmethod
    def parse(raw: dict) -> "Zone":
        armed = raw.get("armed") or {}
        return Zone(id=str(raw["id"]), name=str(raw.get("name") or raw["id"]),
                    polygon=tuple((float(x), float(y)) for x, y in raw["polygon"]),
                    classes=tuple(raw.get("classes") or ("person",)),
                    min_dwell_s=float(raw.get("min_dwell_s", 3.0)),
                    armed_from=armed.get("from"), armed_to=armed.get("to"),
                    severity=str(raw.get("severity", "high")))

    def armed(self, ts: float) -> bool:
        if not self.armed_from or not self.armed_to:
            return True
        now = datetime.fromtimestamp(ts, tz=IST).strftime("%H:%M")
        if self.armed_from <= self.armed_to:
            return self.armed_from <= now < self.armed_to
        return now >= self.armed_from or now < self.armed_to      # overnight, e.g. 22:00-06:00


def inside(poly: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    """Ray casting; points on an edge may fall either way, which is fine at this scale."""
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


@dataclass
class _State:
    since: float | None = None
    last: float = 0.0
    peak: int = 0
    raised: bool = False
    counts: dict[str, int] = field(default_factory=dict)


class ZoneWatch:
    def __init__(self, camera: str, zones: list[Zone], gap_s: float = 2.0):
        self.camera, self.zones, self.gap_s = camera, zones, gap_s
        self._state = {z.id: _State() for z in zones}

    def update(self, objs, frame_ts: float, width: int, height: int, interval: float = 0.0) -> list[dict]:
        """objs: this frame's detections (objects.Obj). Returns events to send, usually none."""
        events = []
        gap = max(self.gap_s, 2.5 * interval)
        for z in self.zones:
            st = self._state[z.id]
            if not z.armed(frame_ts):
                self._state[z.id] = _State()
                continue
            here = [o.label for o in objs if o.label in z.classes
                    and inside(z.polygon, (o.box[0] + o.box[2] / 2) / width, (o.box[1] + o.box[3]) / height)]
            if not here:
                continue
            if st.since is None or frame_ts - st.last > gap:      # a new occupancy
                st = self._state[z.id] = _State(since=frame_ts)
            st.last = frame_ts
            st.peak = max(st.peak, len(here))
            for label in set(here):
                st.counts[label] = max(st.counts.get(label, 0), here.count(label))
            dwell = frame_ts - st.since
            if not st.raised and dwell >= z.min_dwell_s:
                st.raised = True
                events.append({
                    "camera_code": self.camera, "event_type": "intrusion", "label": z.id, "value": st.peak,
                    "event_ts": datetime.fromtimestamp(frame_ts, tz=timezone.utc).isoformat(),
                    "detail": {"zone": z.id, "zone_name": z.name, "severity": z.severity,
                               "classes": dict(st.counts), "count": st.peak, "dwell_s": round(dwell, 1),
                               "first_seen": datetime.fromtimestamp(st.since, tz=timezone.utc).isoformat()}})
                log.warning("%s: INTRUSION %s (%s): %d in zone for %.1f s", self.camera, z.name, z.id, st.peak, dwell)
        return events


def zones_for(camera: dict) -> list[Zone]:
    out = []
    for raw in camera.get("zones") or []:
        try:
            out.append(Zone.parse(raw))
        except (KeyError, TypeError, ValueError) as e:
            log.warning("%s: ignoring malformed zone %r: %s", camera.get("camera_code"), raw, e)
    return out
