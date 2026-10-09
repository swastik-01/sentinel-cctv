"""Intrusion zones: ground point in polygon, dwell, armed hours, gaps, and what an event carries."""
from datetime import datetime, timezone

from sentinel_analytics.objects import Obj
from sentinel_analytics.zones import Zone, ZoneWatch, inside, zones_for

W, H = 1000, 1000
GATE = Zone.parse({"id": "gate", "name": "Depot gate", "polygon": [[0.1, 0.5], [0.4, 0.5], [0.4, 0.9], [0.1, 0.9]],
                   "classes": ["person"], "min_dwell_s": 3})
T0 = datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc).timestamp()   # 04:30 IST


def person(x, y_top, h=200, w=60):
    return Obj("person", (x, y_top, w, h), 0.8)


def test_ground_point_decides():
    assert inside(GATE.polygon, 0.25, 0.7) and not inside(GATE.polygon, 0.6, 0.7)
    zw = ZoneWatch("CAM", [GATE])
    head_in_feet_out = person(200, 400, h=560)       # box spans the zone but the feet are below it
    assert zw.update([head_in_feet_out], T0, W, H) == [] and zw._state["gate"].since is None


def test_dwell_then_one_event_per_occupancy():
    zw = ZoneWatch("CAM", [GATE])
    ev = []
    for t in range(0, 8):                            # standing in the zone for 7 s at 1 fps
        ev += zw.update([person(200, 500)], T0 + t, W, H, interval=1.0)
    assert len(ev) == 1 and ev[0]["event_type"] == "intrusion" and ev[0]["detail"]["dwell_s"] == 3.0


def test_passing_through_faster_than_dwell_is_ignored():
    zw = ZoneWatch("CAM", [GATE])
    assert zw.update([person(200, 500)], T0, W, H) + zw.update([person(200, 500)], T0 + 1, W, H) == []


def test_missed_frames_do_not_split_an_occupancy():
    zw = ZoneWatch("CAM", [GATE])
    ev = zw.update([person(200, 500)], T0, W, H, interval=1.0)
    ev += zw.update([], T0 + 1, W, H, interval=1.0)             # detector missed them
    ev += zw.update([person(200, 500)], T0 + 2, W, H, interval=1.0)
    ev += zw.update([person(200, 500)], T0 + 3, W, H, interval=1.0)
    assert len(ev) == 1


def test_a_new_occupancy_after_the_zone_empties_raises_again():
    zw = ZoneWatch("CAM", [GATE])
    ev = [e for t in range(5) for e in zw.update([person(200, 500)], T0 + t, W, H)]
    ev += [e for t in range(30, 35) for e in zw.update([person(200, 500)], T0 + t, W, H)]
    assert len(ev) == 2


def test_armed_hours_overnight():
    night = Zone.parse({**GATE.__dict__, "polygon": GATE.polygon, "armed": {"from": "22:00", "to": "06:00"}})
    assert night.armed(T0)                                          # 04:30 IST
    day = datetime(2026, 9, 24, 6, 30, tzinfo=timezone.utc).timestamp()   # 12:00 IST
    assert not night.armed(day)
    zw = ZoneWatch("CAM", [night])
    assert [e for t in range(6) for e in zw.update([person(200, 500)], day + t, W, H)] == []


def test_event_carries_no_identity():
    zw = ZoneWatch("CAM", [GATE])
    (e,) = [e for t in range(5) for e in zw.update([person(200, 500), person(300, 500)], T0 + t, W, H)]
    assert not {"bbox", "track_id", "crop_path"} & e.keys()
    assert e["value"] == 2 and e["detail"]["classes"] == {"person": 2}


def test_other_classes_do_not_trigger_a_person_zone():
    zw = ZoneWatch("CAM", [GATE])
    car = Obj("car", (150, 600, 200, 150), 0.9)
    assert [e for t in range(6) for e in zw.update([car], T0 + t, W, H)] == []


def test_malformed_zone_is_skipped():
    zs = zones_for({"camera_code": "CAM", "zones": [{"id": "x"}, {"id": "ok", "polygon": [[0, 0], [1, 0], [1, 1]]}]})
    assert [z.id for z in zs] == ["ok"]
