"""StaticText: fixed text (a hoarding's phone number) is stored once, then muted; vehicles are not."""
from sentinel_analytics.static_text import StaticText, iou, similar

# The boxes and reads the sandbox's CAM05 produced on 25 Sep for the hoarding "75750 83008".
HOARDING = [("TS75OB3008", (854, 740, 188, 50), 0.0), ("TS75OB3008", (838, 734, 204, 70), 22.0),
            ("TS75O8300", (838, 730, 204, 76), 23.0), ("TS75O8300", (838, 728, 204, 78), 32.0),
            ("TS75OB3008", (854, 736, 186, 56), 60.0), ("TS75O8300", (838, 730, 204, 76), 65.0),
            ("TS75OB3008", (840, 730, 202, 78), 80.0)]


def test_the_hoarding_is_stored_once():
    f = StaticText("CAM05")
    kept = [p for p, box, ts in HOARDING if f.allow(p, box, ts)]
    assert kept == ["TS75OB3008"]
    assert f.dropped == len(HOARDING) - 1


def test_different_vehicles_at_one_spot_are_all_stored():
    f = StaticText("CAM12")        # a toll booth: every vehicle stops at the same place
    booth = (600, 400, 120, 40)
    plates = ["GJ01AB1234", "GJ18KM4455", "MH04CD9087", "GJ27TT0011"]
    assert all(f.allow(p, booth, 30.0 * i) for i, p in enumerate(plates))


def test_plates_of_one_series_at_one_spot_are_all_stored():
    f = StaticText("CAM06")        # a gate: vehicles from one RTO pass the same place a minute apart
    gate = (700, 520, 110, 38)
    plates = ["GJ99AG1234", "GJ99AA5678", "GJ99AB2701", "GJ99AG5519"]     # synthetic: GJ99 is not an RTO
    assert all(f.allow(p, gate, 44.0 * i) for i, p in enumerate(plates))
    assert not similar("GJ99AG1234", "GJ99AG5519") and similar("TS75OB3008", "TS75O8300")


def test_same_plate_elsewhere_is_stored():
    f = StaticText("CAM14")
    assert f.allow("GJ01AB1234", (100, 600, 120, 40), 0.0)
    assert f.allow("GJ01AB1234", (1400, 300, 120, 40), 30.0)   # the vehicle moved on


def test_mute_lapses_when_the_text_stops_being_read():
    f = StaticText("CAM05", window_s=600, mute_s=1800)
    box = (838, 730, 204, 76)
    assert f.allow("TS75OB3008", box, 0.0)
    assert not f.allow("TS75OB3008", box, 10.0)          # muted from here
    assert not f.allow("TS75O8300", box, 1000.0)         # still read: mute extended
    assert f.allow("TS75OB3008", box, 1000.0 + 1801.0)   # unread for 30 min: stored again


def test_off_when_window_is_zero():
    f = StaticText("SIM", window_s=0)
    assert all(f.allow("GJ01ZZ0001", (10, 10, 50, 20), t) for t in (0.0, 60.0, 120.0))


def test_helpers():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 5, 5)) == 0.0
    assert similar("TS75OB3008", "TS75O8300") and not similar("GJ01AB1234", "MH04CD9087")
