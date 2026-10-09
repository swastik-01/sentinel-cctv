# Plate OCR A/B: ocr_baseline_checkread

Generated 2026-09-26T16:40:32+05:30 by `bench/ocr_ab.py`. fast-plate-ocr 1.1.0, onnxruntime 1.30.0, CPU only, 2 ONNX threads, batches of 8. Each crop goes through `PlateOCR.read_many` (ocr.py), `normalise_plate`, and the worker gate (confidence >= 0.35 on the weakest character, `looks_like_indian_plate`, and at most 1 letters made from digits, as `worker.check_read`). Counts and rates only: no plate text is written here.

Intervals: Wilson treats every crop as independent; `groups` is a bootstrap over groups (one vehicle seen many times, or crops close in time, form one group; 2000 draws). Trust the group interval when groups are few.

## sandbox-blind-v1

120 crops in 55 groups; layout {'one-line': 107, 'two-line': 13}. Real sandbox plates (CAM06, CAM07, CAM12) from sightings Sentinel stored, each read blind by a team member on the Plate review page; their reading is the true plate. Vehicle plates only.

9 of the 120 true plates are not in the form `normalise_plate` gives, so no normalised read (a model's or the stored one) can match them: exact is at most 111/120 here.

| Metric | cct-xs-v2-global-model |
|---|---|
| exact after normalise | 88/120 = 73.3% (Wilson 64.8%–80.4%; groups 65.8%–81.0%) |
| raw exact | 62/120 = 51.7% (Wilson 42.8%–60.4%; groups 38.4%–65.1%) |
| within one character | 108/120 = 90.0% (Wilson 83.3%–94.2%; groups 84.4%–94.8%) |
| per-character accuracy (1 - CER) | 1121/1168 = 96.0% (Wilson 94.7%–97.0%; groups 94.6%–97.3%) |
| passes the worker gate | 119/120 = 99.2% (Wilson 95.4%–99.9%; groups 97.2%–100.0%) |
| passes the gate and is wrong | 31/120 = 25.8% (Wilson 18.8%–34.3%; groups 17.9%–33.8%) |
| exact, of those that pass | 88/119 = 74.0% (Wilson 65.4%–81.0%; groups 66.1%–81.8%) |
| ms per crop | 5.74 |

cct-xs-v2-global-model, exact by layout: one-line 78/107; two-line 10/13

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 90/120 = 75.0% (Wilson 66.6%–81.9%; groups 67.3%–82.6%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 3, crop right and stored wrong 1 (exact McNemar p = 0.6250).
- Sightings Sentinel stored with confidence >= 0.9: 81 of 120. Exact among them: stored read 69/81; cct-xs-v2-global-model 69/81.
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 92/120; cct-xs-v2-global-model 90/120.

## sandbox-v1

28 crops in 15 groups; layout {'one-line': 26, 'two-line': 2}. Real sandbox crops, labelled by our AI coding assistant, not blind (exact, one_off or wrong verdicts).

| Metric | cct-xs-v2-global-model |
|---|---|
| exact after normalise | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) |
| raw exact | 17/28 = 60.7% (Wilson 42.4%–76.4%; groups 34.3%–95.2%) |
| within one character | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) |
| per-character accuracy (1 - CER) | 271/277 = 97.8% (Wilson 95.4%–99.0%; groups 95.1%–100.0%) |
| passes the worker gate | 28/28 = 100.0% (Wilson 87.9%–100.0%; groups 100.0%–100.0%) |
| passes the gate and is wrong | 3/28 = 10.7% (Wilson 3.7%–27.2%; groups 0.0%–25.0%) |
| exact, of those that pass | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) |
| ms per crop | 5.36 |

cct-xs-v2-global-model, exact by layout: one-line 23/26; two-line 2/2

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 24/28 = 85.7% (Wilson 68.5%–94.3%; groups 72.4%–100.0%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 0, crop right and stored wrong 1 (exact McNemar p = 1.0000).
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 24/28; cct-xs-v2-global-model 25/28.

## reject-v1

23 crops in 3 groups; layout {'one-line': 19, 'two-line': 4}. Real sandbox crops our AI coding assistant judged not a plate (the sandbox stored every one as a sighting): each that passes the gate goes on to the tracker as a plate read.

| Metric | cct-xs-v2-global-model |
|---|---|
| passes the worker gate | 0/23 = 0.0% (Wilson 0.0%–14.3%; groups 0.0%–0.0%) |
| ms per crop | 4.88 |

## ownfeed-v1

5528 crops in 128 groups; layout {'one-line': 2178, 'two-line': 3350}. AMD-TRAF-001/002 crops, synthetic plates painted on stock footage, labelled from the painted list.

| Metric | cct-xs-v2-global-model |
|---|---|
| exact after normalise | 5308/5528 = 96.0% (Wilson 95.5%–96.5%; groups 94.2%–97.7%) |
| raw exact | 4135/5528 = 74.8% (Wilson 73.6%–75.9%; groups 68.3%–81.0%) |
| within one character | 5479/5528 = 99.1% (Wilson 98.8%–99.3%; groups 98.6%–99.6%) |
| per-character accuracy (1 - CER) | 54994/55280 = 99.5% (Wilson 99.4%–99.5%; groups 99.2%–99.7%) |
| passes the worker gate | 5508/5528 = 99.6% (Wilson 99.4%–99.8%; groups 99.3%–99.9%) |
| passes the gate and is wrong | 205/5528 = 3.7% (Wilson 3.2%–4.2%; groups 2.1%–5.6%) |
| exact, of those that pass | 5303/5508 = 96.3% (Wilson 95.8%–96.8%; groups 94.5%–97.7%) |
| ms per crop | 6.78 |

cct-xs-v2-global-model, exact by layout: one-line 2117/2178; two-line 3191/3350

**Stored read against single-crop re-read.** The stored read is the plate Sentinel saved for the sighting: the track's vote over several reads (`tracker.py`). The crop is only the track's best-confidence read, and the table above re-reads that one crop.

- Stored read, exact after normalise: 5330/5528 = 96.4% (Wilson 95.9%–96.9%; groups 94.8%–97.8%).
- Stored read against cct-xs-v2-global-model on the single crop, paired on exact: stored right and crop wrong 71, crop right and stored wrong 49 (exact McNemar p = 0.0548).
- With the true plate also put through `normalise_plate` (a look-alike typed where the format fixes a letter or a digit then counts as agreeing), exact: stored read 5330/5528; cct-xs-v2-global-model 5308/5528.

## Caveats

- The crops are the stored evidence crops: the worker's padded plate crop, saved as JPEG (quality 85). The worker read the raw crop; this reads the JPEG.
- A crop is scored as one read. The stored sighting is a track's vote over several reads, so the model rates are per read, not per sighting; only the stored-read lines are per sighting.
- ownfeed-v1 is labelled by matching the stored read to a painted plate within 2 edits, so crops the product misread worse than that are not in it: its rates favour the model that made the stored reads (the baseline). Its plates are synthetic, painted onto Pexels stock footage.
- sandbox-v1 and reject-v1 are real sandbox crops labelled against each crop by our AI coding assistant, with the stored read in view: not blind, not a person (`sandbox_eye.md`). They are a frozen test set and are never used for training.
- sandbox-blind-v1 is real sandbox plates that Sentinel stored and a team member then read blind on the Plate review page, typing the plate without seeing Sentinel's read. Their reading is taken as the answer; on our own plates, where the truth is known, the same reviewer was right 222 times in 226 (`review_truth.md`), so a few answers here may be wrong. Only stored sightings are in it: a plate Sentinel never stored cannot be, so the set says nothing about plates missed. Its crops include every sandbox-v1 crop. It is a frozen test set and is never used for training.
- ms per crop is wall time for `read_many` on a laptop shared with a live worker: compare models within one run, not across runs.
