# Sentinel — build plan for the Gujarat Police Innovation Challenge 2026

Finale: **12–13 October 2026**; submission closes 28 September (the original brief said a 22–23 September
finale; the portal corrected it on 23 September). Plan written 17 September, when the day targets below
were set against the old date.

## Scope

**Model 1 + Model 2 hybrid.** Model 1 (centralised registry + GIS) is the mandatory base
layer and carries no ML risk. Model 2 (unified viewing + metadata analytics) connects
directly to department systems over RTSP/ONVIF/VMS APIs without replacing anything.
Model 3 federation adapters and appearance-based cross-camera re-ID are stretch goals.

Deliberate exclusions, each presented as an argued position rather than a gap:

| Not built | Why | What we present instead |
|---|---|---|
| 80,000 live cameras | 320 Gbps of ingest at 4 Mbps per camera (`bench/capacity.py` Model 4; 64 Gbps for sub-streams only); not a laptop problem | A capacity model from *measured* per-stream cost (`bench/`) |
| Face recognition | DPDP Act exposure, demographic bias, 4 GB VRAM | `docs/privacy-dpdp.md`; person kinds on the watchlist match by vehicle |
| Live VAHAN / eGujCop / NAFIS | Needs government network access | One adapter contract, with mocks over local fixture files; a client per system behind that contract at deployment |
| ANPR on wide-angle cameras | Optics: ~20 px character height needed | Per-camera `anpr_viable` flag; analytics tiered by what the geometry permits |
| Certified security posture | Months of STQC/CERT-In work | Threat model, RBAC matrix, audit design, clearly labelled as design |

## Day-by-day

| Day | Target | Demo-able state at end of day |
|---|---|---|
| 1 — 18 Sep | Docker stack, schema, registry API, feed simulator with mixed codecs | A live camera playing in a browser |
| 2 — 19 Sep | GIS map, video wall, health monitoring, gap analysis | **Model 1 complete** — the safe fallback demo exists from here on |
| 3 — 20 Sep | RTSP worker, vehicle + plate detection, OCR, sightings persisted, movement timeline | Search a plate, get a timestamped location history |
| 4 — 21 Sep | Watchlist UI, real-time alerts, 60-second onboarding flow, GPU benchmark | Full live test case end to end |
| 5 — 22 Sep | HLD, Plan for Scale, privacy note, demo video, rehearsal | Submission pack + rehearsed demo |

Buffer is on day 5 on purpose.

## The live test case, mapped to components

| Judges will ask for | Component |
|---|---|
| Onboard ~50 mixed feeds from different departments | `POST /cameras/import` (CSV) and `POST /cameras/sync-catalogue` (API) |
| Centralised monitoring | Video wall (WHEP, HLS fallback) + health monitor + fleet dashboard |
| Track a registration number given on the spot | `GET /sightings/movement/{plate}` — timeline + GeoJSON route |
| Cross-check live feeds against a watchlist | Ingest path matches every read: exact, then Levenshtein ≤ 1 |
| Automated real-time alerts | `alerts` table + WebSocket `/ws/events` + control-room panel |

## Hardware and network — decide by day 2

- The dev box (GTX 1650 Ti, 4 GB) handles roughly **8–16 cameras** at sampled detection rates
  (17 Sep estimate; measured since: about 4 streams at ~4.5 fps with object detection on, HLD §5.4).
  The stated test case is ~50 cameras. Options: one RTX 4090/A5000-class machine, 2–3 machines
  sharding cameras by worker ID (already supported), or a cloud L4/A10 for the week (~₹15–25k).
- 50 streams at 2–4 Mbps is 100–200 Mbps sustained. Venue wifi will not carry it. Either wired,
  or ingest workers sit next to the feeds and only metadata crosses the network.

## Biggest risk

The top evaluation criterion is *"successful test case on government feed"*, and that feed cannot
be rehearsed against beforehand. Mitigation: the adapter boundary is strict enough that onboarding
an unknown RTSP/ONVIF source is a form submission, never a code change — and that flow gets
rehearsed on the simulator's deliberately awkward mix (H.264/H.265, D1 analog, 12–25 fps) until it
is boring.

## Status log

- **17 Sep:** Day 1 done a day early. Stack, schema, simulator (12 cams), full API, 22-check
  smoke test green, 12/12 streams online with health monitoring. Synthetic plates verified legible.
- **17 Sep (later):** Day 2 done. React control room: map, 3×3 video wall with 9/9 tiles live over
  WebRTC (H.265 cameras via H.264 preview sub-streams), search with route map, live alerts, health
  and gap reports, registry onboarding, watchlist. **Model 1 is complete and demo-able.**
- **17 Sep (later):** Day 3 done. Analytics worker live on 8 streams: YOLOv11n plate detector
  (CUDA) + text-line finder, batched 10-slot OCR, per-character voting. 90 sightings and 17
  watchlist alerts in 100 s across all 8 ANPR cameras. Synthetic-font OCR is ~59% exact on the drawn
  plates (a synthetic font; not an accuracy figure); the 1-edit fuzzy matcher absorbs the rest. Real footage needed for accuracy numbers that matter.
- **17 Sep (later):** Day 4 done. Onboarding by stream URL (probe → relay → register) in ~2 s,
  self-healing relays, UI card; 29-check smoke test green. Benchmark shows CPU (not GPU) is
  the ceiling → GPU-native edge nodes. `docs/plan-for-scale.md` written from `bench/capacity.py`.
- **17 Sep (later):** Day 5. Submission pack in `submission/`: HLD, Plan for Scale and privacy PDFs
  with seven generated diagrams; solution deck; scripted demo video; detection report; finale runbook
  (`docs/demo-runbook.md`). Redis swapped for Valkey (Redis 7.4 moved to source-available licences; Redis 8 adds an AGPL option). Plate
  detector licence found to be AGPL-3.0 — disclosed in the HLD with options. Simulator fixed so
  vehicles never hide each other's plates.
- **23 Sep:** Vehicle and person detection. A second detector (stock YOLO11n, COCO) on the frames the
  plate path already pulls: per-camera counts (one row per camera per minute, frames analysed as the
  denominator) and vehicle type/colour bound onto plate sightings. Two simulator cameras now replay
  real traffic (Pexels footage, every plate replaced by a synthetic registration). Measured: type
  30/30 and colour 22/27 on held-out real vehicles; colour's first version managed 48% and was reworked.
  Plate throughput −5% at 4 streams. 34-check smoke test and 42 unit tests green.
- **Open risks:** antivirus consuming ~41% CPU on the dev laptop (add exclusions);
  no real Indian-plate footage yet (the real-traffic cameras carry synthetic plates); per-node
  capacity is still an assumption.

## 24 September

Added:

- **Store-and-forward.** Batches the API cannot take spool to disk (512 MB cap, oldest dropped with a
  warning) and replay oldest first with their frame times; batch ids make a replay after a lost reply
  store once. During an outage the worker checks reads against its copy of the active vehicle
  watchlist (plate, kind, severity; refreshed every 60 s) and records hits in its log and
  `data/local-alerts.jsonl`; the control-room alert is raised on replay with the original sighting time.
- **Tracker and plate choice.** The confirmation hold runs on the wall clock and stretches with the
  achieved analysis rate; below 2 fps one read with OCR confidence ≥ 0.6 is accepted, and the API
  alerts on such a sighting only on an exact match. The old tracker stored nothing at 0.8, 0.5 or
  0.3 fps. The stored plate is now the per-character vote across a track's reads.
- **Hardware decode** (`HW_DECODE=auto`, D3D11 through OpenCV, software fallback per camera; on this
  laptop the decoder is the Intel integrated GPU's, not NVDEC);
  **watchlist matching** by one-character masks instead of a Levenshtein scan; a **24 h
  retrospective check** when a plate is added.
- **Control room:** alerts in priority order with near-match cards, inline disposition, toast and
  chime for high/critical; the **journey view** (stops, dwell, hop speed, implausible-speed flag);
  **intrusion zones** drawn on the video wall, triggered by the ground point of the object
  detector's boxes, counts only, no box, crop or track stored.
- **Security:** database, cache and media-server control bound to the host; crops served only with
  token, permission and camera scope; department ownership guard on onboarding and relays.
  `scripts/security_checks.py`, 15 checks.
- **Government-feed tooling:** `smoke.py --skip-fleet`, warnings for `MAX_STREAMS` truncation and
  unknown `CAMERAS`, catalogue dry-run preview on the Registry page, wider catalogue mapping.
- **Detection report** with a per-vehicle front page and `_vehicles.csv`; the own-feed report is now
  `detections_20260924_014621.*` (window 23 Sep 11:56–12:06 IST).
- **Map at scale:** above 2,000 cameras the map shows counts per grid cell, and only the cameras in
  view from zoom 12; a small fleet still loads whole.
- **Measurement tools:** `scripts/anpr_eval.py`, `scripts/latency_report.py`, `bench/matcher.py`,
  `bench/decode_summary.py`, `bench/plate_choice.py` (reads `TRACK_LOG`), `bench/zone_check.py`,
  `bench/core_scale.py`.

Measured on the GTX 1650 Ti laptop (files in `bench/results/`):

- Outage test (one camera): API down ~87 s, 21 sightings spooled, all 21 replayed, 20 local alerts,
  control-room alerts with the original times.
- ANPR, current worker, 10 min: AMD-TRAF-002 96.8% of sightings exact, 91.2% of plates on screen
  ≥ 1 s captured; AMD-TRAF-001 90.2% and 21.7%. Synthetic plates painted onto stock footage filmed in
  Mumbai; real Gujarat plates remain unmeasured. The "97% / 84%" quoted earlier were the first
  6–10 minutes of the 23 Sep run (98.7% / 90.2% over the whole run) and are replaced everywhere.
- Vote against best single read on 4,891 tracks from two runs: a tie (84.2% and 84.4% exact on the
  hardware-decode run); the vote is kept.
- First valid read to alert row: median 1.06 s, p95 1.94 s, 31 alerts, 4 cameras, same host clock.
- Hardware decode: +49% analysed fps per stream at 8 and at 12 streams, no change at 4 (plate
  pipeline only; the decoder was the laptop's Intel integrated GPU, not NVDEC).
- Matcher at 100,011 entries: 0.79 ms (one character off) and 1.14 ms (not listed), against 45–56 ms.
- Core at statewide size (one laptop, separate database): 80,000 cameras, 3.0 M sightings, 100,100
  watchlist entries; ingest 706 sightings/s sustained against the model's 556/s average; 30-day
  movement history 337 ms; map state view as clusters 161 ms (`bench/results/core_scale.md`).
- Intrusion, one demo zone on AMD-TRAF-001: 14 events in 15 min, one per 60 s loop, one or two
  people each; 6 alerts after the 120 s cooldown. Shows the mechanism, not a false-alarm rate.
- Tests: 182 unit (42 on 23 Sep), 34 smoke (3 can SKIP with `--skip-fleet`), 15 security checks.

Corrected above: the scope table's 17 Sep "80 Gbps of ingest" is now `bench/capacity.py`'s Model 4
figure, 320 Gbps at 4 Mbps per camera (64 Gbps if only 0.8 Mbps sub-streams were carried); the
17 Sep "~59% exact" was a synthetic font on drawn plates and is not a headline number. HLD v1.3 and
the rebuilt Plan for Scale carry the new figures; screenshots were retaken. The demo video was not
re-recorded: its scenes are from 23 Sep, and only its title card was replaced (`retitle.mjs`).

Still open: accuracy on real Gujarat plates, the government-feed run and report, per-node capacity
(and NVDEC decode) on a server GPU, and a load test of the core on server hardware at peak rates.

Later on 24 Sep:

- **Model 2, not a hybrid.** A teammate filling the form saw that it confirms Model 1 separately, so "Model 1 +
  Model 2" is simply Model 2. The HLD (v1.4, section 3), deck (slides 1 and 4), video title card, READMEs and form
  answers now say Model 2 on the Model 1 foundation.
- **Publisher credential.** An anonymous RTSP ANNOUNCE to the relay's LAN address got 200 OK: Docker Desktop hands
  LAN connections to the container from the same private range as the host's. Pushing a stream now needs the
  publisher credential (`MEDIAMTX_PUBLISH_PASS`); the new security check gets 401. Security checks 16/16, smoke 34/34.
- **Report.** `detection_report.py` lists intrusion alerts (section, summary tile, `_intrusions.csv`). The shipped
  own-feed report is now 24 Sep 01:30-01:39 on four cameras with the current worker: 862 reads, 10 watchlist and 4
  intrusion alerts.
- **Portal FAQ** appended to `docs/official-problem-statement.md`: the sandbox is 30+ cameras with ~12 h of footage
  each from our five seeded departments, on a common timeline; two categories, top three of each to the finale.
