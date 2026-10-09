"""The counts-only worker (counts.py): keyframe-only decoding, PTS timing, and which cameras it takes."""
import time

import av
import numpy as np
import pytest

from sentinel_analytics.counts import KeyframeSource, StreamClock, keyframes, long_gop, pick, scaled


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A 2 s, 25 fps H.264 clip with a keyframe every 10 frames, drawn so each frame differs."""
    path = tmp_path_factory.mktemp("clip") / "gop10.mp4"
    out = av.open(str(path), "w")
    st = out.add_stream("libx264", rate=25, options={"x264-params": "keyint=10:min-keyint=10:scenecut=0"})
    st.width, st.height, st.pix_fmt = 64, 48, "yuv420p"
    for i in range(50):
        img = np.full((48, 64, 3), 40, np.uint8)
        img[:, (i * 3) % 60: (i * 3) % 60 + 4] = 220
        for packet in st.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
            out.mux(packet)
    for packet in st.encode():
        out.mux(packet)
    out.close()
    return path


def test_only_keyframes_are_decoded(clip):
    with av.open(str(clip)) as c:
        frames = list(c.decode(c.streams.video[0]))
    with av.open(str(clip)) as c:
        keys = list(keyframes(c, _never()))
    assert len(frames) == 50
    assert len(keys) == sum(f.key_frame for f in frames) == 5
    assert all(f.key_frame for f in keys)


def test_every_frame_mode_decodes_them_all(clip):
    with av.open(str(clip)) as c:
        assert len(list(keyframes(c, _never(), every_frame=True))) == 50


def test_long_keyframe_intervals_switch_a_camera_to_every_frame():
    assert long_gop([0.0, 1.0, 2.0, 3.1]) == 0.0              # keyframes every second: keyframes only
    assert long_gop([0.0, 15.0, 30.5, 45.0]) == 15.0          # the sandbox's CAM07: every frame
    assert long_gop([0.0, 15.0]) == 0.0                       # one gap is not enough to decide
    assert long_gop([0.0, 2.0, 4.0, 30.0]) == 0.0             # one late keyframe is not a long GOP


def test_source_delivers_images_from_keyframes(clip):
    src = KeyframeSource("CLIP", str(clip), min_interval=0.0).start()
    try:
        deadline, f = time.time() + 10, None
        while f is None and time.time() < deadline:
            f = src.latest()
            time.sleep(0.02)
    finally:
        src.stop()
    assert f is not None and f.image.shape == (48, 64, 3)
    assert src.latest() is None or src.latest() is None    # a frame is handed out once


def test_clock_follows_pts_and_reanchors_on_a_loop():
    c = StreamClock()
    assert c.ts(0.0, 1000.0) == 1000.0
    assert c.ts(2.0, 1005.0) == 1002.0            # PTS, not arrival: a late frame keeps its own time
    assert c.ts(0.4, 1010.0) == 1010.0            # back to the start of the clip: a loop point
    assert c.discontinuities == 1
    assert c.ts(200.0, 1020.0) == 1020.0          # a jump forward beyond max_gap_s re-anchors too
    assert c.discontinuities == 2


def test_clock_falls_back_to_arrival_when_pts_is_missing_or_stuck():
    c = StreamClock()
    assert c.ts(None, 50.0) == 50.0
    for now in (60.0, 61.0, 62.0):
        c.ts(5.0, now)
    assert c.pts_usable is False
    assert c.ts(5.0, 63.0) == 63.0


def test_large_keyframes_are_scaled_down_keeping_their_shape():
    assert scaled(1920, 1080) == {"width": 960, "height": 540}
    assert scaled(2560, 1440) == {"width": 960, "height": 540}
    assert scaled(1280, 1024)["height"] == 768
    assert scaled(704, 576) == {} and scaled(960, 540) == {}


def test_pick_takes_every_camera_but_the_plate_workers_up_to_the_cap():
    cams = [{"camera_code": f"CAM{i:02d}"} for i in range(1, 11)]
    got, left = pick(cams, [], {"CAM06", "CAM07"}, 6)
    assert [c["camera_code"] for c in got] == ["CAM01", "CAM02", "CAM03", "CAM04", "CAM05", "CAM08"]
    assert left == ["CAM09", "CAM10"]
    got, left = pick(cams, ["CAM02", "CAM06"], {"CAM06"}, 60)
    assert [c["camera_code"] for c in got] == ["CAM02"] and left == []


def _never():
    import threading
    return threading.Event()
