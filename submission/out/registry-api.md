# Sentinel — Unified CCTV Integration Platform: API reference

Version 0.1.0 · generated 24 Sep 2026 02:25 IST from the running API. The full machine-readable contract (every parameter and schema) is `registry-api.json` (OpenAPI 3); a running instance also serves it interactively at `/docs`.

## Examples

Sign in, then send the token as `Authorization: Bearer <token>` (all endpoints except sign-in, `/healthz` and `/ingest/*`).

```
POST /auth/login            {"username": "admin", "password": "..."}   -> {"access_token": "...", "user": {...}}
GET  /cameras?department=GSRTC&health=online&limit=100               -> {"total": 2, "items": [{camera_code, name, department_code, district, lat, lon, codec, resolution, health, anpr_viable, ...}]}
POST /cameras/sync-catalogue?url=http://<host>/api/ingest&dry_run=true -> {"rows": [{camera_code, department_code, district, lat, lon, coord_source, warnings}], ...}  (nothing written)
POST /cameras/import         multipart CSV (template: GET /cameras/template.csv) -> {"inserted": n, "updated": n, "errors": [{line, camera_code, error}]}
GET  /gis/clusters?zoom=7    -> {"total": 80000, "clusters": [{lat, lon, cameras, online, offline, anpr}]}   (state view)
GET  /gis/cameras.geojson?bbox=72.50,22.98,72.62,23.08 -> GeoJSON FeatureCollection of the cameras in view
GET  /reports/gaps           -> {"districts": [...], "findings": [{district, finding, severity}]}
GET  /sightings/movement/GJ01AB1234?purpose=FIR%20123 -> {"timeline": [...], "visits": [{n, camera_code, first_ts, last_ts, hop: {distance_m, travel_s, speed_kmh, implausible}}], "route": {...}}
```

Scope: a department or district officer sees and writes only their own cameras (enforced in the query layer and on
write paths). Every plate search and movement query is written to the audit trail with its stated purpose.

## Registry: cameras (Model 1)

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/cameras` | Search the registry: text, department, district, health, ANPR suitability; paged | token |
| POST | `/cameras` | Register one camera (manual entry); department-scoped users only in their own department | token |
| GET | `/cameras/export.csv` | The registry as CSV (the Model 1 sample dataset) | token |
| POST | `/cameras/import` | Bulk onboarding | token |
| POST | `/cameras/sync-catalogue` | API onboarding: read someone else's camera catalogue and register every camera | token |
| GET | `/cameras/template.csv` | The bulk-import CSV template with every column | token |
| GET | `/cameras/{code}` | One camera's registry record | token |
| PATCH | `/cameras/{code}` | Update a camera's metadata or analytics setting (audited) | token |
| DELETE | `/cameras/{code}` | Remove a camera from the registry (administrators) | token |
| GET | `/cameras/{code}/health` | A camera's health-check history | token |

## Registry: intrusion zones

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/cameras/{code}/zones` | A camera's intrusion zones | token |
| PUT | `/cameras/{code}/zones` | Replace a camera's intrusion zones (polygons, classes, dwell, armed hours; audited) | token |

## GIS: map layers

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/gis/cameras.geojson` | Cameras as GeoJSON; `bbox` (minLon,minLat,maxLon,maxLat) restricts to the visible map | token |
| GET | `/gis/clusters` | Cameras counted per grid cell (about four cells per map tile), with health totals | token |
| GET | `/gis/districts` | Coverage per district: cameras, online, ANPR, departments, uptime | token |
| GET | `/gis/nearby` | Cameras within a radius, nearest first | token |

## Onboarding by stream URL

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/onboard/probe` | Probe a stream URL without registering it: codec, resolution, time to first frame | token |
| POST | `/onboard/stream` | Onboard a camera from a stream URL: probe, relay, register (credentials stay server-side) | token |
| DELETE | `/onboard/stream/{code}` | Remove a camera's relay | token |

## Reports and audit

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/audit` | The append-only audit trail, filterable by action (auditor, supervisor, admin) | token |
| GET | `/reports/departments` | Per-department inventory: cameras, online, ANPR, districts, vendors, retention | token |
| GET | `/reports/fleet` | Fleet totals by health, ANPR suitability and analytics | token |
| GET | `/reports/gaps` | Coverage gap analysis: where the network is thin, blind, or offline | token |
| GET | `/reports/objects` | Vehicle and person counts from the analytics workers | token |
| GET | `/reports/uptime` | Per-camera uptime over a window | token |

## Plate sightings and movement

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/sightings` | Plate sightings by plate (substring), camera and time window (plate searches are audited) | token |
| GET | `/sightings/movement/{plate}` | Full timestamped, location-wise movement history for a registration number | token |
| GET | `/sightings/recent` | The latest plate sightings | token |
| GET | `/sightings/stats` | Sightings, distinct plates and busiest cameras over a window | token |

## Watchlist

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/watchlist` | Active watchlist entries, filterable by kind and plate or name | token |
| POST | `/watchlist` | Add a watchlist entry; the reply says whether the plate was already seen in the last 24 h | token |
| GET | `/watchlist/check/{plate}` | Is this plate on any active list? Exact and fuzzy | token |
| POST | `/watchlist/import` | CSV columns: kind, plate, subject_name, severity, source, source_ref, reason | token |
| GET | `/watchlist/sources` | Government-database adapters and their status (mock, awaiting access) | token |
| POST | `/watchlist/sync/{source}` | Pull the current list from a government-database adapter (VAHAN, eGujCop, ...) | token |
| DELETE | `/watchlist/{entry_id}` | Deactivate a watchlist entry (audited) | token |

## Alerts

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/alerts` | Alerts in the caller's scope, newest first; unacknowledged ones in priority order (severity, then time) | token |
| GET | `/alerts/summary` | Counts of unacknowledged, acknowledged and last-24-hour alerts | token |
| POST | `/alerts/{alert_id}/ack` | Acknowledge an alert (audited) | token |
| POST | `/alerts/{alert_id}/close` | Close an alert or mark it a false positive, with a disposition (audited) | token |

## Sign-in

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/auth/login` | Sign in with username and password; returns a bearer token and the user's role and permissions | public |
| GET | `/auth/me` | The signed-in user, role and scope | token |
| POST | `/auth/token` | OAuth2 password flow, so the Swagger UI 'Authorize' button works | public |

## Analytics workers (ingest key, not user tokens)

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/ingest/cameras` | Cameras an analytics worker may consume: analytics enabled and a stream URL present | ingest key |
| POST | `/ingest/events` | Non-plate detections | ingest key |
| POST | `/ingest/heartbeat` | Worker liveness: marks its cameras as seen and reports observed analytics fps | ingest key |
| POST | `/ingest/sightings` | Plate sightings from a worker; each is matched against the watchlist and may raise an alert | ingest key |
| GET | `/ingest/watchlist` | The edge copy of the active vehicle watchlist, so a worker cut off from the API can still flag a hit locally | ingest key |

## Service

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/healthz` | Liveness and fleet summary | public |

