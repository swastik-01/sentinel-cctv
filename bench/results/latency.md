# Alert latency: first valid read to alert

Window 2026-09-24T01:00:13 to 2026-09-24T01:15:14 (IST), measured by `scripts/latency_report.py` on 2026-09-24.
Conditions: 4 cameras (AMD-POL-001, AMD-AMC-001, AMD-TRAF-001, AMD-TRAF-002), one worker and the API on the same GTX 1650 Ti laptop, HW_DECODE=auto, object detection on, ~4.5 analysed fps per camera; watchlist = the simulator's test plates plus GJ13LU9863 on the stock camera

| Alerts | Median s | p95 s | Max s | Cameras |
|---|---|---|---|---|
| 31 | 1.06 | 1.94 | 2.00 | 3 |

Measured from the worker's wall clock at the first valid read of the vehicle's track to the API's clock
when the alert row exists (same host). It includes the track confirmation hold (the tracker waits up to
~1 s, or 3 reads, to vote across reads), the 1 s batch flush and the API's matching. It does not include
camera-to-worker transport or the browser's display of the alert.
Excluded: 6 alert(s) that were retrospective, replayed from the outage spool, or from before latency was recorded.
