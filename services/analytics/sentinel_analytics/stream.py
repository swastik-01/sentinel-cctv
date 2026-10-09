"""RTSP source: one decode thread per camera, latest-frame semantics, frame timestamps.

Sandbox rules honoured here:
  - RTSP over TCP (set via OPENCV_FFMPEG_CAPTURE_OPTIONS in __init__)
  - auto-reconnect with exponential backoff
  - event time comes from the stream position (PTS), not from arrival time: we anchor a
    wall-clock epoch to the first decoded frame and add the stream's own PTS offset,
    so buffering or a slow consumer never shifts timestamps
  - PTS fallback: some live RTSP sources report a position that never advances. If the
    position has not moved after PTS_PROBE_FRAMES, the source is marked `pts_usable=False`
    and timing falls back to the decode clock, with one warning. Without this, every
    sighting on such a camera would carry an identical timestamp.
  - loop-point / discontinuity handling: a PTS jump backwards or a gap > 5 s re-anchors
  - decoder complaints (e.g. joining mid-GOP) are counted and logged, never fatal
  - CAP_PROP_FPS is recorded for reporting only; no timing decision depends on it

Hardware decode (hw_decode="auto"): OpenCV is asked for any hardware decoder (D3D11 on
Windows: NVDEC or an Intel iGPU; VAAPI on Linux). Decoding every frame of every stream
is what limits streams per machine, and the GPU's decoder is otherwise idle. If a camera
will not open, or delivers no frame, with hardware decode, it falls back to software
for that camera and says so once.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

log = logging.getLogger("sentinel.stream")
MIN_BACKOFF = 2.0      # sandbox guidance: start ~2 s
MAX_BACKOFF = 30.0     # ...cap ~30 s
# A connection counts as healthy, and the backoff starts again from MIN_BACKOFF, only after this long. On 25-26 Sep
# the sandbox kept dropping sessions a few seconds in, after a few frames: resetting on the first frame made every
# camera reconnect every 2-5 s, and that retry storm preceded two login lockouts.
STABLE_S = 60.0
PTS_PROBE_FRAMES = 60  # frames to decide whether the source's PTS actually advances


@dataclass
class Frame:
    image: np.ndarray
    ts: datetime          # frame timestamp (UTC)
    seq: int
    pos_ms: float


ACCEL_NAMES = {0: "software", 1: "any", 2: "D3D11", 3: "VAAPI", 4: "MFX"}
HW_FIRST_FRAME_TRIES = 50   # grabs allowed before a hardware-decoded camera is declared stuck


@dataclass
class Stats:
    decoder: str = "software"    # what OpenCV actually gave us, per connection
    decoded: int = 0
    retrieved: int = 0
    dropped: int = 0
    reconnects: int = 0
    decode_hiccups: int = 0      # failed grabs/retrieves: logged, never fatal
    discontinuities: int = 0
    pts_usable: bool = True      # False = source PTS never advanced; using the decode clock
    last_frame_at: float = 0.0
    connected: bool = False
    width: int = 0
    height: int = 0
    src_fps: float = 0.0
    errors: list[str] = field(default_factory=list)


class RtspSource:
    """`retrieve_fps` caps how often a decoded frame is converted to a BGR image. Every frame
    must still be decoded (inter-frame codecs), but colour conversion and the copy of a
    1080p image are a large share of per-stream CPU, and analysis needs only a few per second."""

    def __init__(self, code: str, url: str, retrieve_fps: float = 0.0, hw_decode: str = "off"):
        self.code, self.url = code, url
        self.hw_wanted = hw_decode == "auto"
        self._hw_failed = False
        self.retrieve_interval = 1.0 / retrieve_fps if retrieve_fps > 0 else 0.0
        self.stats = Stats()
        self._latest: Frame | None = None
        self._consumed_seq = -1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"rtsp-{code}", daemon=True)

    def start(self) -> "RtspSource":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> Frame | None:
        """Newest frame not yet handed out; None if nothing new since last call."""
        with self._lock:
            f = self._latest
            if f is None or f.seq == self._consumed_seq:
                return None
            self._consumed_seq = f.seq
            return f

    # ------------------------------------------------------------------ decode loop
    def _open(self) -> cv2.VideoCapture | None:
        cap = None
        if self.hw_wanted and not self._hw_failed:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY])
            if not cap.isOpened():
                cap.release()
                cap = None
                self._fall_back("hardware decode would not open the stream")
            elif not cap.get(cv2.CAP_PROP_FRAME_WIDTH) or not cap.get(cv2.CAP_PROP_FRAME_HEIGHT):
                # The hardware decoder failed to initialise but the capture still "opened" at 0x0: every
                # retrieve then fails. Seen on a sandbox H.264 camera; fall back now, not after 50 failures.
                cap.release()
                cap = None
                self._fall_back("hardware decode opened the stream at 0x0")
        if cap is None:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        self.stats.decoder = ACCEL_NAMES.get(int(cap.get(cv2.CAP_PROP_HW_ACCELERATION) or 0), "other")
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.stats.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.stats.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.stats.src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        return cap

    def _run(self) -> None:
        backoff = MIN_BACKOFF
        seq = 0
        while not self._stop.is_set():
            cap = self._open()
            if cap is None:
                self.stats.connected = False
                self._note(f"connect failed, retry in {backoff:.0f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            self.stats.connected = True
            self.stats.reconnects += 1
            connected_at = time.monotonic()
            log.info("%s: connected %dx%d @ %.1f fps, %s decode", self.code, self.stats.width,
                     self.stats.height, self.stats.src_fps, self.stats.decoder)
            on_hw = self.stats.decoder != "software"
            first_frame = False
            epoch: float | None = None
            last_pos = -1.0
            fails = 0
            next_retrieve = 0.0
            frames_here = 0
            first_pos: float | None = None
            pts_ok = True
            while not self._stop.is_set():
                if not cap.grab():
                    fails += 1
                    self.stats.decode_hiccups += 1
                    if on_hw and not first_frame and fails >= HW_FIRST_FRAME_TRIES // 2:
                        self._fall_back("no frame from the hardware decoder")
                        break
                    if fails >= 25:
                        self._note(f"{fails} consecutive decode failures, reconnecting")
                        break
                    time.sleep(0.02)
                    continue
                fails = 0
                now = time.time()
                pos = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                self.stats.decoded += 1
                self.stats.last_frame_at = now
                frames_here += 1

                # Does this source's PTS actually advance? Some live RTSP servers report 0 forever.
                if first_pos is None:
                    first_pos = pos
                elif pts_ok and frames_here == PTS_PROBE_FRAMES and abs(pos - first_pos) < 1.0:
                    pts_ok = False
                    self.stats.pts_usable = False
                    log.warning("%s: stream position never advanced over %d frames — falling back to the "
                                "decode clock for event timestamps", self.code, PTS_PROBE_FRAMES)

                if pts_ok:
                    if epoch is None or pos < last_pos - 500 or pos - last_pos > 5000:
                        # first frame, loop point, or a discontinuity: re-anchor stream time to now
                        if epoch is not None:
                            self.stats.discontinuities += 1
                            log.info("%s: scene discontinuity %.0f -> %.0f ms, re-anchoring", self.code, last_pos, pos)
                        epoch = now - pos / 1000.0
                    last_pos = pos
                if now < next_retrieve:
                    continue
                ok, img = cap.retrieve()
                if not ok or img is None:
                    self.stats.decode_hiccups += 1
                    if on_hw and not first_frame and self.stats.decode_hiccups >= HW_FIRST_FRAME_TRIES:
                        self._fall_back("the hardware decoder returned no image")
                        break
                    continue
                first_frame = True
                next_retrieve = now + self.retrieve_interval
                ts = datetime.fromtimestamp(epoch + pos / 1000.0 if pts_ok else now, tz=timezone.utc)
                seq += 1
                with self._lock:
                    if self._latest is not None and self._latest.seq != self._consumed_seq:
                        self.stats.dropped += 1
                    self._latest = Frame(img, ts, seq, pos)
                self.stats.retrieved += 1
            cap.release()
            self.stats.connected = False
            if time.monotonic() - connected_at >= STABLE_S:
                backoff = MIN_BACKOFF              # it had been working: retry soon
            if not self._stop.is_set():
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    def _fall_back(self, why: str) -> None:
        if not self._hw_failed:
            self._hw_failed = True
            log.warning("%s: %s; using software decode for this camera", self.code, why)

    def _note(self, msg: str) -> None:
        log.warning("%s: %s", self.code, msg)
        self.stats.errors = (self.stats.errors + [msg])[-5:]
