"""Counts-only worker (the tier B profile): vehicle and person counts, and intrusion zones, on many cameras at
once, from keyframes only.

The plate worker decodes every frame of every stream it reads, and decode is what limits a machine to a handful of
streams. Counting needs about one frame a second, and a keyframe can be decoded without the frames before it, so this
worker asks FFmpeg (PyAV) to skip every other frame: on 7 Oct, 14 simulator streams (H.264 and H.265, 576p to
1080p) cost 0.52 CPU cores keyframes-only against 2.53 cores decoding every frame. It runs as its own process beside
the plate worker, never inside it, so the plate path is unchanged; give it the cameras the plate workers do not
take (COUNTS_EXCLUDE), or two workers would raise each zone's alert twice.

Count rows are the same `object_counts` rows the plate worker writes (objects.CountWindow), marked
`"profile": "keyframes"`; the reports use per-frame averages and peaks, which do not depend on the sampling rate.
Timing follows the sandbox rules: RTSP over TCP, event time from the stream's PTS, reconnects back off 2 s -> 30 s
and start again from 2 s only after a minute of healthy streaming.

    COUNTS_EXCLUDE=CAM06,CAM07 uv run --no-sync sentinel-counts
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from collections import deque
from datetime import datetime, timezone

import av

from .config import get_settings
from .objects import CountWindow, ObjectDetector
from .sink import ApiSink
from .stream import MAX_BACKOFF, MIN_BACKOFF, STABLE_S, Frame
from .worker import fetch_cameras, loopback_ipv4, via_relay_host
from .zones import ZoneWatch, zones_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinel.counts")
# FFmpeg complains about every frame it cannot decode after joining a stream between keyframes (thousands of lines a
# minute on long-GOP cameras); those are expected, so its messages are not forwarded.
av.logging.set_level(None)

READ_TIMEOUT_S = 15.0    # no packet for this long: the session is dead, reconnect (keyframes can be ~10 s apart)
STUCK_PTS = 3            # keyframes in a row with the same PTS: the source's clock does not advance
GATHER_S = 0.5           # longest a keyframe waits for others to fill a detector batch
LONG_GOP_S = 4.0         # keyframes further apart than this (median): decode every frame of that camera instead
LONG_GOP_SAMPLES = 2     # keyframe gaps seen before deciding
TAKE_TOLERANCE = 0.8     # a frame is counted if at least this share of the interval has passed


def long_gop(arrivals) -> float:
    """The median gap between the last keyframe arrivals when it exceeds LONG_GOP_S, else 0."""
    seq = list(arrivals)
    gaps = sorted(b - a for a, b in zip(seq, seq[1:]))
    if len(gaps) < LONG_GOP_SAMPLES:
        return 0.0
    median = gaps[len(gaps) // 2]
    return median if median > LONG_GOP_S else 0.0
# The detector sees 640 px. Converting a 1080p keyframe at full size, then shrinking it, was most of the CPU at 40-50
# streams (bench/results/counts_capacity.md); FFmpeg scales while converting instead. Zones are in normalised
# coordinates, so they do not care.
MAX_WIDTH = 960


def scaled(w: int, h: int) -> dict:
    """reformat arguments that bring a frame down to MAX_WIDTH wide, keeping its shape; none if already that small."""
    if w <= MAX_WIDTH:
        return {}
    return {"width": MAX_WIDTH, "height": max(2, round(h * MAX_WIDTH / w / 2) * 2)}


class StreamClock:
    """Wall-clock time of a frame from the stream's own PTS: anchored at the first frame, re-anchored when the
    position jumps back (a loop point) or forward by more than `max_gap_s`. A source whose PTS never advances falls
    back to the arrival clock, as stream.RtspSource does."""

    def __init__(self, max_gap_s: float = 60.0):
        self.max_gap_s = max_gap_s
        self.epoch: float | None = None
        self.last: float | None = None
        self.discontinuities = 0
        self.pts_usable = True
        self._same = 0

    def ts(self, pts_s: float | None, now: float) -> float:
        if pts_s is None or not self.pts_usable:
            return now
        if self.last is not None and abs(pts_s - self.last) < 1e-3:
            self._same += 1                          # repeats of the previous PTS: STUCK_PTS frames = one fewer
            if self._same >= STUCK_PTS - 1:
                self.pts_usable = False
                return now
        else:
            self._same = 0
        if self.epoch is None or pts_s < self.last - 0.5 or pts_s - self.last > self.max_gap_s:
            if self.epoch is not None:
                self.discontinuities += 1
            self.epoch = now - pts_s
        self.last = pts_s
        return self.epoch + pts_s


def keyframes(container, stop: threading.Event, every_frame: bool = False):
    """Decoded keyframes of a container's first video stream; every other frame is skipped by the decoder
    (`every_frame` decodes them all, for a camera whose keyframes are too far apart)."""
    stream = container.streams.video[0]
    stream.codec_context.skip_frame = "DEFAULT" if every_frame else "NONKEY"
    for frame in container.decode(stream):
        if stop.is_set():
            return
        yield frame


class KeyframeSource:
    """One camera: a decode thread with latest-frame semantics, like stream.RtspSource, but keyframes only.
    At most one image per `min_interval` is converted to BGR; keyframes in between are dropped before conversion.

    Keyframe intervals differ by camera: on 7 Oct the sandbox's ran from 1 s to 20 s. A camera whose keyframes come
    more than LONG_GOP_S apart would be counted every 15-20 s and its zones would miss short presences, so it switches to
    decoding every frame on the open session (still converted and counted at most once per `min_interval`)."""

    def __init__(self, code: str, url: str, min_interval: float):
        self.code, self.url, self.min_interval = code, url, min_interval
        self.every_frame = False
        self.clock = StreamClock()
        self.connected = False
        self.frames = 0
        self.reconnects = 0
        self.errors = 0
        self.last_frame_at = 0.0
        self._latest: Frame | None = None
        self._consumed = -1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"kf-{code}", daemon=True)

    def start(self) -> "KeyframeSource":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> Frame | None:
        with self._lock:
            f = self._latest
            if f is None or f.seq == self._consumed:
                return None
            self._consumed = f.seq
            return f

    def _run(self) -> None:
        backoff, seq = MIN_BACKOFF, 0
        while not self._stop.is_set():
            connected_at = time.monotonic()
            try:
                container = av.open(self.url, options={"rtsp_transport": "tcp"}, timeout=(10.0, READ_TIMEOUT_S))
            except Exception as e:  # noqa: BLE001 - any open failure is retried with backoff
                self._note(f"connect failed ({type(e).__name__}), retry in {backoff:.0f}s")
            else:
                self.connected = True
                self.reconnects += 1
                last_take = 0.0
                arrivals: deque[float] = deque(maxlen=LONG_GOP_SAMPLES + 1)   # bounded: a session can last days
                try:
                    for frame in keyframes(container, self._stop, self.every_frame):
                        now = time.time()
                        self.last_frame_at = now
                        if not self.every_frame:
                            arrivals.append(now)
                            if len(arrivals) > LONG_GOP_SAMPLES and (gop := long_gop(arrivals)):
                                # Switched on the open session: reconnecting would cost up to one more
                                # keyframe interval before anything decodes.
                                container.streams.video[0].codec_context.skip_frame = "DEFAULT"
                                self.every_frame = True
                                log.info("%s: keyframes every %.0f s; decoding every frame instead (counted at most "
                                         "%.1f/s)", self.code, gop, 1 / max(self.min_interval, 1e-6))
                        # Keyframes come a little faster or slower than their nominal interval: a strict 1 s cap
                        # took every other one of a camera keyframing every 0.95 s.
                        if now - last_take < TAKE_TOLERANCE * self.min_interval:
                            continue
                        last_take = now
                        ts = self.clock.ts(frame.time, now)
                        seq += 1
                        img = frame.to_ndarray(format="bgr24", **scaled(frame.width, frame.height))
                        with self._lock:
                            self._latest = Frame(img,
                                                 datetime.fromtimestamp(ts, tz=timezone.utc), seq, (frame.time or 0) * 1000)
                        self.frames += 1
                    if not self._stop.is_set():
                        self._note("stream ended, reconnecting")
                except Exception as e:  # noqa: BLE001 - decoder and network errors are never fatal
                    self._note(f"{type(e).__name__}: {e}"[:160] + ", reconnecting")
                finally:
                    container.close()
                    self.connected = False
            if self._stop.is_set():
                return
            if time.monotonic() - connected_at >= STABLE_S:
                backoff = MIN_BACKOFF
            self._stop.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    def _note(self, msg: str) -> None:
        self.errors += 1
        log.warning("%s: %s", self.code, msg)


def pick(all_cams: list[dict], explicit: list[str], exclude: set[str], max_streams: int) -> tuple[list[dict], list[str]]:
    """The cameras this worker counts: CAMERAS when given, else every analytics camera; minus COUNTS_EXCLUDE (the
    plate workers' cameras); at most `max_streams`. Returns them and the codes left over."""
    cams = sorted(all_cams, key=lambda c: c["camera_code"])
    if explicit:
        cams = [c for c in cams if c["camera_code"] in explicit]
    cams = [c for c in cams if c["camera_code"] not in exclude]
    return cams[:max_streams], [c["camera_code"] for c in cams[max_streams:]]


def run() -> int:
    s = get_settings()
    sink = ApiSink(s.counts_worker_id)
    try:
        all_cams = fetch_cameras(sink, s.startup_wait_s)
    except Exception as e:  # noqa: BLE001
        log.error("cannot fetch camera list from %s after %.0f s: %s", s.api_url, s.startup_wait_s, e)
        return 1
    cams, left = pick(all_cams, s.camera_list, set(s.counts_exclude_list), s.counts_max_streams)
    if left:
        log.warning("COUNTS_MAX_STREAMS=%d: %d camera(s) will NOT be counted: %s", s.counts_max_streams, len(left),
                    ", ".join(left))
    if not cams:
        log.error("no cameras to count (CAMERAS=%s, COUNTS_EXCLUDE=%s)", s.cameras, s.counts_exclude)
        return 1
    objects = ObjectDetector()
    if not objects.ready:
        log.error("the object detector is unavailable (OBJECT_DETECTION or %s): nothing to count with", s.object_model)
        return 1
    log.info("%s: counting %d cameras from keyframes, up to %.1f frame/s each: %s", s.counts_worker_id, len(cams),
             s.counts_fps, ", ".join(c["camera_code"] for c in cams))

    interval = 1.0 / s.counts_fps
    sources = {c["camera_code"]: KeyframeSource(c["camera_code"],
                                                loopback_ipv4(via_relay_host(c["rtsp_url"], s.relay_host)),
                                                interval).start() for c in cams}
    start = time.time()
    windows = {code: CountWindow(code, s.count_window_s, start) for code in sources}
    zone_watch = {c["camera_code"]: ZoneWatch(c["camera_code"], zs) for c in cams if (zs := zones_for(c))}
    if zone_watch:
        log.info("intrusion zones: %s", ", ".join(f"{c} ({len(z.zones)})" for c, z in zone_watch.items()))
    last_ts: dict[str, float] = {}
    analysed = {code: 0 for code in sources}
    obj_frames = obj_ms = 0.0
    t_flush = t_beat = t_log = start
    running = True

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    pending: dict[str, Frame] = {}      # newest keyframe per camera, waiting to be batched
    waiting_since = 0.0
    while running:
        now = time.time()
        for code, src in sources.items():
            if (f := src.latest()) is not None:
                if not pending:
                    waiting_since = now
                pending[code] = f
        # Keyframes trickle in one or two at a time; the detector costs about the same for a batch as for one
        # frame, so gather up to a batch or GATHER_S, whichever comes first.
        ready: list = []
        if pending and (len(pending) >= s.counts_batch or now - waiting_since >= GATHER_S):
            ready, pending = list(pending.items()), {}
        for i in range(0, len(ready), s.counts_batch):
            chunk = ready[i: i + s.counts_batch]
            t0 = time.perf_counter()
            for (code, f), objs in zip(chunk, objects.detect_batch([f.image for _, f in chunk])):
                ts = f.ts.timestamp()
                windows[code].add(objs, ts)
                analysed[code] += 1
                if code in zone_watch:
                    h, w = f.image.shape[:2]
                    gap = min(10.0, ts - last_ts[code]) if code in last_ts else interval
                    for e in zone_watch[code].update(objs, ts, w, h, max(gap, interval)):
                        sink.add_event(e)
                last_ts[code] = ts
            obj_frames += len(chunk)
            obj_ms += (time.perf_counter() - t0) * 1000
        if not ready:
            time.sleep(0.02)

        for code, w in windows.items():
            if w.due(now):
                sink.add_event(_mark(w.to_event(now, objects.name), sources[code]))
                windows[code] = CountWindow(code, s.count_window_s, now)
        if now - t_flush >= s.batch_flush_s:
            sink.flush()
            t_flush = now
        if now - t_beat >= s.heartbeat_s:
            span = max(1e-6, now - t_log)
            sink.heartbeat(s.counts_worker_id, list(sources), {c: round(n / span, 2) for c, n in analysed.items()})
            t_beat = now
        if now - t_log >= s.log_every_s:
            span = now - t_log
            up = sum(1 for x in sources.values() if x.connected)
            quiet = [c for c, x in sources.items() if now - x.last_frame_at > 30]
            log.info("%d/%d streams up | analysed %.1f frames/s (%.2f per camera) | objects %.0f ms/frame | count "
                     "rows sent %d%s", up, len(sources), sum(analysed.values()) / span,
                     sum(analysed.values()) / span / len(sources), obj_ms / max(1, obj_frames), sink.events_sent,
                     f" | no keyframe for 30 s: {', '.join(quiet)}" if quiet else "")
            for c in analysed:
                analysed[c] = 0
            obj_frames = obj_ms = 0.0
            t_log = now

    for src in sources.values():
        src.stop()
    for code, w in windows.items():     # partial windows are still real data; window_s says how long
        if w.frames:
            sink.add_event(_mark(w.to_event(time.time(), objects.name), sources[code]))
    sink.flush()
    return 0


def _mark(event: dict, src: KeyframeSource) -> dict:
    """How the camera was sampled: from its keyframes, or by decoding every frame (keyframes too far apart)."""
    event["detail"]["profile"] = "every-frame" if src.every_frame else "keyframes"
    return event


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
