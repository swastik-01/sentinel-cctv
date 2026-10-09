# Plate OCR A/B: ocr_ft1

Generated 2026-09-26T19:47:17+05:30 by `bench/ocr_ab.py`. fast-plate-ocr 1.1.0, onnxruntime 1.30.0, CPU only, 2 ONNX threads, batches of 8. Each crop goes through `PlateOCR.read_many` (ocr.py), `normalise_plate`, and the worker gate (confidence >= 0.35 on the weakest character, `looks_like_indian_plate`, and at most 1 letters made from digits, as `worker.check_read`). Counts and rates only: no plate text is written here.

Intervals: Wilson treats every crop as independent; `groups` is a bootstrap over groups (one vehicle seen many times, or crops close in time, form one group; 2000 draws). Trust the group interval when groups are few.

## Gate verdicts (`bench/ocr_gates.md`, Addenda 1 and 2)

Written 2026-09-26T20:05:24+05:30 by `bench/ocr_gate_verdict.py` from this file's JSON, the export check and a timing run. Tree 87fa327 plus uncommitted `bench/ocr_gate_verdict.py`. Candidate `cct_xs_v2_india_ft1`: `best.keras` of `2026-09-26_17-59-48`, epoch 9 of 12 (best `val_acc` 0.8003 on the synthetic validation split: the checkpoint rule fixed before training, NEXT.md step 1; `last.keras` is not scored), exported to ONNX (sha256 bee613328baa; `best.keras` 46a8169bfae3). Baseline `cct-xs-v2-global-model`, the shipped model.

**Not adopted.** No candidate replaces the shipped model before the 27 Sep submission, whatever it scores (Addendum 2); adoption is for the finale, with every gate passed by 9 Oct 18:00 IST.

| Gate | Rule | Result | Verdict |
|---|---|---|---|
| 0 integrity | ONNX input `input` [N,64,128,3] uint8, dynamic batch; output `plate` [N,10,37] | `input` [N,64,128,3] uint8; `plate` [N,10,37] float | **pass** |
| 0 export | ONNX gives the Keras checkpoint's plate probabilities: same top character in every slot, largest difference below 1e-4 | synthetic-parity 200/200 same, largest difference 8.0e-06; ownfeed-sample 64/64 same, largest difference 3.7e-06 | **pass** |
| 0 self-check | loaded through the product's `PlateOCR`, reads a synthetic plate | 139/200 synthetic plates read exactly (200 non-empty); baseline 130/200 | **pass** |
| 0 speed | CPU time per crop at most 1.25x the baseline, back to back, worker stopped | 4.99 against 5.34 ms = 0.93x; 5.03 against 4.93 ms = 1.02x; slowest valid run 1.02x | **pass** |
| 0 pytest | `pytest` passes after the integration change | no integration change: the product is unchanged (NEXT.md step 4) | **pending** |
| 1 sandbox-v1 | breaks <= fixes on exact; passes-and-wrong: candidate <= baseline | 3 fixed, 1 broken (McNemar p = 0.6250); passes and wrong 1/28 against 3/28 | **pass** |
| 1 reject-v1 | crops passing the worker gate: candidate <= baseline (0 of 23 since Addendum 2) | 0/23 against 0/23 | **pass** |
| 1 ownfeed-v1 | exact difference: group 95% lower bound above -1.0 pt; passes-and-wrong difference: upper bound below +0.5 pt | exact +1.75 pt (-0.16 pt to +3.61 pt); passes and wrong -1.66 pt (-3.32 pt to +0.11 pt) | **pass** |
| 1 sandbox-blind-v1 | breaks <= fixes on exact; passes-and-wrong: candidate <= baseline | 8 fixed, 7 broken (McNemar p = 1.0000); passes and wrong 31/120 against 31/120 | **pass** |
| 1 sandbox-fresh-v1 | breaks <= fixes on exact; passes-and-wrong: candidate <= baseline; all rows and new vehicles | not scored: the set is frozen on 27 Sep by 10:00 IST, and no candidate is scored on its crops before then; the gate lapses if it is not frozen by 3 Oct | **pending** |
| 2 held-out synthetic | exact better with McNemar p < 0.05; no subgroup (tahoma-bold, two-line) with more broken than fixed at p < 0.05 | not run yet (`data/ocr-train/test.csv`, NEXT.md step 3) | **pending** |
| 3 live own-feed A/B | AMD-TRAF-001/002, A B A B 10-minute windows, stored exact and capture no worse than the same-session baseline | not run: needs the worker change of NEXT.md step 4 and Gates 0-2 passed; after the submission | **pending** |

**Real-plate gain: not shown.** On sandbox-blind-v1 the candidate fixed 8 and broke 7 (McNemar p = 1.0000); exact difference +0.83 pt (groups 95% -6.36 pt to +7.96 pt). A gain needs p < 0.05, fixes > breaks and a lower bound above 0 there (at least 6 fixes with no break, 8 with one, 10 with two), then fixes > breaks on sandbox-fresh-v1. Addendum 1's criteria are not met on sandbox-blind-v1; the real sets show non-inferiority only.

**Speed.** CPU time per crop, each run the median of 3 interleaved passes (A B A B A B) over 5528 own-feed crops (batches of 8, 2 ONNX threads). Every run of this script on this candidate is kept, and the verdict takes the slowest valid one: 19:55 baseline 5.34 ms, candidate 4.99 ms (0.93x; wall 2.75 and 2.56 ms; worker, rotation or trainer running: none; CPU 25% busy just before); 20:05 baseline 4.93 ms, candidate 5.03 ms (1.02x; wall 2.52 and 2.54 ms; worker, rotation or trainer running: none; CPU 28% busy just before). Slowest valid run 1.02x. The `ms per crop` rows below are `ocr_ab.py`'s wall time per set: sandbox-v1 0.90x; reject-v1 1.52x; ownfeed-v1 1.01x; sandbox-blind-v1 1.14x; pooled over every crop 1.02x. Small sets (reject-v1 is 23 crops in 3 batches) swing with the laptop's load; the gate names CPU time, measured above.

**Overall: passes every gate scored so far. Still pending: 0 pytest, 1 sandbox-fresh-v1, 2 held-out synthetic, 3 live own-feed A/B. Not adopted, and not before the submission in any case.**

## sandbox-v1

28 crops in 15 groups; layout {'one-line': 26, 'two-line': 2}. Real sandbox crops, labelled by our AI coding assistant, not blind (exact, one_off or wrong verdicts).

| Metric | cct-xs-v2-global-model | cct_xs_v2_india_ft1 |
|---|---|---|
| exact after normalise | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) | 27/28 = 96.4% (Wilson 82.3%–99.4%; groups 87.9%–100.0%) |
| raw exact | 17/28 = 60.7% (Wilson 42.4%–76.4%; groups 34.2%–95.0%) | 27/28 = 96.4% (Wilson 82.3%–99.4%; groups 87.5%–100.0%) |
| within one character | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) | 28/28 = 100.0% (Wilson 87.9%–100.0%; groups 100.0%–100.0%) |
| per-character accuracy (1 - CER) | 271/277 = 97.8% (Wilson 95.4%–99.0%; groups 95.1%–100.0%) | 276/277 = 99.6% (Wilson 98.0%–99.9%; groups 98.7%–100.0%) |
| passes the worker gate | 28/28 = 100.0% (Wilson 87.9%–100.0%; groups 100.0%–100.0%) | 27/28 = 96.4% (Wilson 82.3%–99.4%; groups 88.5%–100.0%) |
| passes the gate and is wrong | 3/28 = 10.7% (Wilson 3.7%–27.2%; groups 0.0%–24.1%) | 1/28 = 3.6% (Wilson 0.6%–17.7%; groups 0.0%–12.5%) |
| exact, of those that pass | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.0%–100.0%) | 26/27 = 96.3% (Wilson 81.7%–99.3%; groups 87.5%–100.0%) |
| ms per crop | 2.52 | 2.27 |

cct-xs-v2-global-model, exact by layout: one-line 23/26; two-line 2/2

cct_xs_v2_india_ft1, exact by layout: one-line 25/26; two-line 2/2

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 24/28 = 85.7% (Wilson 68.5%–94.3%; groups 72.4%–100.0%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 0, crop right and stored wrong 1 (exact McNemar p = 1.0000).
- Stored read against cct_xs_v2_india_ft1 on the single crop, paired on exact: stored right and crop wrong 1, crop right and stored wrong 4 (exact McNemar p = 0.3750).
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 24/28; cct-xs-v2-global-model 25/28; cct_xs_v2_india_ft1 27/28.

Candidate vs baseline, paired on exact: 3 fixed, 1 broken, exact McNemar p = 0.6250.

- exact after normalise: +7.1% (groups 95% -9.5% to +22.7%)
- within one character: +10.7% (groups 95% +0.0% to +24.2%)
- per-character accuracy (1 - CER): +1.8% (groups 95% -0.9% to +4.7%)
- passes the gate and is wrong: -7.1% (groups 95% -22.2% to +9.1%)
- paired on exact, by layout: one-line baseline 23/26, candidate 25/26, 3 fixed, 1 broken, p = 0.6250; two-line baseline 2/2, candidate 2/2, 0 fixed, 0 broken, p = 1.0000

## reject-v1

23 crops in 3 groups; layout {'one-line': 19, 'two-line': 4}. Real sandbox crops our AI coding assistant judged not a plate (the sandbox stored every one as a sighting): each that passes the gate goes on to the tracker as a plate read.

| Metric | cct-xs-v2-global-model | cct_xs_v2_india_ft1 |
|---|---|---|
| passes the worker gate | 0/23 = 0.0% (Wilson 0.0%–14.3%; groups 0.0%–0.0%) | 0/23 = 0.0% (Wilson 0.0%–14.3%; groups 0.0%–0.0%) |
| ms per crop | 3.09 | 4.70 |

Candidate vs baseline, paired on passes_gate (lower is better): 0 fixed, 0 broken, exact McNemar p = 1.0000.

- passes the worker gate: +0.0% (groups 95% +0.0% to +0.0%)

## ownfeed-v1

5528 crops in 128 groups; layout {'one-line': 2178, 'two-line': 3350}. AMD-TRAF-001/002 crops, synthetic plates painted on stock footage, labelled from the painted list.

| Metric | cct-xs-v2-global-model | cct_xs_v2_india_ft1 |
|---|---|---|
| exact after normalise | 5308/5528 = 96.0% (Wilson 95.5%–96.5%; groups 94.2%–97.7%) | 5405/5528 = 97.8% (Wilson 97.4%–98.1%; groups 96.4%–98.8%) |
| raw exact | 4135/5528 = 74.8% (Wilson 73.6%–75.9%; groups 68.3%–81.3%) | 5395/5528 = 97.6% (Wilson 97.2%–98.0%; groups 96.2%–98.7%) |
| within one character | 5479/5528 = 99.1% (Wilson 98.8%–99.3%; groups 98.5%–99.6%) | 5526/5528 = 100.0% (Wilson 99.9%–100.0%; groups 99.9%–100.0%) |
| per-character accuracy (1 - CER) | 54994/55280 = 99.5% (Wilson 99.4%–99.5%; groups 99.2%–99.7%) | 55155/55280 = 99.8% (Wilson 99.7%–99.8%; groups 99.6%–99.9%) |
| passes the worker gate | 5508/5528 = 99.6% (Wilson 99.4%–99.8%; groups 99.3%–99.9%) | 5518/5528 = 99.8% (Wilson 99.7%–99.9%; groups 99.6%–100.0%) |
| passes the gate and is wrong | 205/5528 = 3.7% (Wilson 3.2%–4.2%; groups 2.2%–5.6%) | 113/5528 = 2.0% (Wilson 1.7%–2.5%; groups 1.1%–3.3%) |
| exact, of those that pass | 5303/5508 = 96.3% (Wilson 95.8%–96.8%; groups 94.4%–97.8%) | 5405/5518 = 98.0% (Wilson 97.5%–98.3%; groups 96.8%–98.9%) |
| ms per crop | 2.52 | 2.55 |

cct-xs-v2-global-model, exact by layout: one-line 2117/2178; two-line 3191/3350

cct_xs_v2_india_ft1, exact by layout: one-line 2158/2178; two-line 3247/3350

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 5330/5528 = 96.4% (Wilson 95.9%–96.9%; groups 94.8%–97.8%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 71, crop right and stored wrong 49 (exact McNemar p = 0.0548).
- Stored read against cct_xs_v2_india_ft1 on the single crop, paired on exact: stored right and crop wrong 74, crop right and stored wrong 149 (exact McNemar p = 0.0000).
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 5330/5528; cct-xs-v2-global-model 5308/5528; cct_xs_v2_india_ft1 5405/5528.

Candidate vs baseline, paired on exact: 166 fixed, 69 broken, exact McNemar p = 0.0000.

- exact after normalise: +1.8% (groups 95% -0.2% to +3.6%)
- within one character: +0.9% (groups 95% +0.4% to +1.4%)
- per-character accuracy (1 - CER): +0.3% (groups 95% +0.1% to +0.5%)
- passes the gate and is wrong: -1.7% (groups 95% -3.3% to +0.1%)
- paired on exact, by layout: one-line baseline 2117/2178, candidate 2158/2178, 45 fixed, 4 broken, p = 0.0000; two-line baseline 3191/3350, candidate 3247/3350, 121 fixed, 65 broken, p = 0.0000

## sandbox-blind-v1

120 crops in 55 groups; layout {'one-line': 107, 'two-line': 13}. Real sandbox plates (CAM06, CAM07, CAM12) from sightings Sentinel stored, each read blind by a team member on the Plate review page; their reading is the true plate. Vehicle plates only.

9 of the 120 true plates are not in the form `normalise_plate` gives, so no normalised read (a model's or the stored one) can match them: exact is at most 111/120 here.

| Metric | cct-xs-v2-global-model | cct_xs_v2_india_ft1 |
|---|---|---|
| exact after normalise | 88/120 = 73.3% (Wilson 64.8%–80.4%; groups 65.7%–81.5%) | 89/120 = 74.2% (Wilson 65.7%–81.2%; groups 66.0%–82.7%) |
| raw exact | 62/120 = 51.7% (Wilson 42.8%–60.4%; groups 37.6%–65.1%) | 87/120 = 72.5% (Wilson 63.9%–79.7%; groups 63.2%–81.9%) |
| within one character | 108/120 = 90.0% (Wilson 83.3%–94.2%; groups 84.0%–95.1%) | 111/120 = 92.5% (Wilson 86.4%–96.0%; groups 88.1%–96.8%) |
| per-character accuracy (1 - CER) | 1121/1168 = 96.0% (Wilson 94.7%–97.0%; groups 94.5%–97.3%) | 1125/1168 = 96.3% (Wilson 95.1%–97.3%; groups 95.0%–97.6%) |
| passes the worker gate | 119/120 = 99.2% (Wilson 95.4%–99.9%; groups 97.0%–100.0%) | 119/120 = 99.2% (Wilson 95.4%–99.9%; groups 97.2%–100.0%) |
| passes the gate and is wrong | 31/120 = 25.8% (Wilson 18.8%–34.3%; groups 18.3%–33.7%) | 31/120 = 25.8% (Wilson 18.8%–34.3%; groups 17.9%–33.7%) |
| exact, of those that pass | 88/119 = 74.0% (Wilson 65.4%–81.0%; groups 66.4%–82.1%) | 88/119 = 74.0% (Wilson 65.4%–81.0%; groups 65.8%–82.2%) |
| ms per crop | 2.36 | 2.69 |

cct-xs-v2-global-model, exact by layout: one-line 78/107; two-line 10/13

cct_xs_v2_india_ft1, exact by layout: one-line 80/107; two-line 9/13

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 90/120 = 75.0% (Wilson 66.6%–81.9%; groups 67.3%–82.6%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 3, crop right and stored wrong 1 (exact McNemar p = 0.6250).
- Stored read against cct_xs_v2_india_ft1 on the single crop, paired on exact: stored right and crop wrong 8, crop right and stored wrong 7 (exact McNemar p = 1.0000).
- Sightings Sentinel stored with confidence >= 0.9: 81 of 120. Exact among them: stored read 69/81; cct-xs-v2-global-model 69/81; cct_xs_v2_india_ft1 66/81.
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 92/120; cct-xs-v2-global-model 90/120; cct_xs_v2_india_ft1 91/120.

Candidate vs baseline, paired on exact: 8 fixed, 7 broken, exact McNemar p = 1.0000.

- exact after normalise: +0.8% (groups 95% -6.4% to +8.0%)
- within one character: +2.5% (groups 95% -2.5% to +8.8%)
- per-character accuracy (1 - CER): +0.3% (groups 95% -0.7% to +1.7%)
- passes the gate and is wrong: +0.0% (groups 95% -7.4% to +7.2%)
- paired on exact, by layout: one-line baseline 78/107, candidate 80/107, 7 fixed, 5 broken, p = 0.7744; two-line baseline 10/13, candidate 9/13, 1 fixed, 2 broken, p = 1.0000

## Caveats

- The crops are the stored evidence crops: the worker's padded plate crop, saved as JPEG (quality 85). The worker read the raw crop; this reads the JPEG.
- A crop is scored as one read. The stored sighting is a track's vote over several reads, so the model rates are per read, not per sighting; only the stored-read lines are per sighting.
- ownfeed-v1 is labelled by matching the stored read to a painted plate within 2 edits, so crops the product misread worse than that are not in it: its rates favour the model that made the stored reads (the baseline). Its plates are synthetic, painted onto Pexels stock footage.
- sandbox-v1 and reject-v1 are real sandbox crops labelled against each crop by our AI coding assistant, with the stored read in view: not blind, not a person (`sandbox_eye.md`). They are a frozen test set and are never used for training.
- sandbox-blind-v1 is real sandbox plates that Sentinel stored and a team member then read blind on the Plate review page, typing the plate without seeing Sentinel's read. Their reading is taken as the answer; on our own plates, where the truth is known, the same reviewer was right 222 times in 226 (`review_truth.md`), so a few answers here may be wrong. Only stored sightings are in it: a plate Sentinel never stored cannot be, so the set says nothing about plates missed. Its crops include every sandbox-v1 crop. It is a frozen test set and is never used for training.
- ms per crop is wall time for `read_many` on a laptop shared with a live worker: compare models within one run, not across runs.
