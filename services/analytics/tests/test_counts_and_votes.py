"""Count windows and the per-track attribute vote."""
from sentinel_analytics.objects import CountWindow, Obj
from sentinel_analytics.tracker import PlateDeduper, pick

T0 = 1_790_000_000.0


def objs(*labels):
    return [Obj(lab, (0, 0, 10, 10), 0.9) for lab in labels]


def test_window_carries_numerator_and_denominator():
    w = CountWindow("CAM-1", 60, T0)
    w.add(objs("car", "car", "person"), T0 + 1)
    w.add(objs("car", "truck"), T0 + 2)
    w.add([], T0 + 3)
    assert not w.due(T0 + 59) and w.due(T0 + 60)
    e = w.to_event(T0 + 60, "yolo11n")
    assert e["event_type"] == "object_counts" and e["value"] == 3
    d = e["detail"]
    assert d["detections"] == {"car": 3, "person": 1, "truck": 1}
    assert d["peak"] == {"car": 2, "person": 1, "truck": 1}
    assert d["peak_vehicles"] == 2 and d["frames"] == 3 and "reason" not in d


def test_count_rows_carry_no_identity():
    w = CountWindow("CAM-1", 60, T0)
    w.add(objs("person", "person"), T0 + 1)
    e = w.to_event(T0 + 60, "yolo11n")
    assert not {"bbox", "track_id", "label", "confidence"} & e.keys()


def test_empty_window_says_why():
    e = CountWindow("CAM-1", 60, T0).to_event(T0 + 60, "yolo11n")
    assert e["value"] == 0 and "reason" in e["detail"]


def test_pick():
    assert pick([], 0.5) is None
    assert pick([("car", 0.8)], 0.5) == "car"                      # one confident read is enough
    assert pick([("car", 0.45)], 0.5) is None                      # one weak read is not
    assert pick([("car", 0.6), ("truck", 0.6)], 0.5) is None       # split vote: no answer
    assert pick([("bus", 0.7), ("bus", 0.6), ("truck", 0.5)], 0.5) == "bus"


def test_first_read_attribution_is_kept():
    d = PlateDeduper("CAM-1", window_s=8, confirm_s=1.0, confirm_reads=3, min_reads=2)
    d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0, None, ("car", 0.8), ("white", 0.7))
    d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0 + 0.2, None)
    d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0 + 0.4, None)
    (r,) = d.harvest(T0 + 2)
    assert (r.vehicle_type, r.vehicle_color) == ("car", "white")


def test_unattributed_track_stays_null():
    d = PlateDeduper("CAM-1", window_s=8, confirm_s=1.0, confirm_reads=3, min_reads=2)
    for k in range(3):
        d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0 + k * 0.2, None)
    (r,) = d.harvest(T0 + 2)
    assert r.vehicle_type is None and r.vehicle_color is None


def test_no_colour_without_a_confident_type():
    d = PlateDeduper("CAM-1", window_s=8, confirm_s=1.0, confirm_reads=3, min_reads=2)
    d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0, None, ("car", 0.42), ("red", 0.8))   # weak type
    for k in (1, 2):
        d.offer("GJ01AB1234", 0.9, 0.8, (0, 0, 10, 4), T0 + k * 0.2, None)
    (r,) = d.harvest(T0 + 2)
    assert r.vehicle_type is None and r.vehicle_color is None


def test_stored_plate_is_the_vote_not_the_best_single_read():
    d = PlateDeduper("CAM-1", window_s=8.0)
    for text, conf in [("GJ01AB1234", 0.70), ("GJ01AB8234", 0.90), ("GJ01AB1234", 0.72)]:
        d.offer(text, conf, 0.9, (0, 0, 40, 12), ts=T0, crop=None, arrival=T0)
    (r,) = d.harvest(T0 + 5)
    assert r.plate_text == "GJ01AB8234"        # the sharpest single read got one character wrong...
    assert r.plate_norm == "GJ01AB1234"        # ...and the vote across reads fixes it; sink sends this


def test_a_misread_variant_does_not_pass_the_repeat_filter():
    d = PlateDeduper("CAM-1", window_s=8.0)
    for i in range(3):
        d.offer("GJ01ZZ0001", 0.9, 0.9, (0, 0, 40, 12), ts=T0 + i * 0.2, crop=None, arrival=T0 + i * 0.2)
    assert len(d.harvest(T0 + 2)) == 1
    for i in range(3):                               # same vehicle, next frames, read one character off
        d.offer("GJ11ZZ0001", 0.6, 0.9, (0, 0, 40, 12), ts=T0 + 3 + i * 0.2, crop=None, arrival=T0 + 3 + i * 0.2)
    assert d.harvest(T0 + 5) == []                   # not a new vehicle
    for i in range(3):                               # a genuinely different plate still gets through
        d.offer("MH12AB4321", 0.9, 0.9, (0, 0, 40, 12), ts=T0 + 6 + i * 0.2, crop=None, arrival=T0 + 6 + i * 0.2)
    assert [r.plate_norm for r in d.harvest(T0 + 8)] == ["MH12AB4321"]
