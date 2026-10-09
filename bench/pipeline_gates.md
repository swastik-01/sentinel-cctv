# Plate pipeline changes: decisions and adoption gates (pre-registered)

Drafted 2026-09-26 16:10-16:16 IST, then checked and corrected 16:30-16:47 IST (the corrections are listed at the end).
Both were done after four analyses came back and before any change below was built into the product or scored live:
`bench/results/ocr_baseline_blind.md` (the blind-read set frozen), `blind_errors.md` (where the 30 misses fall),
`ocr_fix_trials.md` (25 no-training OCR changes), and `pipeline_review.md` with `track_replay.md`, `detect_size.md`,
`pipeline_diag.md` and `ocr_padslot.md`. A change is adopted only if it passes every gate listed for it. Gates are not
changed after a result is seen; a change that fails is recorded as failed in `bench/results/pipeline_gates_results.md`.
The OCR fine-tune keeps its own gates (`bench/ocr_gates.md`, Addenda 1 and 2).

## Decision for the 27 Sep submission: no product change

Nothing below goes into the product before the submission, and the pack describes the shipped build.

1. **No change has a real-plate gain.** Re-reading the stored crop repeats 13 of the 14 misreads on Sentinel's side
   (`blind_errors.md`), so the pipeline changes move capture and reads per vehicle, not the exact rate the pack quotes.
   Their evidence is our own synthetic plates, replayed offline. None of the 25 OCR trials passed its own gain rule on
   real plates (`ocr_fix_trials.md`), and the trials were chosen on the frozen test set.
2. **Every number in the pack was measured on the shipped build**: `anpr_eval_current.md`, `latency.md`, the capacity
   model, the 90 of 120 blind check. Changing the code the night before would make the pack describe a build that no
   longer runs, and fixing that means re-measuring and rewriting documents that another workflow is editing now.
3. **No gate can pass by 27 Sep 12:00 IST.** Each needs the live own-feed A/B (block L below) on a laptop with the GPU
   and CPU free: about 2 hours of windows for G2 alone, then a pass over every document that describes the tracker.
   Tonight the GPU belongs to the CAM06/CAM07 capture, which is the fresh real data below and should run overnight; the
   CAM01-CAM30 rotation and the fine-tune share the CPU; and CLAUDE.md records that this laptop's A/Bs under load are
   noise.
4. **An edit now would contaminate the fresh real data.** `scripts/rotate_worker.py` starts a new worker for every
   group, and each new worker imports the working tree. The CAM06/CAM07 sightings being captured now are the fresh
   real test data below; they must all come from one build.

What goes ahead before the submission is evaluation only:

- **E1 (done 16:14-16:40).** `bench/ocr_ab.py` applies the worker's full gate, `check_read`, letters-from-digits rule
  included. The shipped model under it, all four frozen sets (`bench/results/ocr_baseline_checkread.md`):
  sandbox-blind-v1 88/120 exact, 119/120 passing, 31/120 passing and wrong; sandbox-v1 25/28, 3/28 passing and wrong;
  reject-v1 0/23 passing (the older harness counted 23/23); ownfeed-v1 5308/5528, 205/5528 passing and wrong.
- **E2 (done 16:36).** `scripts/anpr_eval.py` compared the REAL `ocr_conf` column with 0.9, so every sighting stored at
  exactly 0.9 (three agreeing reads) fell into the 0.7-0.9 band, the fault `pipeline_diag.py` had. Fixed by rounding to
  3 decimals, as the review page bands. `bench/results/anpr_eval_current_recheck.md` re-scores the window of
  `anpr_eval_current.md`: only the confidence tables change. On the two stock-footage cameras the >= 0.9 band holds
  728 of 874 sightings, 719 exact (98.8%), where the old table put 499 in it; 229 sit at exactly 0.9. The drawn
  AMD-AMC-001 has 8 of 26 exact at >= 0.9: three agreeing reads can repeat a misread, as on the sandbox.
  `anpr_eval_current.md` is left as generated (it is cited, and its headline numbers are unchanged); no document
  quotes its confidence table.
- **E3, E4.** New blind reviews, a second reader, and the freezes `sandbox-fresh-v1` and `sandbox-blind-v2` (next
  sections).

Until E3 or E4 changes it under the rules below, the quoted real-plate figure stays 90 of 120 stored plates exact (one
blind reviewer); 88 of 120 is the single-crop re-read. No AI-assistant estimate of a corrected figure is quoted.

## Decisions for the finale (12-13 Oct)

| Id | Change (source) | Decision | Why |
|---|---|---|---|
| G0 | Instrumentation: per-camera decoded, retrieved and analysed fps; richer TRACK_LOG with per-read times (`pipeline_review.md` rank 0) | Adopt first | The sandbox's 1.6 fps is not yet split between frame delivery and the laptop, and the replay cannot emulate a hold without per-read times. G2b, G5 and G6 depend on it. No accuracy effect |
| OCR | Indian-format fine-tune `ft1` (`ocr_gates.md`) | Adopt if its gates pass | The model makes 13 of the 14 Sentinel-side misreads. It is the only lever on the stored exact rate |
| G2 | Tracker: one read >= 0.9 accepted at any analysis rate (rank 2); a length tie broken by summed confidence (rank 3b) | Adopt if G2 passes | Small code, low risk. At 2.2 fps on our own feeds the replay puts capture at 65.3% and 84.1% against 51.3% and 71.1%, precision unchanged; the tie-break gave 7 fixes and 1 break on 14 tied tracks. The claim stays on our own feeds |
| G2b | A 2-read track held longer for a third read (rank 3a) | Re-specify after G0, then gate | As proposed (max(1 s, 4 analysis intervals)) it equals the shipped hold at 4.5 fps, where the replay found its 4 fixes, and the 24 Sep logs have no per-read times to size a hold |
| G3 | Confidence marking (rank 4, **amended**) | Adopt if G3 passes | No accuracy change. It is the honest way to use a 75%-exact figure. Amended: nothing is suppressed; see G3 |
| G4 | Evidence crop from a read that agrees with the stored plate (rank 7) | Adopt if G4 passes | The crop shown as evidence should show the plate that was stored; at least 4 of 120 sandbox sightings disagree today |
| G5 | Plate detector at 960 on plate cameras (rank 1) | Adopt only if G0 shows headroom and G5 passes | Largest measured capture effect on our clips (640 reads 61.8% of painted plates per frame, 960 reads 88.2%), but it costs GPU, precision per read, and every capacity number |
| G6 | Raise the analysis rate on plate cameras; classical finder off there (ranks 5 and 10) | Investigate after G0; adopt only through G6, and only after G2 | The fix depends on what G0 finds. Without G2's one-read rule, lifting a camera from below 2 fps to 2-3 fps loses capture (replay: 65.2% at 1.5 fps against 51.3% at 2.2 on AMD-TRAF-001) |
| - | Length chosen by summed confidence instead of count (`blind_errors.md` fix 3) | Drop | Unmeasured; one confident short read would outvote two full-length reads. The tie-break alone (G2) was measured |
| - | Reject the raw shape two series letters + three digits (rank 8, `blind_errors.md` fix 3) | Drop for the finale | Found post hoc on the test set; reaches about 3 of 120; 1 of the 4 such single reads on the blind set was a right nine-character plate, and 29 of the 120 true plates have nine characters. 5 of the 7 shortened stored reads were below 0.9, so G3 marks them; 2 were at 0.90 and 0.95. The fresh data will be too small to confirm it |
| - | TTA with the tracker vote, K=5 or K=8 (`ocr_fix_trials.md`) | Drop for the finale | No pre-set gain rule passed; the held-out estimate is about +3 plates of 120; the OCR's CPU cost rises 7-10x on a laptop whose analysis rate is the bottleneck; a fine-tuned model would need it re-measured. The suggested integration (variant reads fed to `PlateDeduper.offer` as extra reads) is wrong: 9 reads from one frame close the track at `confirm_reads`, pass `min_reads`, and, when they agree, get the unanimous-vote boost (0.99) on a single glimpse. Any later attempt combines the views into one read per crop before the tracker |
| - | One sighting per pass with a late correction (rank 6) | After the finale | M effort and a new ingest update path (spool replay, alert re-evaluation) for +5 fixes of 873 own-feed passes |
| - | Vote weights from size, sharpness or per-character probability (rank 9) | Drop | Indirect evidence only; squared and plain confidence give 6 and 5 fixes, no real difference |
| - | CLAHE, gamma, upscaling, other hub models, ensembles, slot-vote and mean-probability TTA, two-line halves, rotate/deskew, pad-slot confidence, OCR every Nth frame, equal vote weights, `SINGLE_READ_CONF` 0.9, a wider crop, IoU association | Drop | Measured worse or neutral, or no evidence (`ocr_fix_trials.md`, `pipeline_review.md` "Not recommended"). Rotation +3 deg (7 fixed, 6 broken) stays a hypothesis |
| - | Review page: normalise the typed reading, warn when it is not a valid registration (`blind_errors.md`) | Drop the warning; score both ways | A warning nudges an unsure reviewer into guessing a valid plate. Scoring reports the reading as typed (primary, as for v1) and after `normalise_plate` (secondary) |

**Deadline.** A finale change passes all its gates by **9 Oct 2026 18:00 IST**, or it waits until after the finale.
If one is adopted, every document that describes the tracker, the detector, the alerts or the capacity figures is
updated in one pass (CLAUDE.md, "change the story everywhere at once"), and the HLD version is bumped.

## Shared blocks

**Build.** Each change is its own commit and sits behind a setting whose default is the shipped behaviour. An A/B
flips the setting, never the code. The commit and the settings are written into every results file.

**T: tests.** `pytest` passes: every existing test plus the new ones named under each gate. `smoke.py` 34/34 and
`security_checks.py` 20/20, run before any live window (they write to the database), and `npx tsc --noEmit -p .` if the
web changed. `smoke.py` gets no new checks.

**L: live own-feed A/B.** One worker on AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001 and AMD-AMC-001 under the conditions of
`bench/results/anpr_eval_current.md` (HW_DECODE=auto, object detection on, about 4.5 analysed fps per camera), with
`STATIC_TEXT_WINDOW_S=0` and every other setting at its default, on the GTX 1650 Ti laptop on AC power. No other
worker, rotation or training job runs, and the CPU is below 20% busy before the first window. Windows are 10 minutes
from 60 s after the worker's first status line, in the order A B A B (A = shipped setting, B = candidate) in one
session, the worker restarted between windows. Only AMD-TRAF-001 and AMD-TRAF-002 are scored. Per window:
- `scripts/anpr_eval.py --camera AMD-TRAF-001 --camera AMD-TRAF-002 --since ... --until ...` (with the E2 fix): exact
  over sightings, within one character, capture of plates shown >= 1 s, and the confidence table;
- `bench/pass_capture.py` (to be written and run on the A windows before any B window is scored): **passes captured**
  = exact sightings after merging sightings of the same plate less than 30 s apart (the clips loop every 60 s), per 10
  minutes; **extra sightings** = sightings less than 30 s after an earlier one whose plate is within 2 edits. It is
  needed because `anpr_eval.py`'s capture counts a plate read in any loop, so over 10 loops it saturates and cannot
  see a per-pass change;
- `scripts/latency_report.py` (first read to alert, one clock), with the same watchlist in both arms;
- analysed fps per camera: the median over the window's status lines.
Arms are pooled over their windows. "Pooled" means both stock-footage cameras together.

**O: frozen OCR sets.** `bench/ocr_ab.py` on `sandbox-blind-v1`, `sandbox-v1`, `reject-v1` and `ownfeed-v1`, with the
worker's `check_read` as its gate (E1; baseline `ocr_baseline_checkread.md`). O applies only to changes that alter what
a single read returns or whether it passes.

**F: fresh real sets.** `sandbox-fresh-v1` and `sandbox-blind-v2`, defined in the next section.

**R: real tripwire, concurrent.** For a change to the tracker (G2, G2b) or the detector (G5), if the sandbox is
reachable before 9 Oct: CAM06 and CAM07 on one worker in alternating 20-minute windows, A (shipped) and B (candidate),
until each arm has at least 60 stored plates (about 6 hours at the 26 Sep rate). A reader reads every sighting of the
session blind on the Plate review page in time order, not knowing the arm. Report per arm: stored exact as typed, with
Wilson and group-bootstrap intervals, one-read sightings apart, and plates stored per analysed hour (counts only). The
change is withdrawn if B's exact rate is more than 10 points below A's. Both arms see the same part of the footage
loop, which a comparison with v1 would not. R detects gross harm only: with 60 plates an arm, a change that does
nothing is withdrawn by chance about one time in ten (more, since vehicles repeat), and a gain is never claimed from
it.

## Real labelled data: new blind reviews and a second reader

The only way to add real labelled plates is the Plate review page on sandbox sightings: the organisers' footage is
never downloaded, and their crops are never used to train or tune.

**Capture.** The CAM06/CAM07 capture (`data/rotation-capture`, started 14:58 and again at 15:51 IST for 100 minutes)
is the source. At 16:41 IST the sandbox cameras held 95 sightings stored after v1 that nobody has reviewed (CAM06 64,
CAM07 31; 64 at confidence >= 0.9). The current run stored 18 in its first 50 minutes (about 22 an hour, at 1.4
analysed fps per camera); an earlier run stored 51 between 13:23 and 14:00. The yield follows the footage: the sandbox
replays recorded footage on a loop of unknown length. CAM06 and CAM07 gave 119 of the 120 reviewed plates; the cameras
the registry flags as plate-capable (CAM12-16) gave 0-1 reads each (`sandbox.md`). The fastest way to more plates is
to run these two cameras longer: overnight, alone, with the same working tree, and with the rotation over the other
cameras stopped once its own purpose is done. No product edit is made until this capture stops.

**Readers.** Reader 1 is the team member who read v1 (account `admin`). Reader 2 is a different person, signed in as
`auditor` (no reviews yet). The blind queue shows only the crop; after each typed reading the page reveals Sentinel's
read, never the other reader's. So a vehicle the loop replays is not blind for a reader who saw it before: such
*seen* vehicles are reported apart (below).

**sandbox-fresh-v1.**
- **Rows.** Every sandbox sighting (camera code `^CAM[0-9]{2}$`) with a frame time after 2026-09-26 07:55:27 IST (the
  last sighting in v1), with at least one blind review at freeze time. They were stored by the worker as it stood on the
  afternoon of 26 Sep: the tree committed as e18331a, plus the uncommitted `stream.py` reconnect backoff. The report
  records this. The crop is the stored best crop, copied with its sha256 as v1 was.
- **The answer.** Readings are upper-cased with spaces and punctuation removed. With one reader, their reading is the
  answer (as in v1), and the row is marked single. With two readers: equal readings are the answer. Unequal readings
  are settled by the two readers together from the crop and their two readings only, never Sentinel's read, and
  recorded in `data/ocr-eval/sandbox-fresh-v1/adjudication.csv`. A disagreement not settled by the freeze leaves the
  row out, and the report counts it and gives the rate with those rows counted as misses too. A row either reader calls
  not a plate or unreadable is left out and counted.
- **Groups.** `ocr_sets.same_vehicle` over fresh and v1 rows together (true plates within one edit, or the same camera
  within 10 s). A fresh row linked to a v1 row is a *seen* vehicle; the rest are *new* vehicles. Every result is given
  for all rows and for new vehicles. Anything chosen after looking at v1 is judged on new vehicles only.
- **Freeze.** Once, with a new `bench/ocr_sets.py fresh` builder that refuses to overwrite and has a `--dry-run` that
  prints counts without writing (so it can be tested without freezing), by **27 Sep 2026 10:00 IST**, from the reviews
  done by then. This happens before any candidate (the fine-tune included) is scored on these crops, and before anyone
  looks at which stored reads were right beyond what the review page shows a reader. Reviews after the freeze become
  `sandbox-fresh-v2`, a separate freeze; rows are never appended to a frozen set.
- **Report.** `bench/results/sandbox_fresh.md`, counts and rates only (plate text stays under `data/`). It gives the
  stored read's exact rate as typed (primary), within one character, and exact after normalising the reading
  (secondary), each with Wilson and group-bootstrap 95% intervals, by confidence band (>= 0.9 against < 0.9, compared
  as the review page does), by camera and by one-line or two-line layout, and the two readers' exact agreement on plates
  both read. The conditions: the build, the cameras, the capture windows, and a laptop shared with other CPU jobs.
- **Use in the pack, decided now whatever the result.** If `sandbox_fresh.md` is written by 27 Sep 12:00 IST, the
  documents quote its stored exact rate beside 90 of 120, with its conditions, in one pass after the document workflow
  now running has finished. If not, it is quoted from the finale on. It is never pooled with v1: the loop replays
  vehicles, so the two overlap.

**sandbox-blind-v2 (the answer key for v1, checked).**
- Reader 2 reads **all 144** v1 sightings blind (the 90 hits, the 30 misses and the 24 hoarding crops), in the page's
  order, filtered to the v1 window (25 Sep 21:00 to 26 Sep 07:56 IST). Reading only the 30 misses would let corrections
  run one way, in Sentinel's favour.
- The answer and adjudication rules are those of `sandbox-fresh-v1`. Reader 1 saw Sentinel's read after typing each
  v1 plate, so the report says the adjudication was not free of that memory. It is frozen beside v1 by `ocr_sets.py`
  (a `blindv2` builder, same refusals); v1 is never edited. It reports stored exact on v2 next to v1, how many of the
  90 hits and of the 30 misses changed, and the readers' agreement.
- **Use in the pack, decided now whatever the result.** If v2 is frozen by 27 Sep 12:00 IST with reader 2 a different
  person who read all 144, and every disagreement settled without Sentinel's read, the documents give the v2 figure as
  the headline, with 90 of 120 beside it as one reader's. Otherwise 90 of 120 stays and v2 is reported from the finale
  on. A second pass by reader 1 is a re-read by the same person and changes nothing.

**Order of work.** Reader 1 reads the fresh sightings now (about 14 s a plate: v1's 144 took 34 minutes, 12:28-13:02),
and again in the morning before 10:00. Reader 2 reads the 144 v1 sightings first (they check the quoted number), then
the fresh ones. If time allows, reader 2 also reads about 50 AMD-TRAF-002 sightings blind, so `bench/review_truth.py`
measures their own error against known plates as it did reader 1's (222 of 226).

## Gates

### G0: instrumentation

- **Change.** The worker's 30 s status line gives, per camera, decoded, retrieved and analysed fps, plus reconnects
  since the last line. TRACK_LOG adds dropped tracks (flagged) and, per read, its wall time, box width, sharpness,
  detector source and raw text. The worker also counts stored sightings by detector source per camera (counts only,
  sandbox included). **The worker refuses to start with TRACK_LOG set when any assigned camera code matches
  `^CAM[0-9]{2}$`**, so the own-feeds-only rule is enforced in code.
- **T**, with new tests: the status line's fields; the refusal on a sandbox camera code; a dropped track in TRACK_LOG.
- **L wiring**, one A B pair: no worker error; the fields are present; B's analysed fps is at least 95% of A's; the
  pooled exact rate is >= 93.0%, and AMD-TRAF-002 captures >= 58 of 68 plates shown >= 1 s (the wiring bar of
  `plate_gate_gates.md` A3).
- **Then**, on the sandbox (counts only): CAM06/CAM07 for at least 60 minutes. Decoded fps against analysed fps decides
  G6's direction and whether G5 is affordable. On our own feeds, a TRACK_LOG run at DETECT_FPS 5 and 2.5 gives G2b its
  replay.

### OCR fine-tune

Governed by `bench/ocr_gates.md` Gates 0-3 and Addenda 1-2. Addendum 2 makes the harness gate the worker's
`check_read` (done, E1), adds `sandbox-fresh-v1` to Gate 1, and rules out adoption before the submission whatever `ft1`
scores. At 16:32 IST `ft1` was in epoch 3 of 12. Epoch 1 took 50 minutes and epoch 2 15; at Idle priority its speed
follows the laptop's load, and the first 23 steps of epoch 3 averaged about 40 s each. It finishes tonight only if the
CPU is left to it. It can be scored on the frozen sets when it finishes, but not on `sandbox-fresh-v1` until that set
is frozen.

### G2: one-read acceptance at any rate, and the length tie-break

- **Change.** Two settings in `PlateDeduper`, each off by default:
  - (a) a one-read track is stored at confidence >= 0.9 at any analysis rate; below `SLOW_FPS` the shipped >= 0.6
    still applies;
  - (c) when two lengths tie on count, the vote takes the length with the higher summed read weight.
  The three-read confidence boost and the API's refusal of a fuzzy alert on a one-read sighting are unchanged. B is both
  on. (The one-read decision is a small pure function, so the replay below calls the product's code.)
- **T**, with new tests: a 0.95 one-read track at 4.5 fps is stored and a 0.85 one is not; a 0.65 one-read track at
  1.5 fps is stored (shipped); a tie is broken by weight; with both settings off, every existing tracker test passes
  unchanged.
- **Code check, before any live window.** `bench/track_replay.py` calling the product's decision function and `vote`
  on the two 24 Sep logs reproduces `track_replay.md` exactly: at 2.2 fps with one read >= 0.9 accepted, capture
  260/398 and 1134/1348; on the 14 tied tracks, 7 fixes and 1 break. This checks that the product code does what the
  replay's rules did; it is not new evidence.
- **L**, the pair A B A B at `DETECT_FPS=5`, then A B at 2.5 and A B at 1.5:
  - exact over sightings: at 5 fps, B >= A - 1.5 points pooled and B >= A - 3 points per camera; at 2.5 and 1.5,
    B >= A - 2.5 points pooled;
  - passes captured: at 2.5 fps, **B above A on both cameras** (the change's purpose; the replay predicts about +14 and
    +13 points at 2.2 fps); at 5 and 1.5 (where only (c) acts), B >= 98% of A on each camera;
  - extra sightings: B no more than A + 1 point of sightings;
  - median latency: B <= A + 0.5 s at every rate (neither setting holds a track longer, but one-read sightings close
    at the end of the hold);
  - analysed fps: B >= 95% of A.
- **O / reject-v1.** Not applicable: the tracker never sees a read that `check_read` drops, the hoarding's included.
- **R** applies. If B has at least 15 one-read sightings at >= 0.9 and under two thirds of them are exact, (a) is
  switched off.
- **Claim if adopted.** Our own feeds only: "at 2.5 analysed frames per second, passes captured rose from X to Y on
  stock footage with synthetic plates". No real-plate gain.

### G2b: a longer hold for a third read (after G0)

Not built until G0's TRACK_LOG (with per-read times) has been recorded on our own feeds at DETECT_FPS 5 and 2.5. An
addendum here then fixes the hold from that replay, before any B window is run, and the change passes the G2 blocks
with the latency bound replaced by: median B <= A + 0.5 s at 5 fps and <= A + 1.5 s at 1.5 fps. If no hold shows fixes
> breaks on the replay, G2b is dropped.

### G3: confidence marking

- **Change.** A sighting stored below 0.9, or a watchlist alert raised on a one-character (fuzzy) match, is marked
  "check the crop" in alerts, search and the journey view. It is listed under a "below 0.9, unchecked" filter on the
  Plate review page. Each sighting also stores its read count (`reads`) and the vote's agreement, through
  `upgrades.py`. **No alert is suppressed and no alert rule changes.** The review suggested alerting only on exact
  matches below 0.9; that would lose the fuzzy alert that catches a one-off read of a wanted plate (17 of the 120
  blind-checked plates were one off). A marked alert costs an operator one look at the crop instead. The 0.9
  threshold is the review page's band, and it is fixed now. `ocr_conf` is REAL, so the comparison is made as the
  review page makes it (`>= real '0.9'` in SQL, or rounded to 3 decimals in Python).
- **T**, with new tests: a 0.85 sighting is marked; a 0.90 one, stored in the REAL column and read back, is not; a
  fuzzy alert is marked; alert counts are equal with the marking on and off on the same ingests; the `reads` column is
  written; `security_checks.py` 20/20, with the audit rows still free of plate text.
- **L wiring**, one A B pair: in B, the marked share equals the share of scored sightings below 0.9 in
  `anpr_eval.py`'s confidence table (exact equality; E2's fix is what makes this check possible); median latency
  B <= A + 0.2 s.
- **O, reject-v1, speed of the worker.** Not applicable (no read changes; the worker is untouched).
- **F.** On `sandbox-fresh-v1`, report exact and within one character by band. "Confidence separates right from
  wrong reads" is claimed only if the group-bootstrap 95% interval of (exact at >= 0.9) - (exact below 0.9) is above 0
  on the fresh set; the marking ships either way, as a review aid.

### G4: evidence crop

- **Change.** A sighting's crop comes from the highest-confidence read whose text equals the voted plate, ties going to
  the wider box. If no read equals it, the crop is chosen as today. The stored plate and stored confidence are
  unchanged.
- **T**, with new tests: a track whose best read disagrees with the vote keeps an agreeing read's crop; the stored
  plate and confidence are the same with the setting on and off.
- **L**, one A B pair at 5 fps. The share of sightings whose crop, re-read by `ocr_ab.py`'s reader, equals the stored
  plate is B >= A. The median crop width is not more than 5% narrower. Exact over sightings is B >= A - 1.5 points
  pooled (it should be identical; this is a wiring check). Analysed fps B >= 95% of A.

### G5: plate detector at 960 on plate cameras

- **Precondition.** G0 has shown what limits the analysis rate on CAM06/CAM07. If the plate worker is GPU-bound at
  640, G5 is run only on the finale hardware.
- **Change.** A worker setting `PLATE_IMGSZ` (640 by default). At the finale, plate cameras run on their own worker at
  960. The plate cameras are those with evidence, not the registry's `anpr_viable` flag (wrong on the sandbox for CAM06
  and CAM07): stored plate reads with boxes >= 80 px in the last hour.
- **T**, with new tests: the setting reaches the detector call; the default stays 640.
- **L**, A B A B at 5 fps:
  - passes captured, B above A on both cameras, pooled over the two pairs;
  - exact over sightings, B >= A - 1.5 points pooled;
  - analysed fps, B >= 90% of A;
  - the not-a-plate and fixed-text drop counts and `anpr_eval.py`'s non-ground-truth plates are reported for both arms.
- **O.** `reject-v1` is not affected (the OCR and gate are unchanged); the drop counts above stand in for it live.
- **R** applies, with plates stored per analysed hour at 960 >= 640 (counts only).
- **Capacity.** `bench/capacity.py` is re-run with the plate model at 960 on the GTX 1650 Ti. If G5 is adopted, the Plan
  for Scale says which cameras run at 960 and takes its numbers from that run.
- **Detector replacement.** `bench/detector_gates.md` compares YOLOX with the incumbent at 640. If G5 passes first, an
  addendum written before any YOLOX candidate is scored adds the incumbent at 960 as a reported comparison. The
  replacement should not lose capture against what actually runs.

### G6: analysis rate on plate cameras

- **Only after G0, and after G2 is adopted.** If frames reach the worker at >= 5 fps on a plate camera that is analysed
  below 3 fps, the worker is the limit. The candidates are then: plate cameras first in each tick's batch; a lower
  `OBJECT_FPS` on them; and `DETECTOR=yolo` on a plate-camera worker (a setting that exists; no code). If frames do not
  arrive, no worker change is made, and the stream's reconnect handling is where the work goes (out of scope here).
- **L** with 8 own-feed cameras on the worker (the four above plus four synthetic ones), so the rate falls as on the
  sandbox:
  - analysed fps on AMD-TRAF-001/002, B >= 1.2 × A;
  - passes captured, B above A on both;
  - exact over sightings, B >= A - 1.5 points pooled.
  For `DETECTOR=yolo`, also AMD-POL-001 and AMD-AMC-001 still stored plates (their drawn plates are what the classical
  finder is kept for).
- **R** applies: plates stored per analysed hour on CAM06/CAM07 not lower.

## What may be claimed

Until a fresh-set or v2 result changes it under the rules above: real-plate accuracy is 90 of 120 stored plates exact,
read blind by one team member on 2 sandbox cameras (CAM06, CAM07; 1 plate from CAM12). Capture on real plates is
unmeasured. A pipeline change adopted through G2-G6 is described by what it did on our own feeds, with their conditions.
No change here is described as improving real-plate accuracy. Only the fine-tune can claim that, and only through
`ocr_gates.md`.

## Corrections made at the 16:30-16:47 check

Nothing had been built or scored against these gates in between, so they remain pre-registered.

1. **Times.** The draft and `ocr_gates.md` Addendum 2 named 16:35 and 16:40 IST in files saved at 16:14-16:16.
   Corrected to the times the work was done.
2. **Shortened reads.** The draft said all 7 shortened stored reads were below 0.9. From the frozen manifest, 5 were;
   2 were stored at 0.90 (three agreeing reads) and 0.95. The decision to drop the shape rule stands on its other
   reasons.
3. **G2 split.** The draft bundled the third-read hold (b) into G2. As specified it equals the shipped hold at 4.5 fps,
   and the logs cannot size a hold, so it became G2b, after G0. The draft's replay step, which fed the product's
   `PlateDeduper` with these logs, could not work for a time-based hold; the code check now covers (a) and (c) only.
4. **Fresh-data counts.** The draft gave 80 unreviewed sightings (51 at >= 0.9), 30-50 an hour and a 12-hour loop.
   At 16:41: 95 unreviewed, 64 at >= 0.9 (compared as REAL); about 22 an hour on the current run; the loop's length is
   not known.
5. **E2.** `anpr_eval.py`'s confidence bands had the REAL fault. G3's wiring check depends on those bands.
6. **R.** The draft withdrew a change if its real exact rate fell below 66.6% (v1's lower bound). v1 comes from another
   part of the footage loop, and the 25 Sep evening and 26 Sep morning runs' rates differ (`sandbox_daynight.md`;
   the same looping footage, so the difference is the loop, not the light), so R now compares concurrent A and
   B windows.
7. **Quoting.** The draft quoted the fresh figure only if it fell outside v1's interval and otherwise left it to the
   team, which let the choice follow the result. Both fresh and v2 figures now have a rule fixed in advance.
8. **Reader 2's order.** v1 first, since it checks the number the pack quotes.
9. **G4.** The replay step was removed (the logs carry no crops); a unit test covers it.
10. **`ft1` status** updated from the log.

## Corrections after the check, 26 Sep evening

No gate, threshold, set or rule changed, and nothing had been built or scored against these gates.

11. **Security checks.** `security_checks.py` has had 20 checks since the camera-quality check went in (commit of
    26 Sep 15:01 IST), before this file was drafted; T and G3 said 19/19 and now say 20/20.
12. **Quoting.** The decision section named the AI assistant's estimated corrected figure while saying it is never
    quoted; it now names no figure.
13. **The two sandbox runs** are named by run (the 25 Sep evening run, the 26 Sep morning run), not day and night: the
    sandbox replays the same looping footage (correction 6, `sandbox_loop.md`).
14. **The fresh set overlaps v1, measured before the freeze** (2026-09-26 17:59 IST; one fresh review recorded by then, its verdict not looked at): 84 of 173 fresh sightings (49%) repeat a reading stored in v1's window exactly (`sandbox_loop.md`), a lower bound on seen vehicles. The rule above already reports all rows and new
    vehicles; wherever the pack quotes the fresh rate, it gives the new-vehicle rate beside it and says the set
    re-reads the same looping footage. No threshold, set or rule changed.
15. **Note 14's boundary, corrected** (2026-09-26 19:18 IST). Note 14 counted from
    07:55:27.000, which took in v1's own last sighting (07:55:27.55): its "one fresh review" was that sighting's v1
    review, so no fresh sighting had been reviewed. From 07:55:28, with the CAM06/CAM07 capture ended at 18:07: 90 of
    188 fresh sightings (48%) repeat a reading stored in v1's window exactly (`sandbox_loop.md`). The fresh
    builder (`bench/ocr_sets.py fresh`) leaves v1's sightings to v1 in the same way. No threshold, set or rule changed.
16. **G3 result, 8 Oct 2026 09:30 IST.** Built as specified (API setting `CONFIDENCE_MARKING`, `marking.py`; `reads`
    and `agreement` columns; marks in alerts, search, journey, the live toast; the review page's "below 0.9, unchecked"
    filter). T: 7 pytest tests plus `bench/g3_check.py` live with marking off and on, all passed; alert counts equal.
    L wiring: A 09:04:46-09:14:46 (off), B 09:19:34-09:29:34 (on); B's marked share 161 of 748 = anpr_eval's
    below-0.9 count exactly; median latency B 1.68 s <= A 2.25 s + 0.2 s (4 and 3 alerts). F not run: no fresh set.
    **PASS; adopted, default on.** Conditions and the analysed-fps caveat in `bench/results/g3_wiring.md`. No other
    gate was run; the fine-tune stays not adopted (`ocr_ft1.md`). `bench/results/pipeline_gates_results.md` indexes this.
