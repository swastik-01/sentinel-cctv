"""Confidence marking (bench/pipeline_gates.md, G3): what is marked "check the crop" and what is not. Synthetic
values only. The gate's own tests: a 0.85 sighting is marked; a 0.90 stored in the REAL column and read back is
not; a one-character (fuzzy) alert is marked; a journey stop carries the mark of its reads."""
import struct
from datetime import datetime, timedelta, timezone

from sentinel_api.journey import visits
from sentinel_api.marking import THRESHOLD, low_confidence, needs_review, reason


def as_real(x: float) -> float:
    """What Postgres hands back for a REAL column: single precision widened to a double."""
    return struct.unpack("f", struct.pack("f", x))[0]


def test_a_read_below_the_band_is_marked():
    assert needs_review(0.85)
    assert needs_review(0.899)


def test_0_9_stored_as_real_and_read_back_is_not_marked():
    assert as_real(0.9) < THRESHOLD                  # the widening the review page's SQL also guards against
    assert not needs_review(as_real(0.9))
    assert not needs_review(0.9)
    assert not needs_review(as_real(0.95))


def test_a_one_character_alert_is_marked_whatever_its_confidence():
    assert needs_review(as_real(0.97), exact_match=False)
    assert not needs_review(as_real(0.97), exact_match=True)


def test_no_confidence_is_not_low_but_a_fuzzy_match_still_marks():
    assert not low_confidence(None)
    assert not needs_review(None)
    assert needs_review(None, exact_match=False)


def test_the_reason_names_why():
    assert reason(0.95) is None
    assert "below 0.9" in reason(0.5)
    assert "one character off" in reason(0.95, exact_match=False)
    both = reason(0.5, exact_match=False)
    assert "below 0.9" in both and "one character off" in both


def _row(ts: datetime, conf: float, mark: bool | None) -> dict:
    return {"camera_code": "GJ-TEST-001", "camera_name": "Test", "district": None, "department": "Test",
            "lat": 23.0, "lon": 72.5, "event_ts": ts, "plate_norm": "GJ99AB1234", "ocr_conf": conf,
            "crop_path": None, "vehicle_type": None, "vehicle_color": None, "needs_review": mark}


def test_a_journey_stop_is_marked_when_any_of_its_reads_is():
    t0 = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
    rows = [_row(t0, 0.95, False), _row(t0 + timedelta(seconds=5), 0.6, True)]
    assert visits(rows, "GJ99AB1234")[0]["needs_review"] is True
    rows = [_row(t0, 0.95, False), _row(t0 + timedelta(seconds=5), 0.93, False)]
    assert visits(rows, "GJ99AB1234")[0]["needs_review"] is False


def test_a_journey_stop_carries_no_mark_when_marking_is_off():
    t0 = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
    assert visits([_row(t0, 0.6, None)], "GJ99AB1234")[0]["needs_review"] is None
