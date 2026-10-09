# Since the submission: 26 September to 9 October 2026

An addendum to the jury pack. The pack submitted on 27 September describes commit `9349f8f`; the finale runs the tree
committed before the 10 October freeze (`2572c82` of 8 October, plus the 7–8 October reliability and security fixes
and this document pass). This page says what changed between the two, what was measured, what was tried
and not adopted, and what runs on the day. Every number names the script-written file it comes from; nothing here is
estimated. Written 8 October 2026; updated 9 October.

## What was built

| Date | Change | Where |
|---|---|---|
| 7 Oct | **Counts-only worker**: vehicle and person counts and intrusion zones on every analytics camera at once, from keyframes only (PyAV `skip_frame`), as its own process beside the unchanged plate worker. A camera whose keyframes are more than 4 s apart is decoded in full. Count rows carry `detail.profile` (`keyframes` or `every-frame`). This is the Plan for Scale's tier B keyframe profile, which the pack called "sized but not yet built". | `services/analytics/sentinel_analytics/counts.py`; settings `COUNTS_FPS`, `COUNTS_MAX_STREAMS`, `COUNTS_EXCLUDE`, `COUNTS_BATCH`, `COUNTS_WORKER_ID` |
| 8 Oct | **G3 confidence marking**: a read stored below 0.9, or a watchlist alert on a one-character match, is marked "check the crop" in alerts, search, the journey view and the live toast; the Plate review page gains a "Below 0.9, unchecked" filter; each sighting stores `reads` and `agreement`. Nothing is suppressed; no alert rule changes. Default on; `CONFIDENCE_MARKING=false` restores the 26 Sep behaviour. | `services/api/sentinel_api/marking.py`; `bench/pipeline_gates.md` G3 |
| 7–8 Oct | **Two-laptop deployment**: `RELAY_HOST` lets a worker on another machine reach the relay; the control room opens from another machine (`CORS_ORIGIN_REGEX`, `pageHost()`); `scripts/lan.ps1` configures laptop A for the LAN; `.env.b.example` is laptop B's settings file; `scripts/db_backup.ps1` (a dump and the crops every N seconds) and `scripts/db_restore.ps1` (laptop B takes over; the relay rebuilds every camera path from the restored sources). | `scripts/`, `.env.b.example`, `services/analytics/sentinel_analytics/config.py` |
| 7–8 Oct | **Reliability**: the database, cache and relay restart with Docker (`restart: unless-stopped`; the core stayed down after a reboot on 7 Oct); the relay image pinned by digest; `scripts/api.ps1` waits for Postgres and runs `python -m uvicorn` with the access log off; `scripts/demo_prep.py` refuses to delete sightings on cameras onboarded by stream address unless `--force`; every launcher is `python -m …` (an antivirus held a `.exe` launcher on 7 Oct); a worker's spool directory is per worker id. | `docker-compose.yml`, `scripts/` |
| 7–8 Oct | **Security**: the simulator's control port bound to loopback (its outage switch had no authentication); a stream already being pushed into the relay cannot be taken over by a second publisher (`overridePublisher: no`, so a camera's picture cannot be replaced from the LAN); the onboarding card hides the stream address; `scripts/onboard_urls.py` onboards a CSV of addresses through the relay so credentials never reach the registry; `scripts/set_analytics.py`; `scripts/set_passwords.py` and `scripts/rotate_secrets.py` replace the development secrets, and the API logs an error at start while one is still an example value; a login rate limit; the ingest key compared in constant time; ingest validation (time-zone-aware event times within ±14 days, a batch size cap); `camera_code` and stream-URL validation on every registry write path; `rtsp_url` masked in `GET /cameras` and the CSV export; plate text masked in the workers' logs; the API's access log off (it wrote every plate searched); audit of `watchlist.check`, `sightings.recent` and the registry export; the detection report writes each evidence crop's SHA-256 (an integrity check, not a signature). | `services/api/`, `services/analytics/`, `scripts/security_checks.py` (23 checks at runtime, was 20), `scripts/detection_report.py` |
| 8 Oct night | **Model 1 and Model 2 gaps, and edge cases**: maintenance state and note, installation year and AMC or warranty expiry in the registry (every write path, the Registry's Edit dialog) and ageing findings in gap analysis; camera-type and maintenance filters; alert tags and a tag filter; acting on another department's alert is "not found". Request guards: a NUL character, `NaN`, out-of-range numbers, a malformed catalogue URL or CSV, and LIKE wildcards in searches were 500s or wrong answers, now 4xx or right; refusals no longer echo the submitted values. The video tile falls back to the relay's preview profile when a stream connects but gives no picture (internet HLS feeds with B-frames). The control room loads pages on first visit, shows when the API is down and fits a phone | `routers/cameras.py`, `routers/alerts.py`, `routers/reports.py`, `guards.py`, `web/src/components/EditCamera.tsx`, `web/src/components/WhepPlayer.tsx`, `scripts/edge_checks.py`, `scripts/ui_checks.mjs` |
| 9 Oct | **A real broker, NVDEC, internet feeds, concurrency**: live events checked end to end on a real broker (alerts in scope, acknowledgements and tags to other control rooms, the reconnecting state); the request guard reads bodies sent without a content type; clearing a district works; the player ignores Chrome's 2x2 placeholder; three public internet HLS streams played through the relay; the NVIDIA decoder measured; `onboard_sandbox.py` works without the reviewed locations file | `scripts/edge_checks.py`, `scripts/ui_checks.mjs`, `bench/nvdec_decode.py`, `guards.py`, `routers/cameras.py`, `WhepPlayer.tsx`, `scripts/onboard_sandbox.py` |
| 9 Oct, later | **The organisers' sandbox, reconnected**: 30 of 30 cameras through Sentinel's URL onboarding, one at a time, consume only; the plate worker on CAM06/CAM07 and the counts worker on CAM01–CAM05 for 15 minutes; a retrospective alert on a plate already read. The health monitor probes each upstream host once a round; the relay's preview transcoder waits for a clean keyframe on a lossy source | `bench/sandbox_oct9.py`, `bench/preview_start.py`, `health_monitor.py`, `infra/mediamtx.yml`, `scripts/onboard_sandbox.py`, `submission/build/wall_probe.mjs` |
| 9 Oct, afternoon | **A retrospective alert no longer holds back a live one**: listing a plate already seen raises a retrospective alert for that earlier pass; it used to count toward the 120 s cooldown, so the vehicle's next pass at the same camera raised nothing. Found when smoke's random plate fell one character from an earlier run's; smoke now draws again until its plate is clear. The 9 Oct sandbox sightings wait in the blind queue, with their scorer written before the first review | `routers/ingest.py`, `scripts/edge_checks.py`, `scripts/smoke.py`, `bench/sandbox_oct9_review.py` |
| 9 Oct, afternoon | **A saved review reading can be changed**: the reviewer of the 9 Oct sandbox sightings mistyped a plate and could not correct it. The Plate review page now offers *Edit my reading* after the reveal and a list of the reviewer's saved reviews; the server grades the change and keeps it beside the first reading, which stays the blind one that results and scores use, and audits it as `plate.review.edit` | `routers/reviews.py`, `review.py`, `upgrades.py`, `ReviewPage.tsx`, `bench/sandbox_oct9_review.py` |
| 9 Oct, afternoon | **Results, plate by plate**: the Plate review page's Results list each review with Sentinel's read and confidence beside the reviewer's reading, any later change, and the verdict. A reviewer's own reviews by default; everyone's on request, after which the crops they had not checked leave their blind queue and a blind check of them is refused (`plate_review_shown`); each listing is audited | `routers/reviews.py`, `upgrades.py`, `ReviewPage.tsx` |

Tests: 379 unit tests (`uv run --no-sync pytest`; 245 at submission, 286 on the morning of 8 Oct, 309 that evening, 373 that night, 374 on 9 Oct before the health-probe change, 376 before the review edit), 34 smoke checks (unchanged, by rule), 23 security
checks (20 at submission), and on 9 Oct 189 edge-case checks (`scripts/edge_checks.py`; 178 before the cooldown check, 179 before the review edit, 185 before the plate-by-plate list) and 111 control-room checks
(`scripts/ui_checks.mjs`); smoke and security checks run 8 Oct on the rotated secrets, all passed; after the night round, on a native
rig without Docker, 34 smoke and 22 of 23 security (the LAN publish probe got no answer there).

## What was measured

| Measurement | Result | Conditions | File |
|---|---|---|---|
| Counts-only worker, streams at once | 10: 0.67 frame/s per stream; 20: 0.82; 30: 0.82; 40: 0.78 on 2.46 CPU cores, GPU 13%; 50: 0.34 (saturated) | One GTX 1650 Ti laptop, 7 Oct; 14 simulator cameras cycled (H.264 and H.265, 576p–1080p, keyframes every 1–2 s); relay CPU excluded; no plate worker running | `bench/results/counts_capacity.md` |
| Counts-only worker on the sandbox | 7 cameras counted 14–34 frames per minute each; keyframe intervals 0.95–15 s by camera; CAM07, CAM17, CAM18 switched to every-frame decoding; every session dropped by the sandbox several times in a 4-minute probe | 7 Oct, one laptop on its home connection, counts only | `bench/results/counts_sandbox.md` |
| G3 wiring pair | marked share 161 of 748 scored sightings = the evaluation's below-0.9 count exactly; median first-read-to-alert 1.68 s with marking on against 2.25 s off (4 and 3 alerts); alert counts equal; live checks passed off and on; the F leg (a frozen fresh set) was not run, so no claim beyond the 120 blind-checked plates | 8 Oct, 4 own-feed cameras, 10-minute windows; the laptop also ran the control room's dev server and other tools (analysed fps below the 24 Sep run's in both arms) | `bench/results/g3_wiring.md` |
| OCR fine-tune `ft1` on the frozen sets | real plates (sandbox-blind-v1): 88 → 89 of 120 exact, 8 fixed, 7 broken, p = 1.0; at confidence ≥ 0.9, 69 → 66 of 81; own feed (synthetic plates): +1.8 points; non-plate text: 0 of 23 pass, both; speed 1.02× | 26 Sep, CPU, the four frozen sets; the fresh-set leg lapsed (never frozen) | `bench/results/ocr_ft1.md` |
| Not-a-plate rule, live | 0 reads dropped in 135 minutes on CAM06 and CAM07 (111 sightings stored; the hoarding it was written for is in CAM06's view) | 26 Sep capture log, scored 8 Oct | `bench/results/plate_gate_live.md` |
| NVDEC, the NVIDIA decoder (decode only) | 1080p H.264: about 740 frames a second at its ceiling (about 29 streams at 25 fps) against 470–510 in software; 1080p H.265 with the resize on the GPU: about 1,500; at 16 real-time 1080p streams, system CPU 89% → 31% (H.264, decoded and resized to 640 px) and 75% → 32% (H.265) | A GTX 1650 laptop, not the benchmark laptop; FFmpeg; 9 Oct; two rounds; the worker does not use NVDEC | `bench/results/nvdec_decode.md` |
| The organisers' sandbox, reconnected | 30 of 30 onboarded, probe median 1.0 s (0.9–2.9 s); 32 sightings in 15 minutes on CAM06/CAM07 (20 at ≥ 0.9; unread); counts on CAM01–CAM05 at 44–56 frames a minute; one retrospective alert with its crop; a wall probe during heavy source trouble showed 14 of 30 within 40 s, and 15 of the 16 without a picture had that trouble in the relay's log | 9 Oct, one laptop, native stack, consume only | `bench/results/sandbox_oct9.md` |
| The relay's preview transcoder on lossy sources | shipped command started 6 of 9 times (median 12.3 s), the adopted one 8 of 9 (median 7.2 s), alternating on CAM07, CAM08, CAM10 | 9 Oct, the sandbox through the relay | `bench/results/preview_start.md` |

## What was tried and not adopted

- **The OCR fine-tune `ft1`**: non-inferior on real plates, no gain (the table above), so the shipped reader
  (`cct-xs-v2-global-model`) runs at the finale. `bench/results/ocr_ft1.md`.
- **25 reader changes without training** (test-time augmentation, contrast, nine other models and ensembles, two-line
  halves, upscaling): already in the pack; none met its pre-set gain rule on real plates. `bench/results/ocr_fix_trials.md`.
- **G0, G2, G2b, G4, G5, G6** (`bench/pipeline_gates.md`): not built, so not adopted.
- **YOLOX detectors** (`bench/detector_gates.md`): not trained. Both detectors remain Ultralytics YOLO, AGPL-3.0, and
  every figure in the pack is theirs.

The index of all of this is `bench/results/pipeline_gates_results.md`.

## What the finale runs

Two GTX 1650-class laptops. **Laptop A**: database, API, relay, the control room on the projector, and the plate worker on a
fixed group of plate cameras at full rate (4 cameras at ~4.5 fps with object detection, `bench/results/latency.md`; or 8
at 2.9 fps with the plate path alone, `bench/results/decode.md`). **Laptop B**: the counts-only worker on every other
camera from keyframes, the judges' hands-on console (operator login), and the hot spare (a database dump and the crops
every 10 minutes to a USB stick; `scripts/db_restore.ps1` brings the control room up on B). No rotation. The plate
pipeline is the 26 Sep build plus G3's marking; the plate detector runs at 640 px; the reader is unchanged.

## What is unchanged, and what is still unmeasured

Unchanged since the submission: real plates 90 of 120 exact (75.0%), 107 within one character, one blind reviewer, two
readable sandbox views of 30 (`bench/results/sandbox_review.md`); at confidence 0.9 and above 69 of 81 exact; stock
footage with synthetic plates 96.8% exact and 91.2% capture on AMD-TRAF-002 (`anpr_eval_current.md`); alert latency
median 1.06 s, p95 1.94 s (`latency.md`); 30 of 30 sandbox cameras onboarded, 1.0–2.2 s each (`sandbox.md`). The two
sandbox runs are the 25 Sep evening run and the 26 Sep morning run of the same looping footage, not day and night
(`sandbox_daynight.md`). The capture grade describes a camera and does not predict a right read (`capture_quality.md`).

Still unmeasured, and said so: capture on real plates; count accuracy (per-frame COCO detections, no auto-rickshaw
class, night misses); a plate worker and the counts worker on one machine; streams per server node (the Plan for
Scale's 250 per tier B node stays an assumption; one laptop took 40).
