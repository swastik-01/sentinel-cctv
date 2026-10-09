# Plate OCR A/B: ocr_baseline

Generated 2026-09-25T22:22:16+05:30 by `bench/ocr_ab.py`. fast-plate-ocr 1.1.0, onnxruntime 1.30.0, CPU only, 2 ONNX threads, batches of 8. Each crop goes through `PlateOCR.read_many` (ocr.py), `normalise_plate`, and the worker gate (confidence >= 0.35 on the weakest character, and `looks_like_indian_plate`). Counts and rates only: no plate text is written here.

Intervals: Wilson treats every crop as independent; `groups` is a bootstrap over groups (one vehicle seen many times, or crops close in time, form one group; 2000 draws). Trust the group interval when groups are few.

## sandbox-v1

28 crops in 15 groups; layout {'one-line': 26, 'two-line': 2}. Real sandbox crops, labelled by our AI coding assistant, not blind (exact, one_off or wrong verdicts).

| Metric | cct-xs-v2-global-model |
|---|---|
| exact after normalise | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) |
| raw exact | 17/28 = 60.7% (Wilson 42.4%–76.4%; groups 34.2%–95.0%) |
| within one character | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.9%–100.0%) |
| per-character accuracy (1 - CER) | 271/277 = 97.8% (Wilson 95.4%–99.0%; groups 95.1%–100.0%) |
| passes the worker gate | 28/28 = 100.0% (Wilson 87.9%–100.0%; groups 100.0%–100.0%) |
| passes the gate and is wrong | 3/28 = 10.7% (Wilson 3.7%–27.2%; groups 0.0%–24.1%) |
| exact, of those that pass | 25/28 = 89.3% (Wilson 72.8%–96.3%; groups 75.0%–100.0%) |
| ms per crop | 8.29 |

cct-xs-v2-global-model, exact by layout: one-line 23/26; two-line 2/2

## reject-v1

23 crops in 3 groups; layout {'one-line': 19, 'two-line': 4}. Real sandbox crops our AI coding assistant judged not a plate (the sandbox stored every one as a sighting): each that passes the gate goes on to the tracker as a plate read.

| Metric | cct-xs-v2-global-model |
|---|---|
| passes the worker gate | 23/23 = 100.0% (Wilson 85.7%–100.0%; groups 100.0%–100.0%) |
| ms per crop | 36.12 |

## ownfeed-v1

5528 crops in 128 groups; layout {'one-line': 2178, 'two-line': 3350}. AMD-TRAF-001/002 crops, synthetic plates painted on stock footage, labelled from the painted list.

| Metric | cct-xs-v2-global-model |
|---|---|
| exact after normalise | 5308/5528 = 96.0% (Wilson 95.5%–96.5%; groups 94.1%–97.6%) |
| raw exact | 4135/5528 = 74.8% (Wilson 73.6%–75.9%; groups 68.1%–81.4%) |
| within one character | 5479/5528 = 99.1% (Wilson 98.8%–99.3%; groups 98.5%–99.6%) |
| per-character accuracy (1 - CER) | 54994/55280 = 99.5% (Wilson 99.4%–99.5%; groups 99.2%–99.7%) |
| passes the worker gate | 5512/5528 = 99.7% (Wilson 99.5%–99.8%; groups 99.4%–99.9%) |
| passes the gate and is wrong | 205/5528 = 3.7% (Wilson 3.2%–4.2%; groups 2.2%–5.4%) |
| exact, of those that pass | 5307/5512 = 96.3% (Wilson 95.8%–96.8%; groups 94.5%–97.8%) |
| ms per crop | 8.62 |

cct-xs-v2-global-model, exact by layout: one-line 2117/2178; two-line 3191/3350

## Caveats

- The crops are the stored evidence crops: the worker's padded plate crop, saved as JPEG (quality 85). The worker read the raw crop; this reads the JPEG.
- A crop is scored as one read. The stored sighting is a track's vote over several reads, so these rates are per read, not per sighting.
- ownfeed-v1 is labelled by matching the stored read to a painted plate within 2 edits, so crops the product misread worse than that are not in it: its rates favour the model that made the stored reads (the baseline). Its plates are synthetic, painted onto Pexels stock footage.
- sandbox-v1 and reject-v1 are real sandbox crops labelled against each crop by our AI coding assistant, with the stored read in view: not blind, not a person (`sandbox_eye.md`). They are a frozen test set and are never used for training.
- ms per crop is wall time for `read_many` on a laptop shared with a live worker: compare models within one run, not across runs.
