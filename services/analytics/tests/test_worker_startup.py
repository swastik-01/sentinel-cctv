"""A starting worker waits for the API instead of exiting (the API restarts after every change)."""
import pytest

from sentinel_analytics.worker import fetch_cameras


class FlakySink:
    def __init__(self, failures: int):
        self.failures, self.calls = failures, 0

    def cameras(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("refused")
        return [{"camera_code": "CAM01"}]


def test_waits_for_the_api():
    slept = []
    sink = FlakySink(failures=3)
    assert fetch_cameras(sink, wait_s=300, sleep=slept.append) == [{"camera_code": "CAM01"}]
    assert slept == [2.0, 4.0, 8.0]                  # backing off


def test_gives_up_after_the_wait():
    slept = []
    with pytest.raises(ConnectionError):
        fetch_cameras(FlakySink(failures=100), wait_s=60, sleep=slept.append)
    assert sum(slept) >= 60 and max(slept) <= 30.0
