"""RtspSource._open: a hardware decoder that "opens" a stream at 0x0 must fall back to software at once.
Seen on a sandbox H.264 camera (25 Sep): D3D11 initialisation failed, OpenCV still reported the capture
open, and every retrieve failed until 50 failures had been counted."""
import cv2
import pytest

from sentinel_analytics import stream as stream_mod
from sentinel_analytics.stream import RtspSource


class FakeCap:
    def __init__(self, url, api, params=None):
        self.hw = bool(params)
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        if prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT):
            return 0.0 if self.hw else (1920.0 if prop == cv2.CAP_PROP_FRAME_WIDTH else 1080.0)
        if prop == cv2.CAP_PROP_HW_ACCELERATION:
            return 2.0 if self.hw else 0.0
        if prop == cv2.CAP_PROP_FPS:
            return 90000.0 if self.hw else 10.0
        return 0.0

    def set(self, prop, value):
        return True

    def release(self):
        self.released = True


@pytest.fixture
def fake_capture(monkeypatch):
    made = []

    def factory(url, api, params=None):
        cap = FakeCap(url, api, params)
        made.append(cap)
        return cap

    monkeypatch.setattr(stream_mod.cv2, "VideoCapture", factory)
    return made


def test_zero_size_hardware_open_falls_back_to_software(fake_capture):
    src = RtspSource("CAM15", "rtsp://relay/CAM15", hw_decode="auto")
    cap = src._open()
    assert cap is not None and not cap.hw                 # the software capture was returned
    assert fake_capture[0].hw and fake_capture[0].released  # the 0x0 hardware capture was closed
    assert src._hw_failed and src.stats.decoder == "software"
    assert (src.stats.width, src.stats.height) == (1920, 1080)


def test_software_only_when_hardware_decode_is_off(fake_capture):
    src = RtspSource("CAM16", "rtsp://relay/CAM16", hw_decode="off")
    cap = src._open()
    assert len(fake_capture) == 1 and not cap.hw and not src._hw_failed
