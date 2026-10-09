# Not-a-plate gate: adoption gates (pre-registered)

Written 2026-09-26 10:45 IST, before the rule below is built into the product and before any classifier is trained.
Two stages, adopted separately: **A**, a rule on the OCR read (for the 27 Sep submission if it passes in time), and
**B**, a plate / not-a-plate image classifier (for the 12–13 Oct finale). No gate is changed after a result is seen; a
stage that fails is recorded as failed.

**What the evidence so far is.** `bench/results/plate_gate.md` (09:42 IST) compared 17 rules; a second run at 10:30
IST reproduced every count exactly. Rule `1e-k2` was picked *after* looking at reject-v1, the eye-labelled stored
sightings and probe seed 7, so those numbers are exploratory: they choose the rule, they do not confirm it. The gates
below are confirmatory: the product code must reproduce the replay, then the rule meets data nobody has looked at yet
(new probe seeds, the team's blind labels, live runs). The real non-plate evidence is thin: reject-v1 is 23 crops of 3
texts (phone numbers on hoardings), all on one sandbox camera. Sandbox crops are test-only, never trained on.

## Stage A: the digit-repair rule (`1e-k2`)

**Rule.** Drop a read when `normalise_plate` had to turn two or more digits into letters to fit a plate layout (state
code, series letters and BH letters counted together). Applied per read in the worker after the existing gate (weakest
character ≥ `min_ocr_conf` and `looks_like_indian_plate`), before the tracker. Built as a public helper in
`services/common/sentinel_common/plates.py` that returns the count (`normalise_plate`'s output unchanged), one condition
in `worker.py`, and a setting that can switch it off in the field.

**A0: implementation parity.** `bench/plate_gate.py` switched from its replay to the product helper. On every read of
reject-v1, sandbox-v1, ownfeed-v1, the 145 labelled sightings, `data/ocr-train/test.csv` and probe seeds 7 and 11: the
helper's count equals the replay's (0 mismatches) and `normalise_plate`'s output is unchanged (0 differences).

**A1: frozen sets reproduce**, with the product helper: reject-v1 23 of 23 caught; stored not_a_plate 24 of 24;
sandbox-v1 0 of 25 exact reads lost; stored sightings 0 of 92 exact and 0 of 4 one-off lost; ownfeed-v1 at most 4 of
5,307 exact reads lost and 0 of 128 vehicles gone; synthetic held-out plates at most 1 of 1,391 GJ, 0 of 180 other
states, 0 of 152 BH.

**A2: fresh probe.** Seeds 101, 202 and 303, 300 crops per kind, never run before this file: per seed the rule leaves
at most 5 of 2,400 crops passing, and over the three seeds at most 20% of what the current gate lets through.

**A3: tests and the live product.**
- `pytest` passes with new unit tests: a digits-only phone-number read is dropped; an exact GJ plate is kept; a GJ plate
  with one state letter read as a digit is kept; an exact BH plate and a BH plate with one misread are kept; a read whose
  two state letters are both digits is dropped; and the known cost (two series letters read as digits) is dropped and
  the test says so.
- `smoke.py` 34/34 and `security_checks.py` 19/19. Never run a plain `demo_prep.py` while the 145 sandbox sightings wait
  for the blind check: it deletes them.
- The worker with the rule on, 10 minutes on AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001 and AMD-AMC-001 under the
  conditions of `bench/results/anpr_eval_current.md` (`STATIC_TEXT_WINDOW_S=0`): no worker error; `anpr_eval.py` pooled
  stock-footage exact ≥ 93.0% and AMD-TRAF-002 capture of plates shown ≥ 1 s at least 58 of 68. These are wiring
  checks, not a measurement of the rule (`anpr_eval_current.md` has 95.3% and 62 of 68).

**A4: deadline.** A0–A3 all green by **27 Sep 2026 12:00 IST**, or Stage A waits until after the submission and the
pack says nothing about it. The documents change in one pass after the running document update has finished, never
at the same time as it.

**A5: after it ships** (checked when the data exists; a failure reopens the rule, goes into `plate_gate.md`, and the
documents are corrected):
- The team's blind check (Plate review, prefix `CAM`): none of the 24 crops the rule drops is typed as a plate (exact,
  one off or wrong).
- Live monitoring: the worker logs, per camera, how many reads the rule dropped (a count, no text). On a
  plate-readable sandbox camera (CAM06, CAM07) over at least 30 analysed minutes, drops above 2% of the reads that
  pass the existing gate suspend the rule (setting off) until the drops are reviewed.

**What may be claimed.** "Reads that needed two or more digits turned into letters to fit a plate layout are dropped.
On the organisers' sandbox this removes all 24 stored sightings of a hoarding's phone number (3 texts, one camera) and
none of the 92 stored plates checked as exact; on our own feeds it drops 4 of 5,307 correct reads and no vehicle."
Always with: the non-plate evidence is 3 texts on one camera, and the sandbox plates were checked by the AI assistant,
not blind, until the team's check is done. Never "eliminates false plates".

## Stage B: plate / not-a-plate classifier

**Candidate (fixed now).** A small CNN (about 100k parameters: conv blocks 16/32/64/96, global average pool, one
logit), trained from scratch with no pretrained weights, on the OCR's own 64×128 RGB input made from the worker's padded
crop. PyTorch (BSD-3) in `D:\GitHub\det-train`, exported to ONNX, run on CPU by ONNX Runtime (MIT) after Stage A and
before the tracker. Off by default behind a setting until adopted.

**Training data**, one manifest row per image (source, URL, licence, author where given, sha256, split); nothing else
may enter:
- Positives: synthetic Indian plates rendered with SIL OFL fonts only (one- and two-line; white, yellow, green, black);
  real plate crops from the train splits of the detector's Tier A sets (`bench/detector_gates.md`): CCPD (MIT), UC3M-LP
  (CC BY 4.0), Open Images plate boxes (CC BY 4.0; images listed CC BY 2.0), Nepali private plates (CC BY 4.0).
- Negatives: synthetic signage in OFL Latin and Noto Sans Gujarati (phone numbers, shop words, timestamps, overlays);
  camera-name overlays from our own `synth.py` clips; crops of Open Images Billboard, Poster, Traffic sign and Whiteboard
  boxes from the train split, only from images where the plate class is verified absent; false positives of the v0 plate
  detector on Tier A train images.
- Never: sandbox crops (organisers' rule); AMD-TRAF or any Pexels-derived crop (Pexels terms §8 name machine learning);
  Windows-font renders (Microsoft's font FAQ is silent on training); DejaVu renders (the own-feed test plates use
  DejaVu); anything boxed by the AGPL detector.

**Operating point:** the threshold giving at least 99.5% recall on the validation positives (synthetic and real), fixed
before any test set below is scored.

**B0: integrity.** ONNX file ≤ 1 MB; ≤ 0.5 ms per crop on CPU in batches of 8 (2 threads), timed back to back with the
OCR; `pytest` passes; the manifest covers every training image and holds no forbidden source.

**B1: plates kept** (Stage A plus the classifier, against Stage A alone): sandbox-v1 0 of 25 exact reads lost; stored
sightings at most 1 of 92 exact (and not one of the sandbox-v1 crops) and 0 of 4 one-off; ownfeed-v1 at most 0.5% of
exact reads (26 of 5,307) and 0 of 128 vehicles gone; synthetic held-out at most 0.5% per kind (GJ ≤ 6 of 1,391, other
≤ 1 of 180, BH ≤ 1 of 152).

**B2: it adds something the rule does not.** The classifier alone (on the current gate, without Stage A) catches at
least 18 of the 24 stored not_a_plate sightings and at least 17 of the 23 reject-v1 crops.

**B3: held-out real non-plate text.** Crops of Open Images Billboard, Poster and Traffic sign boxes from the validation
and test splits (never trained on): the classifier alone rejects at least 90% of them, whatever the OCR reads; of those
that pass the current gate, Stage A plus the classifier lets through no more than Stage A alone.

**B4: fresh probe.** Seeds 404 and 505 (never run), rendered in the probe's fonts, none of which is in training: the
classifier alone rejects at least 90% of all probe crops; Stage A plus the classifier lets through no more than Stage A
alone, and at most 1 crop of the letter-led kinds (shop, vehicle-text, fleet-number) over both seeds.

**B5: live.** As A3 with the classifier on: pooled stock-footage exact ≥ 93.0%, AMD-TRAF-002 capture ≥ 58 of 68. If
the sandbox is reachable: CAM06 and CAM07, 30 analysed minutes each, reads dropped by the classifier at most 2% of the
reads that pass Stage A (counts only).

**Adoption.** Every one of B0–B5. At most one retrain after a failure, and its failure analysis uses validation data
only, never the per-image results of the test sets above. If adopted: "a small plate / not-a-plate classifier, trained
only on synthetic and commercially licensed images, alone rejects N of 24 stored non-plate sightings and M% of held-out
billboard and sign crops, at a measured cost of K plate reads", with the same caveats as Stage A. Not "detects every
non-plate".
