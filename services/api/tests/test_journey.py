"""Movement history as a journey: visits, hops and the implausible-speed flag."""
from datetime import datetime, timedelta, timezone

from sentinel_api.journey import haversine_m, visits

T0 = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
CAM = {  # Gandhinagar and Ahmedabad simulator positions
    "GNR-POL-001": (23.2233, 72.6503), "GNR-GSRTC-001": (23.2156, 72.6369), "AMD-POL-001": (23.0258, 72.5873),
    "GNR-NEAR": (23.2233, 72.6552),   # ~500 m east of GNR-POL-001
}


def read(cam, minute, plate="GJ01AB1234", conf=0.9, second=0):
    lat, lon = CAM[cam]
    return {"camera_code": cam, "camera_name": cam, "lat": lat, "lon": lon, "plate_norm": plate,
            "event_ts": T0 + timedelta(minutes=minute, seconds=second), "ocr_conf": conf}


def test_reads_at_one_camera_become_one_visit():
    v = visits([read("GNR-POL-001", 0), read("GNR-POL-001", 0, second=20), read("GNR-POL-001", 1)], "GJ01AB1234")
    assert len(v) == 1 and v[0]["reads"] == 3 and v[0]["dwell_s"] == 60 and v[0]["n"] == 1


def test_a_return_after_the_gap_is_a_new_visit():
    v = visits([read("GNR-POL-001", 0), read("GNR-POL-001", 30)], "GJ01AB1234")
    assert [x["n"] for x in v] == [1, 2]


def test_hop_between_exact_visits_has_distance_time_speed():
    v = visits([read("GNR-POL-001", 0), read("AMD-POL-001", 40)], "GJ01AB1234")
    hop = v[1]["hop"]
    d = haversine_m(*CAM["GNR-POL-001"], *CAM["AMD-POL-001"])
    assert hop["from_n"] == 1 and hop["distance_m"] == round(d) and hop["travel_s"] == 2400
    assert 30 < hop["speed_kmh"] < 40 and not hop["implausible"]


def test_impossible_speed_is_flagged():
    v = visits([read("GNR-POL-001", 0), read("AMD-POL-001", 2)], "GJ01AB1234")   # ~23 km in 2 min
    assert v[1]["hop"]["implausible"]


def test_near_miss_visit_is_marked_and_skipped_for_speed():
    v = visits([read("GNR-POL-001", 0), read("GNR-GSRTC-001", 1, plate="GJ01AB1284"),
                read("AMD-POL-001", 40)], "GJ01AB1234")
    assert v[1]["possible_misread"] and v[1]["hop"] is None
    assert v[2]["hop"]["from_n"] == 1                 # the hop spans the misread stop


def test_hops_between_close_cameras_are_not_flagged():
    v = visits([read("GNR-POL-001", 0), read("GNR-NEAR", 0, second=10)], "GJ01AB1234")
    assert v[1]["hop"]["distance_m"] < 1000 and not v[1]["hop"]["implausible"]   # placement error dominates


def test_a_stop_without_a_leg_says_why():
    v = visits([read("AMD-POL-001", 0, plate="GJ01AB1284"), read("GNR-POL-001", 1), read("GNR-POL-001", 30)], "GJ01AB1234")
    assert v[0]["hop_note"].startswith("possible misread")
    assert v[1]["hop_note"] == "first exact read"                 # not "same camera": the camera before it was a misread
    assert v[2]["hop_note"] == "same camera as stop 2"
