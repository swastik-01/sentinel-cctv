# The core at statewide size

Measured 2026-09-24 02:09 India Standard Time on DESKTOP-R2I8CQL by `bench/core_scale.py`: one API process
(uvicorn, one worker) and PostgreSQL in Docker Desktop on the same GTX 1650 Ti laptop as everything else; a separate
database seeded with 80,000 cameras (8,000 ANPR) across 33 districts, 3,000,060 sightings
over 30 days drawn from 300,000 plates, 100,100 watchlist entries (1154 MB). Seeding took
3 s (cameras), 96 s (sightings), 16 s (watchlist). Times are
round trips from a Python client on the same machine, admin user (statewide scope).

| Request | Runs | Median ms | Max ms | Response MB |
|---|---|---|---|---|
| cameras page (100) | 10 | 46 | 76 | 0.07 |
| cameras, one department | 10 | 18 | 24 | 0.08 |
| map, whole registry as one GeoJSON (before) | 3 | 6052 | 6265 | 45.37 |
| map, state view: clusters (zoom 7) | 5 | 161 | 202 | 0.00 |
| map, district view: clusters (zoom 10) | 5 | 20 | 22 | 0.01 |
| map, street view: cameras in view (zoom 13) | 5 | 25 | 32 | 0.11 |
| gap-analysis report | 3 | 127 | 138 | 0.01 |
| fleet report | 3 | 150 | 151 | 0.00 |
| movement history (GJ01TR0001, 30 days, fuzzy) | 10 | 337 | 901 | 0.06 |
| watchlist check (100k entries) | 10 | 45 | 54 | 0.00 |

**Ingest**: 8 concurrent clients posting batches of 50 sightings for 60.5 s, each read
matched against the 100,000-entry watchlist in the same request: **706 sightings/s** sustained (42,750 stored, 16 alerts raised), request median
516 ms, p95 718 ms. The capacity model's statewide average is 556 sightings/s.

One laptop, one API process, database on the same disk: a floor for the core, not a sizing. Above 2,000 cameras the
control-room map switches from the whole registry to clusters per grid cell, and to the cameras in view once zoomed in.
