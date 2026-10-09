"""A camera analysed slowly, or whose decode lags, must still produce its sightings.

With ~50 feeds on one machine each camera is analysed well below 1 fps, and a saturated
decoder makes frame times trail the wall clock. Both used to drop every track silently.
"""
import pytest

from sentinel_analytics.tracker import PlateDeduper

T0 = 1_790_000_000.0


def pass_by(rate_fps: float, in_view_s: float = 4.0, lag_s: float = 0.0, conf: float = 0.8) -> tuple[int, PlateDeduper]:
    """One vehicle in view for `in_view_s`, analysed at `rate_fps`; returns sightings emitted."""
    d = PlateDeduper("CAM-1", window_s=8.0)
    step = 1.0 / rate_fps
    for _ in range(5):                         # the worker measures the rate continuously
        d.observe_interval(step)
    out, t = [], 0.0
    while t <= in_view_s:
        d.offer("GJ01AB1234", conf, 0.9, (0, 0, 40, 12), ts=T0 + t - lag_s, crop=None, arrival=T0 + t)
        out += d.harvest(T0 + t)
        t += step
    out += d.harvest(T0 + in_view_s + 60)
    return len(out), d


@pytest.mark.parametrize("rate", [5.0, 1.0, 0.8, 0.5, 0.3])
def test_one_sighting_at_any_analysis_rate(rate):
    n, _ = pass_by(rate)
    assert n == 1


@pytest.mark.parametrize("rate", [5.0, 1.0, 0.5])
def test_lagging_frame_clock_does_not_drop_tracks(rate):
    n, _ = pass_by(rate, lag_s=1.5)
    assert n == 1


def test_single_read_needs_a_slow_camera_and_confidence():
    n, d = pass_by(0.2, in_view_s=3.0)         # seen once, confidently: accepted, and counted
    assert n == 1 and d.single_reads == 1
    n, _ = pass_by(0.2, in_view_s=3.0, conf=0.4)
    assert n == 0                              # one weak read is still noise


def test_fast_camera_still_rejects_single_reads():
    d = PlateDeduper("CAM-1", window_s=8.0)
    for _ in range(5):
        d.observe_interval(0.2)                # 5 fps
    d.offer("GJ01AB1234", 0.9, 0.9, (0, 0, 40, 12), ts=T0, crop=None, arrival=T0)
    assert d.harvest(T0 + 5) == []             # a plate seen once at 5 fps is a mis-detection


def test_hold_stretches_with_the_interval():
    d = PlateDeduper("CAM-1", window_s=8.0, confirm_s=1.0)
    assert d.hold_s == 1.0
    for _ in range(20):
        d.observe_interval(2.0)
    assert d.hold_s == pytest.approx(5.0, rel=0.05) and d.slow
