"""RtspSource reconnects back off when a source keeps dropping sessions after a few frames (the sandbox, 25-26 Sep):
the backoff must grow to its cap, not start again at 2 s because a frame or two arrived."""
import cv2
import numpy as np
import pytest

from sentinel_analytics import stream as stream_mod
from sentinel_analytics.stream import MAX_BACKOFF, MIN_BACKOFF, RtspSource


class FlakyCap:
    """Opens fine, delivers a few frames, then every grab fails (the server dropped the session)."""

    def __init__(self, url, api, params=None):
        self.left = 3

    def isOpened(self):
        return True

    def get(self, prop):
        return {cv2.CAP_PROP_FRAME_WIDTH: 1920.0, cv2.CAP_PROP_FRAME_HEIGHT: 1080.0, cv2.CAP_PROP_FPS: 25.0}.get(prop, 0.0)

    def set(self, prop, value):
        return True

    def grab(self):
        self.left -= 1
        return self.left >= 0

    def retrieve(self):
        return True, np.zeros((8, 8, 3), np.uint8)

    def release(self):
        pass


def run_until(src, monkeypatch, reconnects):
    """Run the decode loop in this thread, recording the reconnect sleeps, until `reconnects` of them."""
    waits = []

    def fake_sleep(s):
        if s >= 1.0:                  # reconnect backoff, not the 20 ms pause between failed grabs
            waits.append(s)
            if len(waits) >= reconnects:
                src._stop.set()

    monkeypatch.setattr(stream_mod.time, "sleep", fake_sleep)
    src._run()
    return waits


@pytest.fixture
def flaky(monkeypatch):
    monkeypatch.setattr(stream_mod.cv2, "VideoCapture", FlakyCap)


def test_backoff_grows_when_sessions_keep_dropping(flaky, monkeypatch):
    src = RtspSource("CAM06", "rtsp://relay/CAM06", hw_decode="off")
    waits = run_until(src, monkeypatch, 6)
    assert waits == [MIN_BACKOFF, 4.0, 8.0, 16.0, MAX_BACKOFF, MAX_BACKOFF]


def test_backoff_starts_again_after_a_healthy_connection(flaky, monkeypatch):
    monkeypatch.setattr(stream_mod, "STABLE_S", 0.0)       # every session counts as healthy
    src = RtspSource("CAM06", "rtsp://relay/CAM06", hw_decode="off")
    waits = run_until(src, monkeypatch, 4)
    assert waits == [MIN_BACKOFF] * 4
