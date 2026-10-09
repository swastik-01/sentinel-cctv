# Sentinel — Unified CCTV Integration Platform

Entry for the **Gujarat Police Innovation Challenge 2026**. A vendor-neutral
platform, built on open-source components (with licence caveats: the AGPL-3.0 detectors, whose
permissive replacement is planned for the pilot and not trained; Hippocratic-licensed react-leaflet; and PyAV, BSD-3,
whose wheels bundle a GPL build of FFmpeg, used for decoding only: see Plan for Scale §3.4 and the HLD's stack table), that brings Gujarat's ~80,000 government cameras across 26
departments onto one registry, one map, one viewer and one analytics layer —
without replacing any department's existing infrastructure.

**Architecture:** Model 2 (Unified Viewing + Selective Analytics) on Model 1 (Centralised
Registry + GIS), the mandatory foundation; on the submission form, "Model 2" with Model 1
confirmed. It connects directly to department systems over RTSP, with no federation middleware;
ONVIF discovery and vendor SDK adapters for VMS that will not re-stream are on the roadmap
(designed, not built).

## Open source: for other states and departments

Sentinel is released under the **Apache License 2.0** ([`LICENSE`](LICENSE)). Any state government, police force,
department, municipal body or integrator may **use it entirely**: deploy it as it is, change it, and run it on their
own cameras. They may also **take it as a reference**: reuse its registry schema, the relay pattern (RTSP in, browser
video out, no change to the cameras), the ANPR and watchlist pipeline, the role and audit model, or its documents (HLD,
Plan for Scale, privacy position) for their own tender or build. Nothing here is tied to Gujarat except the seed data
(districts and departments) and the record systems it is written to connect to (VAHAN, SARTHI, eGujCop/CCTNS, AFIS,
NAFIS), which other states run as well.

Before deploying, read [`NOTICE`](NOTICE): the bundled plate and object detectors (Ultralytics YOLO) are AGPL-3.0, and
the VAHAN and eGujCop connectors are mock adapters until a department grants access. Accuracy figures in the documents
were measured on one laptop with the stated footage; measure again on your own cameras.

This public copy leaves out the competition's private material: the organisers' sandbox address and footage
screenshots (in the submitted decks), the submission form answers, and the team's internal finale notes. Some
documents still mention those files by name.

## The problem we built it for

**Gujarat Police Innovation Challenge 2026 ("SENTINEL")**, Government of Gujarat, Home Department: State Crime
Records Bureau (SCRB), with i-Hub Gujarat. Theme: *Integrated Video Management & Analytics Platform*. The organisers'
own wording is in [`docs/official-problem-statement.md`](docs/official-problem-statement.md).

- **The situation.** 26 government departments run their own CCTV systems: analog and IP cameras from different
  vendors, some recording to the cloud and some locally, kept for anywhere from 7 to 15 days. About 80,000 cameras
  statewide, and none of them can be searched or watched together.
- **What was asked.** A secure, scalable, interoperable and cost-effective platform that reuses existing
  infrastructure. It must bring every camera onto **one registry and map** (Model 1, mandatory), give **one place to
  watch any camera and run analytics on the ones that need it** (Model 2), and link to the state's records: VAHAN,
  SARTHI, eGujCop (CCTNS), AFIS and NAFIS.
- **What Sentinel does.** Every camera is registered with its department, location, maintenance and ageing details,
  and gap analysis by district. Any camera can be watched from one video wall in the browser. Number plates are read
  (ANPR) and matched against the watchlist, with an alert in seconds. A vehicle's movement can be searched across
  cameras. Vehicles and people are counted, and intrusion zones raise alerts. People check the plate reads blind on a
  review page. Access is role-based and audited. There is **no facial recognition**, by design.

## Where else it can be used

Everything below runs on what is already built: the registry, the relay, the video wall, ANPR with watchlists,
vehicle and person counts, intrusion zones, alerts and the audit log. Each is a possible use, not one we have deployed
or measured.

**Other departments** (the challenge's 26 run cameras of their own):

| Department | What Sentinel gives them |
|---|---|
| **Home / Police** (traffic, law and order) | Stolen and wanted vehicles found by ANPR across every camera; a vehicle's route rebuilt for an investigation; one wall for every police control room |
| **Transport / RTO** | Watchlists for unpaid challans, expired fitness or permits and unregistered vehicles; cameras at offices, test tracks and check-posts on the same map |
| **Food & Civil Supplies** | Godowns and PDS shops: intrusion zones outside working hours; truck arrivals and departures logged by plate (diversion of ration stock) |
| **GSRTC / Bus depots** | Depot entry and exit by plate; crowd counts on platforms; each depot sees only its own cameras |
| **Urban Development / Municipal Corporations** | City cameras on one map; pedestrian and vehicle counts for planning; illegal dumping and encroachment zones |
| **Health** | Hospital gates and ambulance bays: zones that must stay clear, ambulance movement by plate |
| **Panchayat & Rural Development** | Village and taluka cameras registered with their gaps (where coverage is missing), viewable from the district |
| **Mines & Geology, Forest** | Trucks at check-posts by plate (illegal mining, timber); intrusion zones on protected land |
| **Education** | Exam centres and strong rooms: intrusion zones and a recorded, audited view |
| **Revenue / Disaster Management** | Live views of flood-prone and evacuation points from one wall; crowd counts at relief camps |
| **Ports & Industries, Energy** | Gates and perimeters of plants and substations: intrusion zones and vehicle logs |

**Other real-world uses:**

- **Smart-city and traffic management.** Vehicle counts by camera and hour, congestion at junctions, enforcement of
  restricted lanes.
- **Toll plazas, highway check-posts and borders.** Plate logs to match against permits and watchlists across states.
- **Large events and pilgrimages** (Ambaji, Somnath, Dwarka, Navratri). Crowd counts per zone, alerts when an area
  fills, and one wall for every camera at the venue.
- **Campuses, ports, airports and industrial estates.** Gate ANPR with allow- and deny-lists, perimeter zones after
  hours, one audited view for security.
- **Parking and logistics.** Entry and exit by plate, dwell time, fleet movement between depots.
- **Missing persons and vehicles.** A vehicle seen anywhere in the last 24 hours is found the moment it is listed (a
  retrospective alert), and its route is shown on the map.
- **Any organisation with mixed, ageing cameras.** It works with the RTSP streams cameras already have: no new
  cameras, no vendor lock-in, and video stays where it is recorded.

## Components

| Path | What it is |
|---|---|
| `infra/` | Docker stack: PostGIS, Valkey, MediaMTX, and the DB schema |
| `feedsim/` | Sandbox-compatible camera simulator: 12 synthetic plate clips, 2 stock traffic clips (Pexels, filmed on a Mumbai road) with every plate replaced by a synthetic registration (`realclip.py`), RTSP publisher, catalogue API |
| `services/api/` | FastAPI: registry, GIS, onboarding, search and journey view, watchlist (adding a plate checks the last 24 h of sightings), alerts, intrusion zones, evidence crops behind login, plate review, plate-reading quality per camera, RBAC, audit |
| `services/analytics/` | GPU worker: RTSP (hardware decode where available) -> plate detection -> OCR -> per-character vote -> sightings; vehicle/person detection -> counts, type/colour on sightings, intrusion zones; spools to disk and matches a cached watchlist while the API is unreachable. `counts.py`: the counts-only worker, vehicle/person counts and intrusion zones on every other camera at once, from keyframes only (PyAV), beside the plate worker |
| `web/` | React control room: map, video wall with zone editor, vehicle search with journey view, alerts in priority order, health with plate-reading quality by camera, registry, watchlist, plate review, audit |
| `scripts/` | End-to-end smoke test, security checks, demo prep, reports (detections, registry, ANPR accuracy, alert latency), sandbox checklist; for the finale's two laptops and their secrets `lan.ps1`, `db_backup.ps1`, `db_restore.ps1`, `set_passwords.py`, `rotate_secrets.py`, `set_analytics.py`, `onboard_urls.py` (one line each under "Since the submission") |
| `bench/` | Measurements: per-stream cost (`sentinel-bench`), the 80k-camera capacity model (`capacity.py`), the core at 80,000 cameras (`core_scale.py`), watchlist matcher, decode A/B summary, plate choice, zone replay, the counts-only worker's capacity (`counts_capacity.py`) and its sandbox run (`counts_sandbox.py`), the G3 gate (`g3_check.py`, `g3_wiring.py`), the not-a-plate rule live (`plate_gate_live.py`), whether the sandbox footage loops (`sandbox_loop.py`); results in `bench/results/` |
| `docs/` | HLD, Plan for Scale, privacy (DPDP) position, finale runbook, generated diagrams |
| `submission/` | Hackathon submission pack — deck, PDFs, demo video, detection report — and the scripts that build them |

## Quick start

```bash
cp .env.example .env                        # then edit secrets
docker compose up -d postgres valkey mediamtx
docker compose run --rm feedsim-synth        # one-off: generate synthetic clips (~5 min)
uv run --no-sync python feedsim/realclip.py  # one-off, on the host (GPU): the two stock-footage cameras (~10 min)
docker compose up -d feedsim-publisher feedsim-catalogue
```

Then, on the host:

```bash
uv sync --all-packages                       # always all packages: --package uninstalls the siblings
uv run --no-sync uvicorn sentinel_api.main:app --reload --port 8000   # API  -> :8000/docs
cd web && npm install && npm run dev                                   # UI   -> :5173
uv run --no-sync python scripts/smoke.py                              # 34 end-to-end checks
uv run --no-sync python scripts/smoke.py --skip-fleet                 # the same, once non-simulator cameras are registered
uv run --no-sync python scripts/security_checks.py                    # 23 checks that refusals hold; the 2 secrets checks fail on a machine still on the example values (below)
uv run --no-sync pytest                                               # 379 unit tests
uv run --no-sync python scripts/edge_checks.py                        # 189 edge cases: hostile input on every endpoint (never a 5xx), registry, CSV and alert limits, scope, live events, concurrency, the relay's publish rule
node scripts/ui_checks.mjs                                            # 111 control-room checks in headless Chrome: every page for every role, the flows, live push
node scripts/shot.mjs                                                              # headless screenshots of every page
```

The scripts read `ADMIN_PASSWORD` (smoke also `INGEST_KEY`) from the shell environment, not from
`.env`. Smoke writes watchlist entries, sightings, alerts and audit rows to the live database;
`--skip-fleet` reports its 3 simulator-fleet checks as SKIP and the count stays 34.
`security_checks.py` covers evidence crops (4), the camera-quality report (1), department write scope (4),
ingest integrity (3), plate review (3), the live secrets (2: `.env` differs from `.env.example` on the JWT secret,
ingest key, publisher credential and database password, and `ADMIN_PASSWORD` is not the dev default; both fail on any
machine still on the example values, which is the point: `scripts/rotate_secrets.py` and `scripts/set_passwords.py`
fix that, and this laptop passes since 8 Oct) and
what the LAN can reach (6: Postgres, Valkey, the relay's control API and metrics, the simulator's outage switch on
8010, and an anonymous publish). The LAN checks need a network interface, else they print SKIP.

Analytics worker (needs an NVIDIA GPU for useful throughput; falls back to CPU):

```bash
uv run --no-sync sentinel-worker                                  # torch (CUDA 12.4), ultralytics, fast-plate-ocr
uv run --no-sync sentinel-bench --streams 1,2,4,8                 # per-stream cost -> bench/results/bench_<stamp>.json
OBJECT_DETECTION=false uv run --no-sync sentinel-worker           # plate-only worker, as before counts existed
HW_DECODE=off uv run --no-sync sentinel-worker                    # software decode; the default, auto, asks OpenCV for a D3D11 hardware decoder (on the dev laptop, the Intel iGPU's) and falls back per camera
TRACK_LOG=tracks.jsonl uv run --no-sync sentinel-worker           # evaluation only: every track with all its reads, for bench/plate_choice.py
MAX_LETTERS_FROM_DIGITS=99 uv run --no-sync sentinel-worker       # turns the not-a-plate rule off (default 1)
uv run --no-sync python -m sentinel_analytics.worker              # the same worker without the .exe launcher (the antivirus held such a launcher on 7 Oct)
COUNTS_EXCLUDE=CAM06,CAM07 uv run --no-sync python -m sentinel_analytics.counts   # counts-only worker on every other analytics camera, keyframes only (sentinel-counts is the same)
RELAY_HOST=192.168.1.10 uv run --no-sync python -m sentinel_analytics.worker      # a worker on another machine than the relay (.env.b.example)
```

**Two profiles, no rotation.** Since 7 Oct the analytics run as two workers side by side. The plate worker,
unchanged, takes the few cameras whose plates are readable (on the laptop 4 streams at about 4.5 analysed fps with
object detection, or 8 at 2.9 with `OBJECT_DETECTION=false`: `bench/results/decode.md`). The counts-only worker
(`python -m sentinel_analytics.counts`, `services/analytics/sentinel_analytics/counts.py`) takes every other analytics
camera at once: vehicle and person counts and intrusion zones from keyframes only, which FFmpeg (PyAV, `skip_frame`)
decodes without the frames between them. A camera whose keyframes are more than 4 s apart is decoded in full (the
sandbox's CAM07, CAM17 and CAM18 keyframe every 10–15 s), and each count row says which (`detail.profile`:
`keyframes` or `every-frame`). Settings: `COUNTS_FPS` (1.0), `COUNTS_MAX_STREAMS` (60), `COUNTS_EXCLUDE` (the plate
workers' cameras, so no zone alerts twice), `COUNTS_BATCH` (16), `COUNTS_WORKER_ID`. Measured on one laptop with no
plate worker running and the relay's CPU excluded: 40 streams at 0.78 frame/s per stream (median) on 2.46 CPU cores
and 13% GPU; 50 saturates (`bench/results/counts_capacity.md`); on 7 sandbox cameras 14–34 frames counted per minute
each while the sandbox dropped every session about every 45 s (`counts_sandbox.md`). This is the Plan for Scale's tier
B keyframe profile, now built; its 250-streams-per-node figure stays an assumption. Not measured: a plate worker and
the counts worker on one machine together, and count accuracy (per-frame COCO detections; no auto-rickshaw class;
night misses). A worker on another machine than the relay sets `RELAY_HOST`: the registry stores
`rtsp://localhost:8554/<code>`, and the worker rewrites localhost to that address (`.env.b.example` is laptop B's
settings file).

A read is dropped as not a plate when two or more of its letters had to be made from digits to fit a
plate layout (how a hoarding's phone number became plate-like on the sandbox); the worker logs per
camera how many reads it dropped, as counts only (HLD §7.1, `bench/results/plate_gate_confirm.md`).

When the API cannot take a batch (link or API down, 5xx), the worker writes it to `data/spool`
(capped by `SPOOL_MAX_MB`, 512 by default; past the cap the oldest batches are dropped, with a
warning) and replays it oldest first, with the original frame times, once the API answers; batch
ids make a replay after a lost reply harmless. Meanwhile it matches reads against its copy of the
active vehicle watchlist (plate, kind and severity only, refreshed every 60 s) and records hits in
its log and `data/local-alerts.jsonl`. The control-room alert is raised on replay, with the original
sighting time. Tested on 24 Sep on one camera: API down ~87 s, 21 sightings spooled, all 21 replayed,
20 local alerts recorded. A worker started while the API is down waits for it (`STARTUP_WAIT_S`, 300 s
by default, retrying every 2 s and backing off to 30 s) instead of exiting. A camera stream that keeps
dropping is retried with a backoff from 2 s to 30 s that starts again from 2 s only after 60 s of healthy
streaming, so a source that drops every session a few seconds in (the sandbox, 25-26 Sep) is not hammered.

Models live in `models/` (gitignored): the plate detector is fetched from Hugging Face on first run,
and the COCO vehicle/person model (`yolo11n.pt`) from the Ultralytics release assets. If neither can
be fetched the worker still runs; without the second model it writes no counts and says so.

```bash
uv run --no-sync python submission/build/objects_frame.py         # what the worker sees in one frame
```

Sign in as `admin` (password from `.env`), then **Registry -> Sync from catalogue API** to onboard
the simulated fleet (**Preview (dry run)** first shows the department, district and coordinates
each camera would get, and writes nothing), or **Add camera by stream URL** to onboard any RTSP feed
in a couple of seconds (probed, relayed through MediaMTX, registered; credentials never reach
browsers or workers).

**Plate review** (`/review`; administrators, supervisors and auditors) is where people check
Sentinel's stored reads against their evidence crops. *Blind check* shows only the crop: the reviewer
types the plate (`?` unreadable, `-` not a plate), then sees Sentinel's read, and the server grades it.
The reading is kept exactly as typed (spaces, punctuation and case aside), and a reading with no letters
is graded not a plate.
*Quick verify* shows the read and its confidence to confirm or correct. *Results* keeps the two apart,
per camera and by confidence band, with agreement where two people checked the same plate blind.
Every review is audited without the plate text. Do blind checks from an auditor account (a supervisor
can look a read up in Vehicle Search first). `bench/sandbox_eye.py score --from-db` writes the totals
to `bench/results/sandbox_review.md`.

**Plate-reading quality by camera** (Health & Reports; `GET /reports/camera-quality`, `reports.read`,
department scope) grades every stored plate capture good, marginal or poor from its crop: size against
published ANPR guidance (characters at least 10 px, plates 100-150 px across), blur, light, contrast and
glare (cut-offs from a damage test on our own stock-footage crops, `bench/results/quality_thresholds.md`),
two-line layout and reader confidence. Captures are graded at ingest; `scripts/quality_backfill.py` grades
older ones. Each camera gets a tier (A reads plates, B marginal, C counts and viewing only) and camera, model
and configuration advice; Vehicle Search shows each sighting's grade. Counts, medians and rates only, no plate
text. The grade describes the camera: on the 120 blind-checked sandbox plates it did not predict a right read,
and the reader's confidence did (`bench/results/capture_quality.md`).

## Since the submission (26 Sep → 8 Oct)

**Confidence marking (G3), adopted 8 Oct.** A stored read below 0.9, or a watchlist alert raised on a one-character
match, is marked "check the crop" in alerts, search, the journey view and the live toast; the Plate review page has a
"Below 0.9, unchecked" filter; each sighting stores `reads` and `agreement` (the vote's weakest position's winning
share). Nothing is suppressed and no alert rule changes. Its pre-registered gate passed (`bench/results/g3_wiring.md`;
the API setting `CONFIDENCE_MARKING=false` restores the 26 Sep behaviour). The band is the review page's: on the 120
blind-checked plates, 69 of 81 at or above 0.9 were exact against 21 of 39 below; no claim is made beyond those 120.
The fine-tuned reader ft1 was scored and not adopted (non-inferior on real plates, no gain: `bench/results/ocr_ft1.md`);
G0, G2, G2b, G4, G5 and G6 were not built; the YOLOX detectors are not trained
(`bench/results/pipeline_gates_results.md`). Every accuracy, capture and latency figure in the pack still describes the
plate pipeline that runs at the finale: the 26 Sep build plus G3's marking.

**Security hardening (8 Oct).** The laptop had run on the repo's example secrets, which anyone who read the public repo
could use from the same network to sign in as admin, fabricate sightings with the ingest key, or publish over a camera.
Now `scripts/rotate_secrets.py` replaces the JWT secret, ingest key, publisher credential and database password with
random ones (`scripts/set_passwords.py` the five seeded users' password, from `NEW_PASSWORD` in the environment), the
API logs an error at every start while any is still an example value, and two security checks fail on any machine
still on the example values (this laptop's were rotated on 8 Oct; all 23 checks, 34 smoke checks and 286 unit tests
passed on the rotated secrets that morning). The ingest key is compared in constant time; sign-ins are rate-limited per address and argon2 runs off the
event loop; a sighting's `event_ts` must carry a timezone and lie within 14 days, a batch holds at most 5,000 rows;
camera codes and stream addresses are validated on every registry write path; `rtsp_url` is masked in `GET /cameras`
and the CSV export; listing a camera's recent sightings, a watchlist check and the registry export are audited;
district-only users are no longer statewide; enum query parameters are validated (422, not 500); the API's access log
(plate searches, tokens in URLs) is off; plate text is masked in the workers' logs; each worker has its own spool
directory. On the LAN, the simulator's control port (8010, whose outage switch has no auth) is bound to 127.0.0.1, a
relay path already being published cannot be taken over (`overridePublisher: no`), and the onboarding card hides the
stream URL (it carries the camera's password) while a screen is projected. `scripts/onboard_urls.py` onboards a CSV of
stream addresses through the relay so credentials never reach the registry (never the Registry page's bulk CSV for
credentialed addresses); `scripts/set_analytics.py --prefix CAM --on` turns analytics on for the finale's cameras in
one go; `detection_report.py` adds a SHA-256 per evidence crop (an integrity check, not a signature).

**Later on 8 Oct.** An evidence crop is served only from its own camera's folder: on Windows a backslash in the file
name had reached another camera's crop while the scope was checked against the first (unit tests and a security check
now cover it). No token travels in a URL any more: the control room fetches crops with the Authorization header, and
the event WebSocket takes its token in its first message. Live events reach a department or district user only for
cameras in their scope. Both workers open a relay on this machine by 127.0.0.1: against a relay listening on IPv4
only, `localhost` failed in both (Docker Desktop answers on both loopbacks and hid it). 309 unit tests.

**8 Oct night: Model 1 and Model 2 gaps, and edge cases.** The registry now keeps each camera's maintenance state
(in service, under maintenance, faulty, decommissioned), a maintenance note, the installation year and the AMC or
warranty expiry, on every write path (API, CSV import, export and template; a catalogue re-sync keeps them) and in the
Registry's Edit dialog, which sends only what changed and can clear a field. Gap analysis adds ageing findings (AMC
expired or ending within 90 days, installed `AGEING_YEARS` (7) or more years ago, under maintenance or faulty, no
installation year), grouped by finding on the Health page; the fleet report counts them; Registry and Map filter by
camera type and maintenance. Alerts take tags (a case number, "intercepted"; any language) and filter by them, and a
scoped user acting on another department's alert gets "not found". `scripts/edge_checks.py` sends hostile values to
every endpoint in the API's OpenAPI document and found these, each a 500 or a wrong answer and each now a 4xx or
right: a NUL character in a path, query or JSON body; `NaN` in a body (the refusal echoed the input, which also
repeated passwords; refusals now say where and why, never the value); a negative `limit`, `offset` or `hours`, or an
`offset` past 64 bits; a time before 1970 on Windows; a malformed catalogue URL; a CSV with a lone carriage return or a
broken quote; a null for a required field in an edit; `%` or `_` in a search, which matched everything.
`scripts/ui_checks.mjs` drives the control room in headless Chrome as each seeded role. It found the Alerts page
wiping its own error message (a stale acknowledge looked like nothing happened) and a phone-width layout whose
sidebar left no room for the page; both fixed. The control room loads each page on first visit and hls.js only when
a tile falls back to HLS; a banner says when the API is not answering. A video tile counts as playing only once a
frame is decoded: a stream that connects but gives no picture (H.264 with B-frames, as internet HLS feeds often are)
falls back to the relay's on-demand preview profile before HLS, and the browser remembers that for a day. A public
internet HLS test stream was onboarded through the relay, read over RTSP and shown on the wall that way. The
simulator's catalogue now answers the control room's browser (CORS), so the simulator's outage buttons appear on the
dev server; a production build looks for the simulator only when `VITE_CATALOGUE_URL` is set. 373 unit tests, 167
edge checks and 98 control-room checks; 34 smoke and 22 of 23 security checks on the native rig (the LAN publish
probe gets no answer there, as before).

**9 Oct: a real broker, NVDEC, internet feeds, concurrency.** Live events were tested end to end on a real broker for the first time: the native test stack's fakeredis counts a subscriber and delivers nothing, so the API ran on Redis 8.10 (RESP3, as Valkey speaks it; redis-py 8 refuses Redis 5). Alerts reached the control room's live feed in scope, and acknowledgements and tags reached other control rooms; with the live link cut, the menu says "reconnecting" and a late Acknowledge gets the 409's explanation. `edge_checks.py` gained these live-event checks, a burst of 300 requests 64 at a time, ten simultaneous acknowledgements of one alert (exactly one wins), four simultaneous imports of the same 20 cameras (no errors, 20 cameras), clearing a camera's district (it had been silently kept), and the relay's publish rule from 127.0.0.2, outside its loopback exemption, which needs no LAN. The request guard now also reads a body sent without a content type, or as `application/*+json`, both of which FastAPI parses as JSON (a NUL had passed that way). The player counts a picture only past Chrome's 2x2 placeholder. Three public internet HLS test streams (one live; one fMP4; two with B-frames) were onboarded through the relay and played on the wall, the B-frame ones through the preview profile; a fourth (Akamai's test stream) fails at its source, its master playlist naming a variant that answers 404. NVDEC was measured: on another laptop's GTX 1650, decode only (9 Oct, `bench/results/nvdec_decode.md`), the NVIDIA decoder took about 740 frames a second of 1080p H.264 at its ceiling (about 29 streams at 25 fps) and about 1,500 of 1080p H.265 with the resize on the GPU, and at 16 real-time 1080p streams cut system CPU from 89% to 31% (H.264, decoded and resized to 640 px) and from 75% to 32% (H.265); the worker does not use NVDEC. `scripts/onboard_sandbox.py` registers cameras without the reviewed locations file, unplaced, department and district inferred from the camera's name. 374 unit tests, 178 edge checks and 107 control-room checks; 34 smoke and 22 of 23 security checks on the native rig.

**9 Oct, later: the organisers' sandbox, reconnected.** Through Sentinel's own URL onboarding, one camera at a time and 10 s apart, consume only: 30 of 30 cameras (one needed a single retry), probe median 1.0 s, H.264 24 and H.265 6, from 960×576 to 2560×1440. In 15 minutes the plate worker stored 32 sightings on CAM06 and CAM07 (20 at confidence 0.9 or above), now waiting in the Plate review page's blind queue; the counts-only worker counted CAM01–CAM05 at 44–56 frames a minute from keyframes; a plate already read, put on the watchlist, raised a retrospective alert at once with its evidence crop. A wall probe that afternoon, while the relay logged heavy trouble on the organisers' side (lost RTP packets, source timeouts), showed 14 of 30 cameras within 40 s; 15 of the 16 without a picture had that trouble logged (`bench/results/sandbox_oct9.md`). The relay's preview transcoder now waits for a clean keyframe on a lossy source and decodes past errors: on the same sandbox cameras it started 8 of 9 times against 6 of 9 (`bench/results/preview_start.md`). The health monitor now probes each upstream host once a round, however many cameras sit behind it. 376 unit tests.

**9 Oct, afternoon: a retrospective alert no longer holds back a live one.** Listing a plate already seen raises a retrospective alert for that earlier pass; it used to count toward the 120 s cooldown, so the vehicle's next pass at the same camera raised nothing. Smoke found it when its random plate fell one character from an earlier run's. The cooldown now ignores retrospective alerts and a new edge check proves it (179); smoke draws again until its plate is clear. The 32 sightings of the 9 Oct sandbox run wait in the Plate review page's blind queue; `bench/sandbox_oct9_review.py` scores them, its rules fixed before the first review. A reviewer can now change a saved reading (a mistyped plate): the change is kept beside the first reading, which stays the blind one and is what every score uses; changes are reported apart. Results list the reviews plate by plate, Sentinel's read beside the reviewer's: their own by default; everyone's on request, after which the crops they had not checked leave their blind queue.

**Two laptops at the finale.** The topology: A runs the database, API, relay, control room
and the plate worker on the fixed plate group (also listed in `COUNTS_EXCLUDE`); B runs the counts-only worker on every
other camera and the operator console, and is the hot spare. Nothing rotates during the slot. `scripts/lan.ps1` writes
A's LAN address into `.env` (`WEBRTC_HOST`, `CORS_ORIGIN_REGEX`) and restarts the relay and API; without it a browser
on B waits 15 s per tile, falls back to HLS, and cannot sign in. `scripts/db_backup.ps1 -Dest <USB stick> -Loop 600`
dumps the database and copies the crops every 10 minutes; `scripts/db_restore.ps1 -Source <USB stick>` restores on B,
after which the relay rebuilds every camera path from `camera_sources` within about 20 s. `.env.b.example` is B's
settings file. Also since the 7 Oct reboot left the core down: Postgres, Valkey and MediaMTX restart with Docker
(`restart: unless-stopped`), the MediaMTX image is pinned by digest, `scripts/api.ps1` waits for Postgres and runs
`python -m uvicorn` without an access log, and `demo_prep.py` refuses to delete sightings on cameras onboarded by
stream address unless `--force`.

## Measurements

The measured numbers the documents quote come from these files, with their conditions, or, for the
checks listed under the table, from the build log (`docs/plan.md`). All were taken on one GTX 1650 Ti laptop. The plates on the stock-footage cameras (AMD-TRAF-001/002) are synthetic
registrations painted onto Pexels video, so none of this is accuracy on real Gujarat plates. That was first measured on the organisers'
sandbox (our 25–26 Sep runs of its replayed footage), checked blind by a team member on the plate review page on 26 Sep: 90 of 120 real
Gujarat plates stored exactly right (75.0%) and 107 within one character (89.2%), almost all on the 2 of 30 sandbox views where
plates are readable (`bench/results/sandbox_review.md`). At Sentinel's confidence 0.9 or above, 69 of 81 were exact
(85.2%); between 0.5 and 0.7, 8 of 18: high-confidence reads can pass and the rest go to a person. The check itself was
tested where the plates are known: on our own cameras the reviewer was right 222 times in 226 (98.2%), and on the stock
clip AMD-TRAF-002 the blind check found Sentinel right on 96.7% against 96.8% from automated ground truth
(`bench/results/review_truth.md`). An earlier check by our AI coding assistant, with the read in view (not blind),
gave 92 of 107 (86.0%): optimistic, since on the crops it judged readable the blind reviewer found 80 exact against its
92. One reviewer so far; a second would settle the 12 disagreements. Our AI assistant's review of the 30
misses puts 13 on the reviewer's reading and 13 on Sentinel's (mostly a dropped character or a misread by the
reader model); it is not a person, so the quoted figure stays 90 of 120 (`bench/results/blind_errors.md`).

| File | Made by | What it says |
|---|---|---|
| `bench/results/bench_20260917_174834.json` | `sentinel-bench` | Per-stream cost with software decode, 17 Sep: 4.8 analysed fps per stream at 1–2 streams; the CPU saturates while the GPU stays under a third busy |
| `bench/results/decode.md` | `sentinel-bench` with `HW_DECODE=off` and `auto`, summarised by `bench/decode_summary.py` | Hardware decode, 24 Sep, two rounds, plate pipeline without object detection: analysed fps per stream 1.93 → 2.88 at 8 streams and 0.91 → 1.34 at 12 (+49% both), unchanged at 4. The D3D11 decoder on this laptop is the Intel integrated GPU's, not NVDEC |
| `bench/results/nvdec_decode.md` | `bench/nvdec_decode.py` (FFmpeg, decode only) | The NVIDIA decoder against software decode on a GTX 1650 laptop, 9 Oct, two rounds: about 740 frames a second of 1080p H.264 at its ceiling, about 1,500 of 1080p H.265 with the resize on the GPU; at 16 real-time 1080p streams system CPU 89% → 31% (H.264) and 75% → 32% (H.265). The worker does not use NVDEC |
| `bench/results/sandbox_oct9.md` | `bench/sandbox_oct9.py` (audit log, stored sightings and counts, `wall_probe.mjs`, the relay's log) | The organisers' sandbox reconnected, 9 Oct: 30 of 30 onboarded, probe median 1.0 s; 32 sightings in 15 minutes on CAM06/CAM07, unread; counts on CAM01–CAM05; one retrospective alert; a wall probe during heavy source trouble showed 14 of 30 within 40 s |
| `bench/results/preview_start.md` | `bench/preview_start.py` | The relay's preview transcoder on lossy sandbox sources, shipped command against the adopted one, alternating, 9 Oct: started 6 of 9 against 8 of 9 |
| `bench/results/matcher.md` | `bench/matcher.py` | Watchlist match per plate read at 100,011 entries: 0.79 ms median one character off, 1.14 ms for a plate not listed; the old Levenshtein scan took 45–56 ms |
| `bench/results/latency.md` | `scripts/latency_report.py` | First valid read at the worker to the alert row in the API, same host clock: median 1.06 s, p95 1.94 s over 31 alerts; 4 cameras, 24 Sep 01:00–01:15 IST. Excludes camera-to-worker transport and browser display |
| `bench/results/anpr_eval_current.md` | `scripts/anpr_eval.py` | Current worker, 10 min on 24 Sep: AMD-TRAF-002 (close view) 96.8% of sightings exact, 91.2% of plates on screen ≥ 1 s read; AMD-TRAF-001 (wide view, not ANPR-viable) 90.2% and 21.7% |
| `bench/results/anpr_eval.md`, `anpr_eval_vote.md` | `scripts/anpr_eval.py` | The same measure for the 23 Sep worker (best single read, ~53 min: 98.7% exact on AMD-TRAF-002, 90.2% on AMD-TRAF-001) and for the vote worker before the repeat-filter change (24 Sep 01:00–01:15) |
| `bench/results/plate_choice.md` | `bench/plate_choice.py` over `TRACK_LOG` files | Character vote against best single read on the same 4,891 tracks: a tie (84.2% and 84.4% exact on the hardware-decode run); the vote is ahead on the wide camera |
| `bench/results/sandbox_review.md` | `bench/sandbox_eye.py score --from-db` | Real Gujarat plates on the organisers' sandbox (our 25–26 Sep runs), checked blind by a team member on the plate review page, 26 Sep 12:28–13:02 IST: 144 of 145 stored sightings; 24 a hoarding (not a plate); of 120 plates 90 exact (75.0%), 107 within one character (89.2%), 13 wrong, none unreadable. CAM06 71 of 92, CAM07 19 of 27, CAM12 0 of 1. By OCR confidence: ≥ 0.9 69 of 81 exact (85.2%), 79 within one; 0.7–0.9 13 of 20; 0.5–0.7 8 of 18; 0.35–0.5 0 of 1. Precision only |
| `bench/results/review_truth.md` | `bench/review_truth.py` | The blind check tested on our own cameras, where the plates are known: 226 reviews, reviewer right 222 times (98.2%); of 41 graded one-off or wrong, 37 were Sentinel's error and 4 the reviewer's typing slip; AMD-TRAF-002 96.7% by the blind check against 96.8% automated |
| `bench/results/sandbox_eye.md` | `bench/sandbox_eye.py score` | The earlier check, not blind: our AI coding assistant against each crop with the stored read in view, 92 of 107 exact (86.0%) after leaving 14 crops out as unreadable (25 Sep evening run 55 of 66, 26 Sep morning run 37 of 41). Optimistic against the blind check (80 exact, not 92, on the crops it judged readable); kept for the record, quoted only as the earlier check, and the file says so |
| `bench/results/sandbox_daynight.md`, `sandbox_plates_day.md` | `bench/sandbox_daynight.py`, `bench/sandbox_plates.py` | Two runs on the same 8 sandbox cameras, the 25 Sep evening run and the 26 Sep morning run: 4.6 and 4.1 plates stored per 1,000 analysed frames; the toll-plaza camera (CAM12) stored none in the morning run's 1,925 frames. The sandbox replays fixed clips, each camera's from one time of day and looping, so the runs are two samples of the same footage, not day against night (the file keeps its old name). Blind check by run: 25 Sep evening (20:07–23:48, all 30 cameras; the government video and report cover it) 54 of 75 exact, 26 Sep morning (06:51–07:58, 8 cameras) 36 of 45 |
| `bench/results/capture_quality.md`, `quality_thresholds.md` | `bench/quality_validate.py`, `bench/quality_thresholds.py` | Plate-reading quality: 8,635 captures graded; per camera tier and advice (sandbox: CAM06, CAM07 B; the rest C). Checked against the blind reviews: the grade does not predict a right read on real plates (good 53/66, marginal 29/44, poor 8/10 exact); the reader's low confidence does (1/6). The blur, light and contrast cut-offs: where fewer than 80% of our reader's reads survive a damage test on our own stock-footage crops |
| `bench/results/blind_errors.md` | `bench/blind_errors.py` | Why the 30 blind-checked sandbox misses missed: by our AI assistant's adjudication, confirmed by its own blind re-read, 13 Sentinel-side (dropped character 5, letter look-alike 3, digit misread 3, vote chose a short read 1, plate box short 1), 13 the reviewer's, 1 both, 3 unclear. The quoted 90 of 120 stands; only a second blind reviewer can move it. Confidence separates Sentinel's misreads best (AUC 0.84) |
| `bench/results/ocr_fix_trials.md` | `bench/ocr_tta.py` | 25 reading changes without training (test-time augmentation, contrast, 9 other models and ensembles, two-line halves, upscaling), fixed before scoring: none met the pre-specified gain rule on real plates; the shipped reader is the best of the available models |
| `bench/results/plate_gate.md`, `plate_gate_confirm.md` | `bench/plate_gate.py`, `bench/plate_gate_confirm.py` | The not-a-plate rule against gates written before the build (`bench/plate_gate_gates.md`), all passed 26 Sep: the sandbox hoarding caught in 23 of 23 frozen crops and 24 of 24 stored sightings; real sandbox plates lost 0 of 25 (frozen set) and 0 of the 92 stored plates the AI assistant labelled exact; own feed 4 of 5,307 exact reads, 0 of 128 vehicles; held-out synthetic plates 1 of 1,723; fresh synthetic non-plate text 4 of 126 still pass (3.2%). The real non-plate evidence is one hoarding on one camera, and the rule was chosen after seeing it |
| `bench/results/core_scale.md` | `bench/core_scale.py` | The core at statewide size, 24 Sep, separate database: 80,000 cameras, 3.0 M sightings, 100,100 watchlist entries; ingest 706 sightings/s sustained with every read matched (model average 556/s); registry page 46 ms; 30-day movement history 337 ms; map state view as clusters 161 ms. One API process on the laptop: a floor, not a sizing |
| `bench/results/counts_capacity.md` | `bench/counts_capacity.py` | The counts-only worker on one laptop, 7 Oct, keyframes only, 14 simulator cameras cycled into N RTSP sessions, no plate worker running, the relay's CPU excluded: 40 streams at 0.78 frame/s per stream (median) on 2.46 CPU cores and 13% GPU; 50 streams saturate (0.34 frame/s). A stream's rate is capped by its keyframe interval (1–2 s on these cameras) |
| `bench/results/counts_sandbox.md` | `bench/counts_sandbox.py` | The same worker on 7 sandbox cameras, 7 Oct 21:13–21:17 IST: 14–34 frames counted per minute each; keyframe intervals by camera 0.95–15 s, so CAM07, CAM17 and CAM18 were switched to every-frame decoding; the sandbox dropped every session about every 45 s. Counts only: count accuracy is not measured |
| `bench/results/g3_wiring.md` | `bench/g3_wiring.py`, `bench/g3_check.py` | G3 confidence marking, 8 Oct: two 10-minute windows on 4 cameras, API marking off (A) then on (B). B marked 161 of 748 scored sightings, exactly anpr_eval's below-0.9 count; median first-read-to-alert latency 1.68 s (B) against 2.25 s (A), 4 and 3 alerts; the live checks passed off and on with equal alert counts. PASS, adopted. The F leg (the fresh sandbox set) was not run, so no claim beyond the 120 blind-checked plates |
| `bench/results/plate_gate_live.md` | `bench/plate_gate_live.py` | The not-a-plate rule live on the two readable sandbox cameras (gate A5), from the 26 Sep 15:51–18:06 capture log: 0 reads dropped as not a plate in 135 minutes, 111 sightings stored (CAM06 81, CAM07 30). One run; the hoarding is in CAM06's view, so this is the rule holding against it, not a false-positive rate on text |
| `bench/results/sandbox_loop.md` | `bench/sandbox_loop.py` | Whether the sandbox footage repeats: identical readings of the same plate recur between windows hours apart on CAM06/CAM07, so it loops, but every gap is bounded by our own windows' spacing and no loop length is established; 90 of 188 fresh sightings repeat a reading from the first blind window |
| `bench/results/ocr_ft1.md`, `pipeline_gates_results.md` | `bench/ocr_ab.py`, `bench/ocr_gate_verdict.py`; the index written by hand from the files it cites | The fine-tuned reader ft1 against the shipped one on the frozen sets, 26 Sep: non-inferior on real plates (sandbox-blind-v1 8 fixed, 7 broken, p = 1.0), no gain shown; not adopted. The index gives every finale gate's state on 8 Oct: G3 passed and adopted, the rest not built, the YOLOX detectors not trained |

Figures from checks with no results file (the build log and repo notes record them):

| Figure | Date and conditions |
|---|---|
| Onboarding by stream URL, 1.2–2.0 s end to end | 17 Sep, idle stack; about 4 s while the demo was recording |
| Relays restored after a media-server restart, 2/2 | 17 Sep, one forced MediaMTX restart |
| Idle media-server CPU ~130% → ~23% of a core with on-demand previews | 17 Sep |
| Object detection cost, 18.4 → 17.5 analysed fps in total (−5%) | 23 Sep, 4 streams |
| Vehicle type 30/30, colour 22/27 (first colour version 48%) | 23 Sep, held-out views of stock-footage vehicles, hand-labelled (AI-assisted) |
| About 13 vehicles and 2 people in view on AMD-TRAF-001, peaks 21 and 7 | 23 Sep, wide stock-footage camera |
| Outage: API down ~87 s, 21 sightings spooled and replayed, 20 local alerts | 24 Sep 00:01–00:03 IST, one camera (AMD-AMC-001), worker log |
| Intrusion demo: 14 events and 6 alerts in 15 min | 24 Sep 01:00–01:15 IST, one zone on AMD-TRAF-001, database counts |

`bench/zone_check.py` replays a clip through the object detector and the zone logic and saves the
frame at every intrusion event, so events can be checked by eye; it is verification tooling, and the
product stores no such images. It has been run on one clip and one zone: that shows the mechanism
works end to end, not a false-alarm rate. `python bench/capacity.py` prints every sizing and cost
figure in the Plan for Scale.

On Windows, `powershell -File scripts/api.ps1` restarts the API cleanly (a stale process holding
the port is the usual reason code changes "don't take"): it waits for Postgres, then runs `python -m uvicorn`
(no .exe launcher) without an access log. Sizing: `python bench/capacity.py`. H.265 cameras are previewed in the browser through an H.264 sub-stream;
inference workers consume the original stream.

Catalogue (sandbox-style): http://localhost:8010/cameras · WebRTC preview of one camera:
http://localhost:8889/GNR-POL-001

## Privacy posture

Face recognition is deliberately **not** implemented. See `docs/privacy-dpdp.md`.
Every plate search, and every movement query with its stated purpose, is written to an append-only
audit log, as are onboarding, watchlist and alert actions, listing a camera's recent sightings, watchlist checks
and the registry CSV export (the last three since 8 Oct), and so is every plate review, without the plate text.
The API's access log is off since 8 Oct: it wrote every plate searched and every token-in-URL to a file outside the
audit log's scoping and retention; the workers' logs mask plate text. Intrusion zones trigger on presence only: the
alert carries the zone, the classes and counts in it and the dwell time, and no box, image or track
is stored.
