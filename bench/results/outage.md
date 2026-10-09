# Backhaul outage: store-and-forward and local alerts

Measured 24 Sep 2026, 00:00–00:03 IST, on the GTX 1650 Ti laptop: one worker on one camera (AMD-AMC-001, synthetic
feed, HW_DECODE off, object detection off) and the API on the same machine. The API process was stopped at 00:01:04
and restarted at 00:02:31 IST (about 87 s down); the worker kept running. Worker log and local-alert file were kept;
sightings and alerts were read back from the database.

| What | Result |
|---|---|
| Sightings produced while the API was down | 21, all written to the worker's disk spool |
| Sightings lost | 0 |
| Replay | all 21 replayed at 00:02:53, oldest first, in 0.5 s, on the worker's first retry after the API returned (backoff had reached 30 s: 2, 4, 8, 16, 30 s) |
| Frame times after replay | unchanged: stored `event_ts` is the time the vehicle was seen; ingest lag of the replayed rows 2–84 s |
| Local alerts during the outage | 20, in the worker log and `data/local-alerts.jsonl`, from the cached watchlist (exact and one-character matches) |
| Control-room alerts on replay | raised with the original sighting time (79–84 s late); others were within the 120 s per-entry cooldown of alerts raised just before the outage |

Conditions and what changed since: this ran on the 24 Sep worker before two additions, each unit-tested since
(`services/analytics/tests/test_spool.py`): batch ids, so a batch the API stored but whose reply was lost is not stored
twice on replay; and the API's 120 s cooldown applied to local alerts too (the 20 local alerts above include repeats of the
same plate). One camera and one outage: this shows the mechanism end to end, not a durability figure; the spool is bounded
(512 MiB by default, oldest batches dropped first with a warning).
