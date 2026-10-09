"""Replay recorded/synthetic clips as live RTSP cameras into MediaMTX.

One supervised ffmpeg process per camera streams the clip with `-c copy`, so mixed
H.264/H.265 and mixed resolutions cost almost nothing on the host.

H.265 cameras' browser preview (`<code>_sub`) is transcoded on demand by MediaMTX
itself (see infra/mediamtx.yml), so this process only replays the original streams.

Outage simulation: the catalogue writes {code: until_epoch} to STATE_DIR/outages.json;
this process kills the matching stream and holds it down until the deadline.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import yaml

MEDIA = Path(os.environ.get("MEDIA_DIR", "media"))
CAMERAS = Path(os.environ.get("CAMERAS_FILE", "cameras.yaml"))
STATE = Path(os.environ.get("STATE_DIR", "/state"))
RTSP_BASE = os.environ.get("MEDIAMTX_RTSP", "rtsp://mediamtx:8554").rstrip("/")
MAX_BACKOFF = 20.0


def main_cmd(cam: dict) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
        "-re", "-stream_loop", "-1", "-fflags", "+genpts",
        "-i", str(MEDIA / f"{cam['code']}.mp4"),
        "-c", "copy", "-an",
        "-f", "rtsp", "-rtsp_transport", "tcp", f"{RTSP_BASE}/{cam['code']}",
    ]


class Proc:
    """A supervised ffmpeg process with exponential restart backoff."""

    def __init__(self, name: str, cmd: list[str], wanted: Callable[[], bool], label: str):
        self.name, self.cmd, self.wanted, self.label = name, cmd, wanted, label
        self.proc: subprocess.Popen | None = None
        self.backoff = 1.0
        self.next_start = 0.0

    def tick(self, now: float) -> None:
        alive = self.proc is not None and self.proc.poll() is None
        if not self.wanted():
            if alive:
                print(f"[pub] {self.name}: held down, stopping", flush=True)
                self.stop()
            return
        if alive:
            if now - self.started > 10:
                self.backoff = 1.0
            return
        if self.proc is not None:
            print(f"[pub] {self.name}: ffmpeg exited rc={self.proc.returncode}, "
                  f"retry in {self.backoff:.0f}s", flush=True)
            self.proc = None
            self.next_start = now + self.backoff
            self.backoff = min(self.backoff * 2, MAX_BACKOFF)
            return
        if now >= self.next_start:
            print(f"[pub] {self.name}: {self.label}", flush=True)
            self.proc = subprocess.Popen(self.cmd)
            self.started = now

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


def read_outages() -> dict[str, float]:
    try:
        return json.loads((STATE / "outages.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main() -> int:
    cams = yaml.safe_load(CAMERAS.read_text())["cameras"]
    outages: dict[str, float] = {}

    def up(code: str) -> Callable[[], bool]:
        return lambda: (MEDIA / f"{code}.mp4").exists() and time.time() >= outages.get(code, 0.0)

    procs: list[Proc] = []
    for cam in cams:
        code = cam["code"]
        procs.append(Proc(code, main_cmd(cam), up(code), f"publishing {cam['codec']} {cam['resolution']}"))

    missing = [c["code"] for c in cams if not (MEDIA / f"{c['code']}.mp4").exists()]
    if missing:
        print(f"[pub] no clip for {len(missing)} camera(s): {', '.join(missing)}. "
              f"Run synth.py or drop real footage into media/.", flush=True)

    running = True

    def shutdown(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while running:
        now = time.time()
        outages.clear()
        outages.update(read_outages())
        for p in procs:
            p.tick(now)
        time.sleep(1.0)

    for p in procs:
        p.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
