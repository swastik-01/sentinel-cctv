"""The live event socket: a user scoped to a department or district receives only events about cameras in that
scope (alerts.scoped_event); a statewide user receives every event unchanged."""
import json

from sentinel_api.routers.alerts import scoped_event

MINE = {"GNR-GSRTC-001", "GNR-GSRTC-002"}


def ev(**kw) -> str:
    return json.dumps({"at": "2026-10-08T12:00:00+00:00", **kw})


def test_a_statewide_user_sees_every_event_unchanged():
    m = ev(type="sighting.new", sighting={"camera_code": "AMD-AMC-001"})
    assert scoped_event(m, None) == m


def test_events_about_one_camera_pass_only_for_a_camera_in_scope():
    for kind, key in (("alert.new", "alert"), ("alert.updated", "alert"), ("sighting.new", "sighting")):
        assert scoped_event(ev(type=kind, **{key: {"camera_code": "GNR-GSRTC-001"}}), MINE) is not None
        assert scoped_event(ev(type=kind, **{key: {"camera_code": "AMD-AMC-001"}}), MINE) is None
    assert scoped_event(ev(type="camera.health", camera_code="GNR-GSRTC-002", to="offline"), MINE) is not None
    assert scoped_event(ev(type="camera.health", camera_code="AMD-POL-001", to="offline"), MINE) is None


def test_counts_and_heartbeats_are_cut_down_to_the_scope():
    out = json.loads(scoped_event(ev(type="detection.counts", cameras=[
        {"camera_code": "GNR-GSRTC-001", "frames": 60}, {"camera_code": "AMD-AMC-001", "frames": 60}]), MINE))
    assert [c["camera_code"] for c in out["cameras"]] == ["GNR-GSRTC-001"]
    out = json.loads(scoped_event(ev(type="worker.heartbeat", worker_id="worker-1",
                                     cameras=["AMD-AMC-001", "GNR-GSRTC-002"],
                                     fps={"AMD-AMC-001": 4.9, "GNR-GSRTC-002": 5.0}), MINE))
    assert out["cameras"] == ["GNR-GSRTC-002"] and out["fps"] == {"GNR-GSRTC-002": 5.0}
    assert scoped_event(ev(type="detection.counts", cameras=[{"camera_code": "AMD-AMC-001"}]), MINE) is None
    assert scoped_event(ev(type="worker.heartbeat", cameras=["AMD-AMC-001"], fps={}), MINE) is None


def test_unknown_or_unreadable_events_are_dropped_for_a_scoped_user():
    assert scoped_event(ev(type="something.new", camera_code="GNR-GSRTC-001"), MINE) is None
    assert scoped_event("not json", MINE) is None
    assert scoped_event(ev(type="alert.new", alert={}), MINE) is None
