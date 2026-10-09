"""Batches sightings and object-count rows to the API's ingest endpoints; sends heartbeats.

When the API cannot be reached, batches go to the local spool (spool.py) and are replayed
once it answers, and sightings are checked against a cached copy of the active vehicle
watchlist so a hit is still recorded at the edge during the outage (see LocalWatchlist).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import httpx
from sentinel_common import mask_plate, normalise_plate

from .config import get_settings
from .spool import Spool

log = logging.getLogger("sentinel.sink")

RETRYABLE = {401, 403, 408, 429}    # auth/throttling can recover (key rotated, limit lifted); 5xx too
REPLAY_PER_FLUSH = 20               # spool files per flush, so a long backlog never stalls analysis


def edits_within(a: str, b: str, k: int) -> bool:
    """Same rule as the API's matcher: equal length and Levenshtein distance at most k."""
    if len(a) != len(b):
        return False
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] <= k


class LocalWatchlist:
    """Active vehicle watchlist entries, cached at the edge: plate, kind and severity only
    (no names, no reasons). Refreshed from the API while it is up and kept on disk, so a
    worker restarted during an outage still has it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.max_edits = 1
        self.cooldown_s = 120.0
        self.entries: list[dict] = []
        self.fetched_at = 0.0
        self._last: dict[tuple[str, str], float] = {}   # (watch plate, camera) -> last local alert
        if path.exists():
            try:
                self._load(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def _load(self, snap: dict) -> None:
        self.max_edits = int(snap.get("max_edits", 1))
        self.cooldown_s = float(snap.get("cooldown_s", 120))
        self.entries = [e for e in snap.get("entries", []) if e.get("plate_norm")]

    def update(self, snap: dict) -> None:
        self._load(snap)
        self.fetched_at = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap), encoding="utf-8")
        tmp.replace(self.path)

    def match(self, plate_norm: str) -> dict | None:
        exact = next((e for e in self.entries if e["plate_norm"] == plate_norm), None)
        if exact or self.max_edits <= 0:
            return exact
        return next((e for e in self.entries if edits_within(e["plate_norm"], plate_norm, self.max_edits)), None)

    def due(self, watch_plate: str, camera: str, now: float) -> bool:
        """The API's cooldown, applied at the edge: one alert per entry per camera per window."""
        last = self._last.get((watch_plate, camera))
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last[(watch_plate, camera)] = now
        return True


class ApiSink:
    def __init__(self, worker_id: str | None = None) -> None:
        s = get_settings()
        self.client = httpx.Client(base_url=s.api_url, timeout=s.ingest_timeout_s,
                                   headers={"X-Ingest-Key": s.ingest_key})
        self.crop_dir = Path(s.crop_dir)
        # One spool per worker process: two workers on one machine (the plate worker and the counts worker) replaying
        # the same folder would each take the other's files mid-read, and the loser died on the missing file.
        mine = Path(s.spool_dir) / (worker_id or s.worker_id)
        self.spool = Spool(mine, s.spool_max_mb)
        self.watchlist = LocalWatchlist(mine / "edge-watchlist.json")
        self.local_alerts_path = mine / "local-alerts.jsonl"
        self._queue: list[dict] = []
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self.sent = 0
        self.alerts = 0
        self.failed = 0
        self.events_sent = 0
        self.spooled = 0
        self.replayed = 0
        self.local_alerts = 0
        self._down_until = 0.0          # API considered unreachable until then: spool without trying
        self._backoff = 2.0

    def cameras(self) -> list[dict]:
        r = self.client.get("/ingest/cameras")
        r.raise_for_status()
        return r.json()

    def save_crop(self, camera: str, plate_norm: str, ts: float, crop) -> str | None:
        if crop is None or not get_settings().save_crops:
            return None
        d = self.crop_dir / camera
        d.mkdir(parents=True, exist_ok=True)
        name = f"{int(ts)}_{plate_norm}.jpg"
        try:
            cv2.imwrite(str(d / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except cv2.error:
            return None
        return f"/crops/{camera}/{name}"

    def add(self, camera: str, read, crop_path: str | None) -> None:
        with self._lock:
            self._queue.append({
                "camera_code": camera,
                "event_ts": datetime.fromtimestamp(read.ts, tz=timezone.utc).isoformat(),
                # the track's vote (tracker.py), not its best single read: that is the plate we stand behind
                "plate_text": read.plate_norm, "ocr_conf": round(read.ocr_conf, 3),
                "det_conf": round(read.det_conf, 3), "vehicle_type": read.vehicle_type,
                "vehicle_color": read.vehicle_color,
                "bbox": list(read.bbox), "track_id": read.track_id, "crop_path": crop_path,
                "reads": read.count, "agreement": round(read.agreement, 3),
                "first_read_at": datetime.fromtimestamp(read.seen_at, tz=timezone.utc).isoformat() if read.seen_at else None,
            })

    def add_event(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    # ------------------------------------------------------------------ sending

    def _post(self, kind: str, batch: list[dict], batch_id: str | None, replayed: bool = False) -> str:
        """'ok', 'retry' (keep it) or 'rejected' (malformed; retrying cannot help)."""
        if time.time() < self._down_until:
            return "retry"
        try:
            params = {"batch_id": batch_id} if batch_id else {}
            if replayed:
                params["replayed"] = "true"
            r = self.client.post(f"/ingest/{kind}", json=batch, params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code < 500 and code not in RETRYABLE:
                log.warning("%s batch rejected by the API (%d): %s", kind, code, e.response.text[:200])
                return "rejected"
            self._mark_down(f"HTTP {code}")
            return "retry"
        except httpx.HTTPError as e:
            self._mark_down(type(e).__name__)
            return "retry"
        self._backoff = 2.0
        j = r.json()
        if j.get("duplicate_batch"):
            log.info("%s batch %s was already stored (its reply was lost); not stored twice", kind, batch_id)
            return "ok"
        if kind == "events":
            self.events_sent += j.get("stored", 0)
            return "ok"
        self.sent += j.get("stored", 0)
        self.alerts += j.get("alerts", 0)
        if j.get("alerts"):
            log.info("ALERT x%d raised from batch of %d", j["alerts"], len(batch))
        if j.get("unknown_cameras"):
            log.warning("unknown cameras in batch: %s", j["unknown_cameras"])
        return "ok"

    def _mark_down(self, why: str) -> None:
        if time.time() >= self._down_until:
            log.warning("API unreachable (%s): spooling locally, next attempt in %.0f s", why, self._backoff)
        self._down_until = time.time() + self._backoff
        self._backoff = min(self._backoff * 2, 30.0)

    def _send_or_spool(self, kind: str, batch: list[dict]) -> None:
        batch_id = uuid.uuid4().hex
        result = self._post(kind, batch, batch_id)
        if result == "retry":
            self.spool.put(kind, batch, batch_id)
            if kind == "sightings":
                self.spooled += len(batch)
                self._match_locally(batch)
        elif result == "rejected":
            self.failed += len(batch)

    def _match_locally(self, batch: list[dict]) -> None:
        hits = []
        for s in batch:
            norm = normalise_plate(s["plate_text"])
            e = self.watchlist.match(norm) if norm else None
            if e and self.watchlist.due(e["plate_norm"], s["camera_code"], time.time()):
                hits.append({"camera_code": s["camera_code"], "event_ts": s["event_ts"], "plate_norm": norm,
                             "watch_plate": e["plate_norm"], "kind": e.get("kind"),
                             "severity": e.get("severity"), "exact": e["plate_norm"] == norm,
                             "raised_at": datetime.now(timezone.utc).isoformat()})
        if not hits:
            return
        self.local_alerts += len(hits)
        self.local_alerts_path.parent.mkdir(parents=True, exist_ok=True)
        with self.local_alerts_path.open("a", encoding="utf-8") as f:
            for h in hits:
                f.write(json.dumps(h) + "\n")
                log.warning("LOCAL ALERT (backhaul down): %s %s on %s at %s; control room alert follows on replay",
                            h["severity"], mask_plate(h["plate_norm"]), h["camera_code"], h["event_ts"])

    def _replay(self) -> None:
        for path in self.spool.pending()[:REPLAY_PER_FLUSH]:
            try:
                kind, batch_id, batch = self.spool.read(path)
            except (OSError, ValueError, KeyError):
                self.spool.reject(path)
                continue
            result = self._post(kind, batch, batch_id, replayed=True)
            if result == "retry":
                return
            if result == "rejected":
                self.spool.reject(path)
                continue
            self.spool.done(path)
            if kind == "sightings":
                self.replayed += len(batch)
        left = len(self.spool.pending())
        if left == 0 and self.replayed:
            log.info("spool drained: %d spooled sightings replayed", self.replayed)

    def flush(self) -> None:
        with self._lock:
            batch, self._queue = self._queue, []
            events, self._events = self._events, []
        if events:
            self._send_or_spool("events", events)
        if batch:                       # live data first; the backlog follows
            self._send_or_spool("sightings", batch)
        if self.spool.pending():
            self._replay()

    def refresh_watchlist(self) -> None:
        if time.time() < self._down_until:
            return
        try:
            r = self.client.get("/ingest/watchlist")
            r.raise_for_status()
            self.watchlist.update(r.json())
        except httpx.HTTPError as e:
            log.debug("watchlist refresh failed: %s", e)

    def heartbeat(self, worker_id: str, cameras: list[str], fps: dict[str, float]) -> None:
        if time.time() < self._down_until:
            return
        try:
            self.client.post("/ingest/heartbeat", params={"worker_id": worker_id},
                             json={"cameras": cameras, "fps": fps})
        except httpx.HTTPError as e:
            log.debug("heartbeat failed: %s", e)
