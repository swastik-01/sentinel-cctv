# Plate pipeline review: changes ranked by expected gain on real plates

Written 26 Sep 2026, 15:00-16:00 IST. It reads the code at commit `e18331a`
(`services/analytics/sentinel_analytics/`: `stream.py`, `detect.py`, `ocr.py`, `worker.py`, `tracker.py`,
`static_text.py`; `sentinel_common/plates.py`; `services/api/sentinel_api/routers/ingest.py`) and the results files
named where each number is used. Four scripts were written or corrected for this review. All four only read data
that is already on disk, and none of them runs the worker or reads a camera:

- `bench/pipeline_diag.py` → `pipeline_diag.md` shows where stored reads go wrong: the sandbox blind review
  (described only, never tuned on), plus our own feed's stored sightings and crops. Corrected today: the confidence
  column is REAL, so the 14 plates stored at exactly 0.9 had fallen below the 0.9 band. It now agrees with
  `sandbox_review.md` (81 plates, 69 exact).
- `bench/track_replay.py` → `track_replay.md` replays tracker rules offline on our own feed's TRACK_LOG
  (AMD-TRAF-001/002, 24 Sep, about 4.5 analysed frames per second per camera). Check: from the same reads, the replay
  stores 887 sightings; the worker's own logs of those runs show 888.
- `bench/detect_size.py` → `detect_size.md` runs the product's plate path at detector sizes 640, 960 and 1280 on our own
  two stock clips, on the CPU at below-normal priority while the live worker kept the GPU.
- `bench/ocr_padslot.py` → `ocr_padslot.md` asks whether the OCR confidence should also count the first empty slot
  (single crops of the frozen sets, CPU).

**What the numbers are.** Real plates appear only in the team's blind review of 120 stored sandbox plates
(`sandbox_review.md`: 90 exact, 107 within one character) and in the error analysis built on it (`blind_errors.md`).
Those are descriptions of where the misses are, not a test any change here passed, and no threshold below was set on
them. Every "how to measure" names our own feeds: Pexels stock footage with synthetic plates painted on. On
AMD-TRAF-002 (an ANPR view, plates about 100 px) that footage is near its ceiling of 98% exact. AMD-TRAF-001 (a PTZ
view, plates read at a median 55 px) is where rules differ. A gain on real plates is claimed only after fresh blind
reviews of new captures, under gates written before the change is scored. No plate text appears here.

## Where stored real plates go wrong (sandbox, 120 plates)

- **The model makes most misreads.** Re-reading the stored crop alone repeats 13 of the 14 misreads the error analysis
  puts on Sentinel's side (12 identically; `blind_errors.md`). So for the exact rate of *stored* plates, the OCR model
  is the main lever: the Indian-format fine-tune under `bench/ocr_gates.md`. The pipeline changes below mostly move
  **capture** (how many passing vehicles get read at all) and **reads per vehicle**. They also change what reaches an
  operator unchecked.
- **Too few reads per vehicle.** The sandbox cameras were analysed at a median of 1.6 frames per second per camera
  (quartiles 0.8-2.1); our own feeds run at about 4.5. Exact by track size (`pipeline_diag.md`): 1 read 24/32 (75.0%),
  2 reads 15/25 (60.0%), 3 reads 51/61 (83.6%). In a two-read track the vote follows the more confident read, so the
  second read adds nothing. Such a track is also stored at any confidence the gate passed (0.35), while a single read
  needs 0.6. Two-read tracks below 0.6 were 1/5 exact.
- **7 of the misses are one character short, all by one mechanism.** The stored plate has a one-letter series where
  the true plate has two. The stored number starts with the digit look-alike of the true last series letter. The OCR
  lost a digit near the plate's right end (`blind_errors.md` section 4), and `normalise_plate`'s positional repair
  filled the 4-digit number from the series. The result looks like a valid plate. The watchlist's fuzzy match
  compares plates of equal length only, so such a read cannot alert on its true plate. Refusing the repair outright
  is not an option: 25 of the 120 true plates have a one-letter series.
- **Confidence already separates.** Plates stored at confidence >= 0.9: 81, of which 69 exact (85.2%) and 79 within
  one character (97.5%). Below 0.9: 39 plates, 21 exact (53.8%). The 14 plates stored at exactly 0.9 are three agreeing
  reads whose best read was below 0.9. Of those, 12 were exact. On real plates a misread can repeat across reads.
- **One vehicle stored twice.** 5 of the 121 stored sandbox sightings (4.1%) sit in pairs within 10 s whose plates
  differ by 1-2 characters.

## The plate path, stage by stage

| Stage | What the code does | What matters for accuracy |
|---|---|---|
| Frame (`stream.py`, `worker.py`) | One decode thread per camera. The newest frame is kept, retrieved at 1.5 × `DETECT_FPS` (5); each camera is analysed at most every 0.2 s. | A camera's analysis rate is the smallest of `DETECT_FPS`, the frames that arrive, and the loop's speed. `Stats.decoded` and `Stats.retrieved` are counted but never logged, so the sandbox's 1.6 fps cannot be split between network and laptop. Two clues point at frame delivery. The 2-camera sandbox run now going gets 0.8-1.2 fps per camera, while four of our own feeds got 4.5 each. That run also logged 92 connects and 92 connect or decode failures between 14:58 and 15:35 (`data/rotation-capture`). |
| Detect (`detect.py`) | YOLO plate detector at `imgsz=640` for every camera, conf 0.35. Unioned with the classical text-line finder, which runs on a 960 px copy on the CPU and gives up to 6 boxes. | At 1920x1080 the frame shrinks 3×. On our own clips, **640 misses plates that 960 reads, even on the ANPR view** (rank 1). `anpr_viable` reaches the worker (`/ingest/cameras`) but is unused, and on the sandbox it is wrong: CAM06 and CAM07, which gave all but one reviewed plate, are flagged not viable, while CAM12-16 are flagged viable and gave 0-1 reads (`sandbox.md`). Which detector found a box is not recorded. |
| Crop (`worker.py`) | Pad = 0.15 × box height on every side, cut from the full-resolution frame. The evidence copy is saved as JPEG 85. | Horizontal padding follows the box height: about 4 px on a 100×30 plate. The error analysis finds the box no shorter on the dropped-character plates, and does not recommend a wider crop (`blind_errors.md`). |
| OCR (`ocr.py`) | fast-plate-ocr CCT-XS v2 on the CPU, one batch per tick. Confidence is the weakest character's probability over the text's slots. | The pad slots' probabilities are ignored. Counting the first pad slot too (is the plate really this short?) was measured today (`ocr_padslot.md`) and changes almost nothing (see Not recommended). |
| Gate (`worker.check_read`) | Confidence >= 0.35, `looks_like_indian_plate` after `normalise_plate`, and at most 1 letter made from digits. | The repair also turns letters into digits in the number field, and nothing counts that. It is the shortening mechanism above. |
| Tracker (`tracker.py`) | Reads join an open track by text alone: at most 2 edits, with box and time unused. A track closes at 3 reads, or when its hold of max(1 s, 2.5 analysis intervals) ends. A track needs 2 reads; the exception is one read >= 0.6 on a camera analysed below 2 fps. The vote is per character over the most common length, and a tie in length goes to the length read first. Each read weighs with its weakest character's confidence. The stored confidence is the best read's, raised to exactly 0.9 for three agreeing reads. The evidence crop is the best-confidence read, even where the vote disagrees with it. | Reads after the third are wasted. They start new tracks, which the repeat filter drops, or which store the vehicle again if they read differently. A camera analysed at 2-3 fps gets neither a third read nor single-read acceptance (rank 2). |
| Ingest (`ingest.py`) | The API normalises again and stores. Fuzzy watchlist matching needs equal length and is skipped on one-read sightings. `plate_text` holds the vote, not the raw read. | The raw read is kept nowhere, so a normaliser repair cannot be seen after the fact. |

## Ranked changes

Each change is ranked by its expected gain in exact reads or capture on real plate cameras, weighed by how well that gain is
evidenced and by what it costs. "Own feed" numbers were measured; "sandbox" numbers describe the blind review and tune nothing.

| Rank | Change | Effort | Risk | Evidence | When |
|---|---|---|---|---|---|
| 0 | Instrument first: per-camera decoded and analysed fps in the status line; TRACK_LOG also logs dropped tracks and each read's time, box width and detector source | XS-S | none (logging) | enabler for ranks 2, 3, 5, 9, 10 | now |
| 1 | Plate detector at 960 on plate-capable cameras, the flag set from evidence | S | medium (GPU time, more non-plate reads to check) | own clips, measured, large | 27 Sep candidate if the live check passes; else finale |
| 2 | Remove the 2 fps cliff: accept one read >= 0.9 at any analysis rate | S | low | own feed, measured | 27 Sep candidate |
| 3 | Hold a track for its third read; break a length tie by summed confidence | XS-S | low (up to ~1 s more latency at a low rate) | own feed, measured; sandbox direction | 27 Sep candidate |
| 4 | Route by confidence: auto band >= 0.9, the rest marked and queued for review | M | low | sandbox descriptive; own feed | finale (policy text now) |
| 5 | Raise the analysis rate on plate cameras: find what caps it, then serve plate cameras first | S to find, M to fix | low | own feed direction; sandbox descriptive | finale |
| 6 | One sighting per pass: keep reading after storing, correct at the end of the pass | M | medium (API update path) | own feed, measured | finale |
| 7 | Evidence crop: the sharpest or largest read that agrees with the stored plate | S | low | own feed and sandbox, indirect | finale |
| 8 | Keep dropped-digit reads out: reject the raw shape two series letters + three digits (as `blind_errors.md` proposes) | S | medium (post hoc; 1 right of 19 such reads) | sandbox post hoc; own feed | finale, after fresh blind data |
| 9 | Vote weights from crop size and sharpness, or per-character probabilities | M | low-medium | own feed, indirect | finale, after rank 0 |
| 10 | Classical text-line finder off on plate cameras if it adds nothing there | S | low | own clips, measured | finale, after rank 0 |

### 0. Instrument first (enabler)

- **Change.** Add each camera's decoded fps, retrieved fps and analysed fps to the worker's 30 s status line
  (`Stats.decoded` and `Stats.retrieved` already exist). Add to TRACK_LOG: tracks dropped by `min_reads` (flagged), and
  for each read its wall time, box width, sharpness, detector source (YOLO or classical) and raw text. TRACK_LOG stays
  for our own feeds only. For the sandbox, log per camera how many stored sightings came from each detector source
  (counts, no text).
- **Why.** Rank 5 cannot be diagnosed without the decoded rate. The replay cannot score single-read rules at a normal
  rate, because a vehicle read once at 4.5 fps is dropped before it is logged. Ranks 9 and 10 need the new fields.
- **Measure.** No accuracy change is expected. Run `pytest`, then one own-feed run to check the fields.

### 1. Plate detector at 960 on plate-capable cameras

- **Evidence** (`detect_size.md`: our two clips, one frame per second, the product's plate path, no tracker). On
  AMD-TRAF-002, the ANPR view, 640 reads 89 of 144 painted plates in the sampled frames (61.8%). 960 reads 127 (88.2%)
  and 1280 reads 132 (91.7%). The plates shown for at least 1 s that were read in at least one sampled frame go from
  53/68 to 64/68 and 65/68. The median width of plates read exactly falls from 125 px to 91 px: 640 was finding only
  the nearest plates. On AMD-TRAF-001 (small plates) the counts are 17, 30 and 34 exact reads of 580, and 13, 22 and 23
  of 129 plates. **The cost is per-read precision.** The exact share of gated reads falls from 92.7% at 640 to 86.4%
  at 960 on AMD-TRAF-002, and from 77.3% to 68.2% on AMD-TRAF-001. On AMD-TRAF-002, 17 reads at 960 match no painted
  plate, against 4 at 640. Some are real plates the painter missed and some are not plates; the clips cannot tell
  which. The product's tracker needs two reads before it stores any of them. The same
  detector found every painted plate at 1280 on native-resolution tiles (`feedsim/realclip.py`). Real plates on the
  sandbox were stored mostly at 80 px and wider (`pipeline_diag.md`: 109 of 120), so a 640 detector sees a real plate
  only once the vehicle is close.
- **Expected effect.** More plates read at all, and more reads per pass: a plate becomes detectable earlier in its
  approach. That is capture, plus more evidence per vote. Plates read small are read less well (own-feed crops under
  70 px: 86.6% exact, against 96.0% at 70-90 px and 98-99% above 90 px; `pipeline_diag.md` section 3). Rank 4 routes
  them.
- **Cost.** About (960/640)² = 2.25× the plate detector's work per frame. The CPU times in `detect_size.md` are too
  noisy on a shared laptop to say more. On the sandbox the analysis rate is capped by frame delivery, not by
  the GPU (rank 5), so a larger detector should cost little there. On a GPU-bound worker it lowers the rate: keep it to
  the 2-4 plate cameras per worker.
- **Change.** An `imgsz` per camera: 960 on plate-capable cameras, 640 elsewhere (two detector batches per tick, or
  one setting per worker with plate cameras on their own worker). "Plate-capable" must come from evidence, not the
  registry flag: for example, a camera that stored plate reads with boxes of 80 px or more in the last hour, or one the
  quality page marks. On the sandbox the flag is wrong for exactly the cameras that read plates.
- **Risk.** Medium. Other text gets read too. Watch precision over stored sightings and the fixed-text and
  not-a-plate drop counts.
- **Effort.** S for a worker-wide setting; S-M per camera.
- **Measure.** `bench/detect_size.py` (done). Then the live A/B on our own feeds (see How to measure): `anpr_eval.py`
  exact over sightings, capture by time on screen, per-camera analysed fps, `latency_report.py`. Pre-register:
  capture up on both cameras, exact over sightings no more than 1 point lower, analysed fps no more than 10% lower.

### 2. Remove the 2 fps cliff in single-read acceptance

- **Evidence** (`track_replay.md` section 3). At about 2.2 analysed fps a camera is not "slow" (`SLOW_FPS=2`), so a
  pass that yields one read is dropped. Capture there is **51.3%** on AMD-TRAF-001 and **71.1%** on AMD-TRAF-002. That
  is below the 1.5 fps figures (65.2% and 86.4%), where single reads are accepted. Accepting one read at >= 0.9 at 2.2
  fps raises capture to **65.3% and 84.1%**, with precision unchanged (95.9% vs 94.9%; 99.0% vs 99.0%). The one-read
  sightings it adds were 56/56 and 175/177 exact. The sandbox cameras sit on this boundary (quartiles 0.8-2.1 fps; the
  26 Sep morning run's log shows cameras at 2.0), so they flip between the two rules. On the sandbox, one-read tracks at >= 0.9 were
  16/19 exact and 19/19 within one character.
- **Change.** In `PlateDeduper.harvest`, store a one-read track at confidence >= 0.9 at any rate, and keep the shipped
  >= 0.6 below `SLOW_FPS`. The API already refuses a fuzzy (one-character) alert on a one-read sighting.
- **Risk.** Low. At a normal rate a one-read pass is a glimpse; count such sightings with rank 0's dropped-track log,
  because the replay cannot see them at 4.5 fps.
- **Effort.** S: one condition and a test in `services/analytics/tests`.
- **Measure.** `track_replay.py` (done). Then one own-feed window each at `DETECT_FPS=2.5` and at 5, with TRACK_LOG
  (rank 0 fields) and `anpr_eval.py`. Pre-register: capture up, and precision within 1 point, on both cameras.

### 3. Hold a track for its third read; break a length tie by summed confidence

- **Evidence** (`track_replay.md` sections 2 and 5). The shipped first sighting of a pass is exact on 186/199
  (AMD-TRAF-001) and 661/674 (AMD-TRAF-002). A vote over each pass's first 3 reads gives 190 and 661: **4 fixes, 0
  breaks**, from tracks whose 1 s hold ended at 2 reads. On the sandbox, 2-read tracks were the weakest group (60.0%).
  Separately, 14 of 1,631 own-feed tracks split evenly between two lengths. The shipped vote takes the length read
  first; summed confidence gives **7 fixes, 1 break**. The error analysis found one sandbox miss where two short reads
  outvoted a right full-length one (`blind_errors.md` section 4).
- **Change.** (a) `harvest` keeps a 2-read track open until a third read, up to a longer limit (for example 4 analysis
  intervals instead of 2.5), then stores it as today. (b) `vote()` picks the length by (count, summed weight).
- **Expected effect.** Own feed: about +2 points exact on AMD-TRAF-001 and none on AMD-TRAF-002 (ceiling). On real
  plates it moves sightings from the 2-read group into the 3-read group. Most sandbox misreads are the model's, so the
  gain there is bounded.
- **Risk.** Low. Tracks that wait gain at most about 1.5 analysis intervals of latency: about 0.3 s at 4.5 fps and
  1 s at 1.5 fps. The alert latency on record has a median of 1.06 s (`latency.md`).
- **Effort.** XS-S. Update the tracker tests that pin the hold.
- **Measure.** `track_replay.py` (done). Then the live own-feed A/B with `anpr_eval.py` and `latency_report.py`.
  Pre-register: exact not worse on either camera, capture not worse, and median latency no more than 0.5 s higher at
  4.5 fps.

### 4. Route by confidence: an auto band and a review band

- **Evidence.** Sandbox, descriptive: >= 0.9 holds 81 of 120 plates, 69 exact and **79 within one character**. The
  watchlist's fuzzy rule allows one substitution, so 97.5% of the band would alert on the right plate. Below 0.9, 21 of
  39 are exact, and 11 of the 14 Sentinel-side misses fall there (`blind_errors.md`). Own feed (`track_replay.md`
  section 4): the band holds 85.3% of first sightings at 99.2% exact (4.5 fps). On our plates, three reads that all
  agree were exact every time (606 of 606 at 4.5 fps). On the sandbox, three agreeing reads whose best read was below
  0.9 were exact on 12 of 14, because on real plates a misread repeats.
- **Change.** A policy, not a model change. At >= 0.9, alerts and search behave as today. Below 0.9, alert on an
  exact match only, show the sighting as "check the crop", and list it in the Plate review queue (the page exists).
  Store `reads` and the vote's agreement beside the confidence (the API already receives `reads`), so the band can
  later use them instead of the 0.9 the boost gives three agreeing reads.
- **Expected effect.** No change in exact reads. What an operator acts on without checking gets more precise, and it
  is the honest way to use a 75%-exact figure.
- **Risk.** Low. A below-band watchlist hit alerts only on an exact match.
- **Effort.** M (API rule, UI badge, review queue filter). The policy text can go into the documents now.
- **Measure.** On our own feeds, the per-camera exact-by-confidence table of `anpr_eval.py`. Check the threshold on the
  next fresh blind batch, never by tuning on `sandbox-blind-v1`.

### 5. Raise the analysis rate on plate cameras

- **Evidence.** Sandbox, descriptive: 3-read tracks 83.6% exact against 60.0% for 2-read tracks, at a median 1.6 fps.
  Own feed (`track_replay.md` section 3): keeping every third read (about 1.5 fps) cuts capture from 95.5% to 65.2% on
  AMD-TRAF-001 and from 98.1% to 86.4% on AMD-TRAF-002, under the shipped single-read rule.
- **Change.** First, rank 0's decoded fps on the live sandbox run. If frames arrive at 5 fps or more, the worker is the
  limit: serve plate cameras first in each tick's batch, lower `OBJECT_FPS` on them (the object pass takes 37-84 ms a
  frame in the sandbox logs), and turn the classical finder off there (rank 10). If frames do not arrive, which the
  reconnect counts suggest, the worker cannot raise the rate. Ranks 2, 3 and 6 are then what handle a slow camera, and
  the stream's reconnect handling is the place to work.
- **Expected effect.** From 1.5 to 4.5 fps: 10-30 points of capture on our own feeds, and 3-read tracks in place of
  1-2 read tracks on the sandbox.
- **Risk.** Low. Non-plate cameras get fewer object frames.
- **Measure.** Load a worker with 6-8 of our own cameras so the rate falls as on the sandbox, then run the live A/B
  with `anpr_eval.py`, the per-camera analysed fps and `latency_report.py`.

### 6. One sighting per pass: keep reading after storing, correct at the end

- **Evidence** (`track_replay.md` sections 1 and 2). A whole-pass vote against the shipped first sighting: **5 fixes, 0
  breaks** (AMD-TRAF-001 93.5% → 96.0%; AMD-TRAF-002 unchanged at 98.1%). Squared-confidence weights give 6 fixes and
  0 breaks; equal weights give 6 and 7. The shipped rule also stores 14 extra sightings of passes it has already stored
  (6 + 8 of 887). On the sandbox, 4.1% of stored sightings are in such pairs.
- **Change.** Store the first track as now, so the alert keeps its latency. The track stays open while its plate is
  still being read, and at the end of the pass the worker sends a correction under the same `track_id` if the
  whole-pass vote differs. The API updates the sighting and re-runs matching without duplicating an alert. Later
  reads that differ by more than one character fold into the pass instead of storing the vehicle again.
- **Expected effect.** Own feed: +2.5 points exact on the small-plate camera and about 1.6% fewer duplicates. On the
  sandbox the gain is bounded by how few reads a pass has at 1.6 fps.
- **Risk.** Medium. It needs a new update path in ingest (idempotent, safe to replay from the spool) and alert
  re-evaluation.
- **Effort.** M.
- **Measure.** `track_replay.py` (done). Then a live own-feed run with `anpr_eval.py`: exact over sightings, capture,
  duplicates.

### 7. Evidence crop: the sharpest or largest agreeing read

- **Evidence.** The crop comes from the track's best-confidence read even when the vote chose another plate. On the
  blind set, the stored plate and a re-read of its own crop disagree on at least 4 of 120: stored right and crop wrong
  3, crop right and stored wrong 1 (`ocr_baseline_blind.md`). Own feed (`pipeline_diag.md` section 3): below 0.7
  confidence, the sharper half of crops reads 94.4% exact and the blurrier half 75.3%; the wider half 93.4% and the
  narrower 75.9%. At >= 0.9 there is no difference.
- **Change.** Among reads whose text equals the stored plate, keep the crop with the highest confidence, ties going to
  the larger box (or sharpness × width).
- **Expected effect.** The stored plate does not change. The evidence then shows the plate that was stored, and the
  review page shows a better image.
- **Risk.** Low. **Effort.** S.
- **Measure.** Own-feed run: the share of sightings whose crop, re-read by `ocr_ab.py`'s reader, equals the stored
  plate, before and after.

### 8. Keep dropped-digit reads out

- **Evidence.** Post hoc, sandbox. All 7 shortened stored misses have the repaired shape: a one-letter series whose
  number starts with the look-alike of the lost series letter (`pipeline_diag.md`). The raw read of a dropped digit
  has a shape no Indian plate has, two series letters then three digits (`blind_errors.md` section 4). Single reads
  of that shape were right on 1 of 4 on `sandbox-blind-v1` (a true nine-character plate) and 0 of 15 on `ownfeed-v1`.
  Our painted plates all have two series letters, so our own feed cannot measure what the rule costs on real
  one-letter plates.
- **Change.** Reject that raw shape in `worker.check_read`, as the not-a-plate rule rejects phone numbers, and log the
  drops per camera (counts only). With rank 3's length rule, a track keeps its full-length reads.
- **Risk.** Medium. It was found by looking at these misses, as the not-a-plate rule was, and 25 of 120 real plates
  have a one-letter series. Most caught reads become no sighting rather than an exact one.
- **Effort.** S.
- **Measure.** Pre-register it, then confirm on the next fresh blind batch (the CAM06/CAM07 capture now running), not
  on the set it came from. Our own feed checks only that nothing else changes (`ocr_ab.py` on `ownfeed-v1`, and the
  live `anpr_eval.py`).

### 9. Vote weights from crop size, sharpness or per-character probability

- **Evidence.** Indirect only. Size and sharpness carry information beyond confidence when confidence is low (rank 7).
  Squared confidence and plain confidence give 6 fixes and 5 fixes, both with 0 breaks (`track_replay.md`): no real
  difference. The OCR's per-position probabilities are thrown away, and each read votes with its weakest character.
- **Change.** Weigh each position by its own character's probability, or scale a read's weight by its crop width and
  sharpness.
- **Expected effect.** Small at 4.5 fps; possibly useful on 2-3 read tracks at a low rate. **Effort.** M: rank 0's
  logging, a replay, then a live check.
- **Measure.** `track_replay.py` extended to the new fields, then `anpr_eval.py`.

### 10. The classical text-line finder on plate cameras

- **Evidence** (`detect_size.md`). On our two clips it contributed 0 exact reads on AMD-TRAF-001 and 1 on AMD-TRAF-002,
  against 17-34 and 88-131 from YOLO. It produced the sandbox hoarding's reads, which the not-a-plate rule now drops,
  and it costs CPU in the main loop on every frame. It remains the safety net for our synthetic clips, where it finds
  drawn plates. Which detector found each stored sandbox plate is not recorded.
- **Change.** Once rank 0 shows it adds nothing on real plate cameras, turn it off per camera (`DETECTOR=yolo`) and
  give the CPU to rank 5.
- **Measure.** `detect_size.py` (done), rank 0's source counts on the sandbox, then the live A/B.

## Not recommended

- **OCR every Nth frame of a track.** OCR costs about 4-9 ms per crop on the CPU on the labelled sets
  (`ocr_baseline*.md`). The sandbox's
  limit is analysed frames, not OCR, and fewer reads weaken every vote (ranks 2, 3 and 5).
- **Counting the first pad slot in the OCR confidence** (`ocr_padslot.md`, single crops through the product's reader).
  On `sandbox-blind-v1`, one wrong read leaves the 0.7 band and none leaves the 0.9 band; the 7 short reads were already
  below 0.9. On `ownfeed-v1`, 4 of 5,512 gated reads leave the 0.9 band, all 4 wrong. Too small to be worth a change.
- **Equal vote weights.** A whole-pass vote with equal weights gives 6 fixes and 7 breaks against the shipped first
  sighting (`track_replay.md`).
- **Raising `SINGLE_READ_CONF` to 0.9 for storage below 2 fps.** Own feed at 1.5 fps: precision rises by 1-2 points and
  capture falls by 13-19 points (`track_replay.md` section 3). Keep 0.6 and route by confidence instead (rank 4).
- **Associating reads by box (IoU) as well as text.** It matters in busy multi-vehicle scenes, but the replay shows
  little damage from text-only association on our feeds, and rank 6 deals with the duplicates.
- **A wider crop.** The box is no shorter on the dropped-character plates (`blind_errors.md`), and single-crop padding
  variants are being scored separately (`bench/ocr_tta.py`).

## How to measure, in one place

1. **Offline first, on our own data.** Tracker rules go through `bench/track_replay.py` (TRACK_LOG from AMD-TRAF-001/002;
   never the sandbox). OCR and confidence changes go through `bench/ocr_ab.py`, with `ownfeed-v1` for non-regression;
   the real sets are used only by the gates in `bench/ocr_gates.md`. Detector changes go through
   `bench/detect_size.py`.
2. **Live, on our own feeds.** Run AMD-TRAF-001 and AMD-TRAF-002 on one worker under the conditions of
   `anpr_eval_current.md`, with candidate and baseline in alternating 10-minute windows (A B A B) in one session.
   Score with `scripts/anpr_eval.py` (exact, within one, capture by time on screen) and `scripts/latency_report.py`.
   Add windows at `DETECT_FPS=1.5` and `2.5` to stand in for the sandbox's rates. Only when the GPU is free, never
   beside the live sandbox worker.
3. **Real plates.** Only through fresh blind reviews of sightings captured after the change (the CAM06/CAM07 run now
   going), scored by `bench/sandbox_eye.py score --from-db`, against gates written before the change is scored. The
   frozen `sandbox-blind-v1` chooses no threshold.

## Caveats

- The sandbox figures are one reviewer's reading of 120 plates, mostly on CAM06, from 55 vehicles or fewer. The
  reviewer was right on 222 of 226 of our own plates (`review_truth.md`), and `blind_errors.md` argues some answers may
  be the reviewer's slips. Per-row counts are small: read them as directions.
- Our own plates are synthetic, in one clean font, painted on stock footage. Real plates' errors (fonts, dirt, glare,
  two-line layouts, night IR) are not in them, and AMD-TRAF-002 sits near its ceiling. Compare rules with each other
  there, not with the sandbox.
- `track_replay.md` rebuilds vehicle passes from logged tracks and imitates lower rates by thinning reads, not frames.
  Its low-rate numbers are directions to confirm live.
- `detect_size.md` scores single sampled frames with no tracker, on a CPU shared with a live worker. It compares
  sizes; it does not give the product's capture or its GPU cost.
