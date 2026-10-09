# Not-a-plate gate, Stage A (rule `1e-k2`): confirmation

Generated 2026-09-26T11:18:32+05:30 by `bench/plate_gate_confirm.py`, from the runs that gates A0-A3 of `bench/plate_gate_gates.md` (written 26 Sep 10:45 IST) name, checked as written there. The gates were not changed. Counts only: no plate text is written here.

Conditions: OCR `cct-xs-v2-global-model` on CPU (2 threads), `min_ocr_conf` 0.35; `MAX_LETTERS_FROM_DIGITS` 1 (the rule on). Worker run: AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001, AMD-AMC-001 on one worker, STATIC_TEXT_WINDOW_S=0, HW_DECODE=auto, OBJECT_DETECTION=true, DETECT_FPS=5, window 2026-09-26T11:05:22+05:30 to 2026-09-26T11:15:44+05:30.

**Verdict: SHIP.** A0-A3 all pass, within A4's deadline.

| Gate | Check | Threshold | Measured | Result | Finished (IST) |
|---|---|---|---|---|---|
| A0 | reject-v1: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 23 reads | PASS | 26 Sep 11:02 |
|  | sandbox-v1: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 28 reads | PASS |  |
|  | ownfeed-v1: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 5,528 reads | PASS |  |
|  | stored sightings: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 145 reads | PASS |  |
|  | synthetic plates: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 3,000 reads | PASS |  |
|  | probe seed 7: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 2,400 reads | PASS |  |
|  | probe seed 11: helper vs replay / normalise_plate vs replay | 0 / 0 mismatches on every read | 0 / 0 of 2,400 reads | PASS |  |
|  | bench/plate_gate.py exit code | 0 (it exits 1 on any parity mismatch) | 0 | PASS |  |
| A1 | reject-v1 caught | 23 of 23 | 23 of 23 | PASS | 26 Sep 11:02 |
|  | stored not_a_plate dropped | 24 of 24 | 24 of 24 | PASS |  |
|  | sandbox-v1 exact reads lost | <= 0 of 25 | 0 of 25 | PASS |  |
|  | stored sightings exact lost | <= 0 of 92 | 0 of 92 | PASS |  |
|  | stored sightings one-off lost | <= 0 of 4 | 0 of 4 | PASS |  |
|  | ownfeed-v1 exact reads lost | <= 4 of 5,307 | 4 of 5,307 | PASS |  |
|  | ownfeed-v1 vehicles gone | <= 0 of 128 | 0 of 128 | PASS |  |
|  | synthetic held-out GJ exact lost | <= 1 of 1,391 | 1 of 1,391 | PASS |  |
|  | synthetic held-out other states exact lost | <= 0 of 180 | 0 of 180 | PASS |  |
|  | synthetic held-out BH exact lost | <= 0 of 152 | 0 of 152 | PASS |  |
| A2 | seed 101: crops still passing with the rule | <= 5 of 2,400 (300 per kind) | 1 of 2,400 (300 per kind; current gate 44) | PASS | 26 Sep 11:03 |
|  | seed 202: crops still passing with the rule | <= 5 of 2,400 (300 per kind) | 1 of 2,400 (300 per kind; current gate 39) | PASS |  |
|  | seed 303: crops still passing with the rule | <= 5 of 2,400 (300 per kind) | 2 of 2,400 (300 per kind; current gate 43) | PASS |  |
|  | three seeds: rule passes as a share of current-gate passes | <= 20% | 3.2% (4 of 126) | PASS |  |
|  | parity on the fresh run (not registered; every source it read) | 0 / 0 | probe seed 101: 0 / 0 of 2,400; probe seed 202: 0 / 0 of 2,400; probe seed 303: 0 / 0 of 2,400 | PASS |  |
| A3 | pytest -q | passes | 214 passed, 0 failed, exit 0 | PASS | 26 Sep 11:16 |
|  | the six required unit tests exist and pass | 6 of 6 | 6 of 6 | PASS |  |
|  | smoke.py --skip-fleet | 34/34, ALL PASSED | 34/34 (31 pass, 3 skip, 0 fail), ALL PASSED | PASS |  |
|  | security_checks.py | 19/19, ALL PASSED | 19/19 (19 pass, 0 skip, 0 fail), ALL PASSED | PASS |  |
|  | worker run: errors in its log | no worker error | 0 ERROR/CRITICAL/Traceback lines | PASS |  |
|  | anpr_eval: pooled stock-footage exact | >= 93.0% | 97.1% (669/689) | PASS |  |
|  | anpr_eval: AMD-TRAF-002 capture, plates shown >= 1 s | >= 58 of 68 | 63 of 68 | PASS |  |
| A4 | A0-A3 all green by the deadline | by 27 Sep 2026 12:00 IST | last gate finished 26 Sep 11:16 | PASS | |

## A2: fresh probe, per kind

Crops passing the current gate / still passing with the rule, 300 crops per kind; the kinds and renderer are `bench/plate_gate.py`'s probe (DejaVu Sans Bold, Arial Bold, Bahnschrift), seeds first run here.

| Seed | mobile | landline | timestamp | overlay | shop | shop-number | vehicle-text | fleet-number | all |
|---|---|---|---|---|---|---|---|---|---|
| 101 | 21 / 0 | 17 / 0 | 5 / 0 | 0 / 0 | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 0 | 44 / 1 |
| 202 | 20 / 1 | 12 / 0 | 7 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 39 / 1 |
| 303 | 31 / 2 | 7 / 0 | 5 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 43 / 2 |

## Not registered: extra checks

- Independent count: on 200,000 generated strings (plate-, BH- and number-shaped, with look-alike characters and separators; made up, never saved), `letters_from_digits` against the digits of the cleaned read that are letters in `normalise_plate`'s output: 0 mismatches (7,170 strings counted 2 or more, 6,750 counted 1).
- The fresh-probe run re-scored the frozen sets: its A1 counts are identical to the A1 run's.
- Worker run, per camera (sightings, exact, capture of plates shown >= 1 s): AMD-TRAF-001 138, 91.3% (126/138), 20.2% (26/129); AMD-TRAF-002 551, 98.5% (543/551), 92.6% (63/68); AMD-AMC-001 90, 56.7% (51/90), 75.0% (3/4); AMD-POL-001 24, 91.7% (22/24), 100.0% (3/3).
- Worker log: last status 4/4 streams up; analysed fps summed over the cameras, per 30 s status line (18 lines): 2.2, 3.9, 4.3, 4.2, 3.9, 3.9, 3.6, 3.3, 3.9, 3.4, 5.0, 12.2, 14.9, 14.9, 13.0, 16.9, 10.0, 14.2 (`anpr_eval_current.md` had about 4.5 per camera, 18 summed); decode D3D11; reads the rule dropped, last log line (camera dropped/passing the gate): AMD-AMC-001 2/2416, AMD-POL-001 2/1571, AMD-TRAF-001 2/394, AMD-TRAF-002 1/1608.

## Caveats

- A3's live run is a wiring check, not a measurement of the rule (`bench/plate_gate_gates.md`): the stock-footage plates are synthetic registrations painted on Pexels footage, and the drawn cameras show drawn plates and an overlay. The worker logs counts, not text, so a read it dropped there may be a misread plate or other text in the scene: not known.
- A2's probe assumes the plate detector has already fired on the text; it measures only what the OCR, the gate and the rule then do, in the probe's three fonts.
- A1 reproduces exploratory numbers: rule `1e-k2` was chosen after looking at reject-v1, the stored sightings and probe seed 7. The non-plate evidence is 3 texts on one sandbox camera, and the sandbox labels were made by our AI coding assistant with the stored read in view, not blind; the team's blind check (A5) is still to come.
- The smoke and security checks and the worker run use the live stack on this laptop (GTX 1650 Ti); the API process had loaded `sentinel_common` before the helper was added, and the API does not call it.
- The worker run was not at `anpr_eval_current.md`'s analysis rate (about 4.5 fps per camera): 1.9 per camera on average over its status lines, 0.6 at the lowest (the cause is not measured here). Below 2 fps per camera the worker accepts single confident reads (`SLOW_FPS`), so part of the window ran that path; the A3 thresholds were checked on the run as it was.
