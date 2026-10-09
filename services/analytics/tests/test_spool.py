"""Store-and-forward: nothing is lost while the API is down, and hits still register at the edge."""
import json

import httpx
import pytest

from sentinel_analytics import config
from sentinel_analytics.sink import ApiSink, edits_within
from sentinel_analytics.spool import Spool


class FakeApi:
    """Stands in for the ingest API; `up` switches the link on and off."""

    def __init__(self):
        self.up = True
        self.received: list[dict] = []
        self.status = 200
        self.batches: set[str] = set()
        self.lose_next_reply = False       # store the batch, then fail as if the reply never arrived

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("backhaul down", request=request)
        if request.url.path == "/ingest/watchlist":
            return httpx.Response(200, json={"max_edits": 1, "cooldown_s": 120, "entries": [
                {"plate_norm": "GJ01AB1234", "kind": "stolen_vehicle", "severity": "high"}]})
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        batch = json.loads(request.content)
        bid = request.url.params.get("batch_id")
        if bid in self.batches:                # the API's ingest_batches check
            return httpx.Response(200, json={"stored": 0, "alerts": 0, "duplicate_batch": True})
        self.batches.add(bid)
        if request.url.path == "/ingest/sightings":
            self.received.extend(batch)
        if self.lose_next_reply:
            self.lose_next_reply = False
            raise httpx.ReadTimeout("reply lost", request=request)
        return httpx.Response(200, json={"stored": len(batch), "alerts": 0})


@pytest.fixture
def sink(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOOL_DIR", str(tmp_path / "spool"))
    monkeypatch.setenv("SPOOL_MAX_MB", "1")
    config.get_settings.cache_clear()
    api = FakeApi()
    s = ApiSink()
    s.client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(api))
    s.api = api
    yield s
    config.get_settings.cache_clear()


def sighting(plate, n=0):
    return {"camera_code": "CAM-1", "event_ts": f"2026-09-23T10:00:{n:02d}+00:00", "plate_text": plate,
            "ocr_conf": 0.9, "det_conf": 0.8, "vehicle_type": None, "vehicle_color": None,
            "bbox": [0, 0, 10, 5], "track_id": "t", "crop_path": None}


def test_outage_spools_then_replays_in_order(sink):
    sink.refresh_watchlist()
    sink.api.up = False
    for i in range(3):
        sink._queue.append(sighting(f"GJ05CD{1000 + i}", i))
        sink.flush()
    assert sink.api.received == [] and sink.spooled == 3
    assert len(sink.spool.pending()) >= 1

    sink.api.up = True
    sink._down_until = 0.0                    # the backoff has elapsed
    sink.flush()
    assert [s["plate_text"] for s in sink.api.received] == ["GJ05CD1000", "GJ05CD1001", "GJ05CD1002"]
    assert sink.spool.pending() == [] and sink.replayed == 3
    assert sink.api.received[0]["event_ts"].startswith("2026-09-23T10:00:00")   # frame time survives


def test_lost_reply_is_not_stored_twice(sink):
    sink.api.lose_next_reply = True            # the API stores the batch but the worker times out
    sink._queue.append(sighting("GJ05CD1000"))
    sink.flush()
    assert sink.spooled == 1                   # so the worker keeps it...
    sink._down_until = 0.0
    sink.flush()                               # ...and replays it with the same batch id
    assert [s["plate_text"] for s in sink.api.received] == ["GJ05CD1000"]
    assert sink.spool.pending() == []


def test_sightings_carry_their_read_count(sink):
    class R:                                   # a harvested track, as the worker hands it over
        ts, plate_norm, ocr_conf, det_conf, vehicle_type, vehicle_color = 1.79e9, "GJ05CD1000", 0.9, 0.8, None, None
        bbox, track_id, count, seen_at, agreement = (0, 0, 10, 5), "t", 1, 1.79e9, 1.0
    sink.add("CAM-1", R, None)
    sink.flush()
    assert sink.api.received[0]["reads"] == 1 and sink.api.received[0]["first_read_at"].startswith("2026-09")
    assert sink.api.received[0]["agreement"] == 1.0     # G3: the vote's agreement travels with the read count


def test_local_alert_during_outage_uses_cached_watchlist(sink, tmp_path):
    sink.refresh_watchlist()
    sink.api.up = False
    sink._queue += [sighting("GJ01AB1284"), sighting("MH12ZZ9999")]   # one OCR slip from the stolen car
    sink.flush()
    assert sink.local_alerts == 1
    hit = json.loads(sink.local_alerts_path.read_text(encoding="utf-8").strip())
    assert hit["watch_plate"] == "GJ01AB1234" and hit["exact"] is False and hit["severity"] == "high"
    assert "subject_name" not in hit and "reason" not in hit


def test_local_alerts_respect_the_api_cooldown(sink):
    sink.refresh_watchlist()
    sink.api.up = False
    for i in range(4):                         # the same stolen car read four times in a minute
        sink._queue.append(sighting("GJ01AB1234", i))
        sink.flush()
    assert sink.local_alerts == 1 and sink.spooled == 4


def test_watchlist_copy_survives_a_restart_during_outage(sink):
    sink.refresh_watchlist()
    sink.api.up = False
    again = ApiSink()                          # same data dir, API unreachable
    assert again.watchlist.match("GJ01AB1234") is not None


def test_malformed_batch_is_set_aside_not_retried_forever(sink):
    sink.api.status = 422
    sink._queue.append(sighting("GJ05CD1000"))
    sink.flush()
    assert sink.failed == 1 and sink.spool.pending() == []


def test_auth_failure_is_kept_for_later(sink):
    sink.api.status = 401                      # e.g. ingest key rotated; fix the key and it replays
    sink._queue.append(sighting("GJ05CD1000"))
    sink.flush()
    assert sink.spooled == 1 and len(sink.spool.pending()) == 1


def test_spool_is_bounded(tmp_path):
    sp = Spool(tmp_path, max_mb=0.01)          # ~10 kB
    for i in range(50):
        sp.put("sightings", [sighting(f"GJ05CD{1000 + i}")])
    assert sum(f.stat().st_size for f in sp.pending()) <= 10 * 1024 + 400
    assert sp.dropped_rows > 0
    kind, _, batch = sp.read(sp.pending()[-1])
    assert kind == "sightings" and batch[0]["plate_text"] == "GJ05CD1049"   # newest kept


def test_edit_rule_matches_the_api():
    assert edits_within("GJ01AB1234", "GJ01AB1284", 1)
    assert not edits_within("GJ01AB1234", "GJ01AB8284", 1)
    assert not edits_within("GJ01AB1234", "GJ01AB123", 1)            # length must match, as in SQL
    assert edits_within("GJ01AB1234", "GJ01AB2134", 2)


def test_two_workers_on_one_machine_have_their_own_spools(tmp_path, monkeypatch):
    """The plate worker and the counts worker replaying one folder took each other's files mid-read."""
    monkeypatch.setenv("SPOOL_DIR", str(tmp_path / "spool"))
    config.get_settings.cache_clear()
    try:
        a, b = ApiSink("plates-1"), ApiSink("counts-1")
        assert a.spool.root != b.spool.root
        assert a.spool.root.parent == b.spool.root.parent == tmp_path / "spool"
        assert a.local_alerts_path != b.local_alerts_path and a.watchlist.path != b.watchlist.path
    finally:
        config.get_settings.cache_clear()


def test_reject_tolerates_a_file_another_process_already_took(tmp_path):
    s = Spool(tmp_path / "s", 1)
    s.put("sightings", [{"plate_text": "GJ99AB1234"}])
    path = s.pending()[0]
    path.unlink()                      # the other worker rejected or replayed it first
    s.reject(path)                     # must not raise: the process would have died with the flush
    assert s.pending() == []
