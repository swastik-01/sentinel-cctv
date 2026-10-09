"""Request validation that turns a worker clock gone wrong or an oversized login into a 422, not a 500 or a stall."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel_api.schemas import LoginIn, SightingIn


def sighting(**over):
    base = {"camera_code": "CAM01", "event_ts": datetime.now(timezone.utc), "plate_text": "GJ99AB1234",
            "ocr_conf": 0.9, "det_conf": 0.8, "bbox": [0, 0, 40, 12]}
    return SightingIn(**{**base, **over})


def test_a_recent_aware_timestamp_passes():
    s = sighting(first_read_at=datetime.now(timezone.utc) - timedelta(seconds=2))
    assert s.event_ts.tzinfo is not None


def test_a_naive_timestamp_is_refused():
    with pytest.raises(ValidationError):
        sighting(event_ts=datetime.now())


def test_a_timestamp_far_from_now_is_refused():
    with pytest.raises(ValidationError):
        sighting(event_ts=datetime.now(timezone.utc) + timedelta(days=30))
    with pytest.raises(ValidationError):
        sighting(first_read_at=datetime.now(timezone.utc) - timedelta(days=400))


def test_a_bbox_beyond_an_integer_column_is_refused():
    with pytest.raises(ValidationError):
        sighting(bbox=[0, 0, 2**40, 12])


def test_login_fields_are_bounded():
    LoginIn(username="admin", password="x" * 128)
    with pytest.raises(ValidationError):
        LoginIn(username="admin", password="x" * 129)
    with pytest.raises(ValidationError):
        LoginIn(username="u" * 65, password="x")
