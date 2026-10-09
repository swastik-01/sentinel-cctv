# Not-a-plate gate: rules on the OCR read

Generated 2026-09-26T10:54:18+05:30 by `bench/plate_gate.py`. OCR `cct-xs-v2-global-model` (fast-plate-ocr 1.1.0, onnxruntime 1.30.0, CPU, 2 threads, batches of 8), read through the product's `PlateOCR.read_many`, `normalise_plate` and the worker gate (weakest character >= 0.35 and `looks_like_indian_plate`). Each rule is applied on top of that gate, so it can only remove reads. Digits turned into letters are counted by the product helper `letters_from_digits` (the count the worker's rule uses); the per-role counts the other rules need come from a step-by-step replay of `normalise_plate`, checked on every read against `normalise_plate` and against the helper (below). Counts only: no plate text is written here.

Implementation parity (`bench/plate_gate_gates.md` A0), reads where the product helper's count differs from the replay's / where `normalise_plate` differs from the replay: reject-v1 0 / 0 of 23; sandbox-v1 0 / 0 of 28; ownfeed-v1 0 / 0 of 5,528; stored sightings 0 / 0 of 145; synthetic plates 0 / 0 of 3,000; probe seed 7 0 / 0 of 2,400; probe seed 11 0 / 0 of 2,400.

Reads identical to the stored `ocr_ab.py` baseline run: reject-v1 23/23; sandbox-v1 28/28; ownfeed-v1 5528/5528.

## Frozen test sets

- **reject-v1**: 23 real sandbox crops our AI coding assistant labelled not a plate (with the stored read in view: not a person, not blind), 3 groups (one group = one piece of fixed text, so the set is really 3 texts, all on one camera). 23 pass the current gate.
- **sandbox-v1**: 28 real plate crops, labelled the same way (one camera, 15 groups). 28 pass the gate: 25 exact, 3 wrong.
- **ownfeed-v1**: 5,528 crops of synthetic plates painted on stock footage (128 vehicles). 5,512 pass the gate: 5,307 exact, 205 wrong.

Columns: *caught* = reads of non-plates the rule removes (want all); *exact lost* = correct plate reads it removes (want none); *wrong removed* = misread plates it removes (a side benefit); *vehicles gone* = groups whose every passing crop is removed.

| Rule | reject-v1 caught (of 23) | texts fully caught (of 3) | sandbox-v1 exact lost (of 25) | sandbox-v1 wrong removed (of 3) | ownfeed-v1 exact lost (of 5,307) | ownfeed-v1 wrong removed (of 205) | ownfeed-v1 vehicles gone (of 128) |
|---|---|---|---|---|---|---|---|
| `conf-0.50` weakest character >= 0.50 (now 0.35) | 3 | 1 | 1 | 0 | 38 | 37 | 1 |
| `conf-0.70` weakest character >= 0.70 | 10 | 1 | 2 | 2 | 761 | 120 | 7 |
| `conf-0.90` weakest character >= 0.90 | 19 | 1 | 10 | 3 | 2129 | 177 | 31 |
| `1a-state-any` reject if a state-code letter was made from a digit | 23 | 3 | 0 | 0 | 161 | 30 | 4 |
| `1b-state-both` reject if both state-code letters were made from digits | 23 | 3 | 0 | 0 | 4 | 0 | 0 |
| `1b-simple` 1b as a one-line check: the raw read starts with two digits and is not a BH plate | 23 | 3 | 0 | 0 | 4 | 0 | 0 |
| `1c-series` reject if a series letter was made from a digit | 21 | 1 | 1 | 0 | 27 | 12 | 1 |
| `1d-k1` reject if any letter was made from a digit (k >= 1) | 23 | 3 | 1 | 0 | 188 | 42 | 5 |
| `1e-k2` reject if 2 or more letters were made from digits | 23 | 3 | 0 | 0 | 4 | 0 | 0 |
| `1f-k3` reject if 3 or more letters were made from digits | 21 | 1 | 0 | 0 | 0 | 0 | 0 |
| `1g-all-digits` reject if the raw read has no letters at all | 19 | 0 | 0 | 0 | 0 | 0 | 0 |
| `1h-state-touched` reject if the state code was changed at all (digit or look-alike) | 23 | 3 | 0 | 0 | 435 | 95 | 9 |
| `1i-any-repair` reject if any character was repaired (reference: the strictest rule) | 23 | 3 | 8 | 2 | 1172 | 155 | 15 |
| `2a-state-as-read` raw read starts with a real state/UT code, or is a BH plate as read | 23 | 3 | 0 | 0 | 435 | 95 | 9 |
| `2b-state-or-bh` raw read starts with a real state/UT code, or normalises to a BH plate | 23 | 3 | 0 | 0 | 435 | 95 | 9 |
| `2c-no-lookalike` state code valid after the digit repair, without the look-alike swap | 0 | 0 | 0 | 0 | 435 | 95 | 9 |
| `2b+1c` 2b, and no series letter made from a digit | 23 | 3 | 1 | 0 | 454 | 106 | 10 |

How the reads reached a valid layout (path through `normalise_plate`): reject-v1 {'std-repaired': 23}; sandbox-v1 {'std': 18, 'std-repaired': 10}; ownfeed-v1 {'std': 4434, 'std-repaired': 1080, 'fallback': 14}.

Weakest-character confidence (p10 / median / p90): reject-v1 0.49 / 0.766 / 0.92; sandbox-v1 0.654 / 0.936 / 0.999; ownfeed-v1 0.647 / 0.949 / 0.998.

## Stored sandbox sightings, labelled by our AI coding assistant

145 stored sightings from the organisers' sandbox (CAM05 24, CAM06 92, CAM07 28, CAM12 1), each labelled by our AI coding assistant from its own evidence crop with the stored read in view (`data/gov-sandbox/eye/labels.csv`): not by a person and not blind, so a label may lean towards the stored read. The team's blind check is separate (`bench/plate_gate_gates.md` A5). The stored text is the track's vote and the raw read was not kept, so each evidence crop (the track's best read) is read again with the product OCR. This set includes the crops frozen into sandbox-v1 and reject-v1, plus sightings labelled after those sets were frozen. Missing crops: 0.

Re-read agrees with the stored text after normalising: not_a_plate 15/24; exact 89/92; one_off 4/4; wrong 8/11; unreadable 13/14. Re-read passes the current gate: not_a_plate 24/24; exact 92/92; one_off 4/4; wrong 10/11; unreadable 14/14.

Dropped by each rule (of the sightings whose re-read passes the current gate):

| Rule | not_a_plate (of 24) | exact (of 92) | one_off (of 4) | wrong (of 10) | unreadable (of 14) |
|---|---|---|---|---|---|
| `conf-0.50` | 3 | 3 | 2 | 0 | 0 |
| `conf-0.70` | 10 | 12 | 3 | 7 | 2 |
| `conf-0.90` | 20 | 34 | 3 | 10 | 9 |
| `1a-state-any` | 24 | 0 | 0 | 0 | 0 |
| `1b-state-both` | 24 | 0 | 0 | 0 | 0 |
| `1b-simple` | 24 | 0 | 0 | 0 | 0 |
| `1c-series` | 22 | 3 | 0 | 1 | 1 |
| `1d-k1` | 24 | 3 | 0 | 1 | 1 |
| `1e-k2` | 24 | 0 | 0 | 0 | 0 |
| `1f-k3` | 22 | 0 | 0 | 0 | 0 |
| `1g-all-digits` | 20 | 0 | 0 | 0 | 0 |
| `1h-state-touched` | 24 | 2 | 0 | 0 | 1 |
| `1i-any-repair` | 24 | 28 | 2 | 7 | 5 |
| `2a-state-as-read` | 24 | 2 | 0 | 0 | 1 |
| `2b-state-or-bh` | 24 | 2 | 0 | 0 | 1 |
| `2c-no-lookalike` | 0 | 2 | 0 | 0 | 1 |
| `2b+1c` | 24 | 5 | 0 | 1 | 2 |

Weakest-character confidence by verdict (p10 / median / p90): not_a_plate 0.492 / 0.759 / 0.918; exact 0.642 / 0.957 / 0.998; wrong 0.515 / 0.588 / 0.848; unreadable 0.651 / 0.865 / 0.967; one_off 0.417 / 0.539 / 0.89.

## Synthetic held-out plates (other states and BH)

`data/ocr-train/test.csv` from `bench/plategen.py`, never trained on: 3,000 synthetic plates (GJ 2453, other 314, BH 233). ownfeed-v1 is all GJ, so this is where a rule would show a cost on other states' plates and on BH plates, which start with digits. Exact reads that pass the current gate: GJ 1391, other 180, BH 152.

| Rule | GJ exact lost (of 1391) | other exact lost (of 180) | BH exact lost (of 152) |
|---|---|---|---|
| `conf-0.50` | 31 | 4 | 1 |
| `conf-0.70` | 193 | 29 | 15 |
| `conf-0.90` | 405 | 62 | 39 |
| `1a-state-any` | 32 | 1 | 0 |
| `1b-state-both` | 1 | 0 | 0 |
| `1b-simple` | 1 | 0 | 0 |
| `1c-series` | 2 | 1 | 0 |
| `1d-k1` | 34 | 2 | 5 |
| `1e-k2` | 1 | 0 | 0 |
| `1f-k3` | 0 | 0 | 0 |
| `1g-all-digits` | 0 | 0 | 0 |
| `1h-state-touched` | 33 | 1 | 0 |
| `1i-any-repair` | 108 | 10 | 8 |
| `2a-state-as-read` | 33 | 1 | 8 |
| `2b-state-or-bh` | 33 | 1 | 0 |
| `2c-no-lookalike` | 30 | 0 | 0 |
| `2b+1c` | 35 | 2 | 0 |

## Synthetic non-plate text (probe)

Rendered in memory and never saved: text on a sign colour in DejaVu Sans Bold, Arial Bold or Bahnschrift, padded like a worker crop, shrunk to 60-200 px wide, blurred, noised and JPEG-coded. It assumes the plate detector has already fired on the text (as it did on the sandbox hoarding); it measures only what the OCR, the gate and each rule then do. Cells: crops that still pass. The first probe run was seed 7 at 150 crops per kind, and `1e-k2` was singled out after it; seed 11 was first run after that choice, as a check.

Seed 7, 300 crops per kind:

| Kind | n | current gate | `conf-0.70` | `1b-state-both` | `1e-k2` | `1g-all-digits` | `2a-state-as-read` | `2b+1c` |
|---|---|---|---|---|---|---|---|---|
| mobile | 300 | 21 | 9 | 13 | 1 | 13 | 0 | 0 |
| landline | 300 | 13 | 2 | 6 | 0 | 7 | 0 | 0 |
| timestamp | 300 | 4 | 0 | 1 | 0 | 2 | 0 | 0 |
| overlay | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shop | 300 | 1 | 0 | 1 | 1 | 1 | 1 | 1 |
| shop-number | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vehicle-text | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fleet-number | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| all | 2400 | 39 | 11 | 21 | 2 | 23 | 1 | 1 |

Seed 11, 300 crops per kind:

| Kind | n | current gate | `conf-0.70` | `1b-state-both` | `1e-k2` | `1g-all-digits` | `2a-state-as-read` | `2b+1c` |
|---|---|---|---|---|---|---|---|---|
| mobile | 300 | 19 | 13 | 8 | 0 | 8 | 0 | 0 |
| landline | 300 | 12 | 5 | 1 | 0 | 3 | 0 | 0 |
| timestamp | 300 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| overlay | 300 | 1 | 0 | 1 | 1 | 1 | 0 | 0 |
| shop | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shop-number | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vehicle-text | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fleet-number | 300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| all | 2400 | 35 | 18 | 10 | 1 | 12 | 0 | 0 |


## Caveats

- One read per crop. The worker applies the gate per read before the tracker votes, and a sighting needs several reads, so a rule that removes one read of a vehicle does not always lose the vehicle; *vehicles gone* is the stricter view on ownfeed-v1.
- The crops are the stored JPEG evidence crops (quality 85); the worker read the raw frame crop.
- The non-plate text is from one sandbox camera and a handful of distinct texts: a rule that catches it may be fitted to those texts, not to hoardings in general. The sandbox crops are test-only and never trained on.
- The sandbox labels (reject-v1, sandbox-v1, the stored sightings) were made by our AI coding assistant with the stored read in view, not by a person and not blind.
- ownfeed-v1 plates are synthetic (all GJ), painted on Pexels stock footage: real out-of-state plates, damaged plates and non-standard fonts are not in it.
- The hoarding sightings were stored before `static_text.py` existed. That filter mutes fixed text read again in the same place, but it still stores the first sighting; a rule on the read stops the first one too.
