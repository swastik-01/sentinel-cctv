# Tracker rules replayed on our own feeds' track logs

Generated 2026-09-26 15:36 IST by `bench/track_replay.py` from `2026-09-24_0116_sw-decode.jsonl`, `2026-09-24_0122_hw-decode.jsonl` (TRACK_LOG of two 5-minute worker runs on 24 Sep 2026, 01:16-01:27 IST: 4 cameras on one worker, GTX 1650 Ti laptop, object detection on, about 4.5 analysed frames per second per camera, software then hardware decode; the tracks behind `plate_choice.md`). No worker, GPU or camera was used. Stock-footage cameras AMD-TRAF-001 (PTZ view, plates read at a median 55 px wide) and AMD-TRAF-002 (ANPR view, ~100 px). Exact = the stored plate is one of the camera's painted registrations. **Synthetic registrations in one clean font painted on Pexels stock footage, not real Gujarat plates.** Counts and rates only.

A pass is the chain of tracks one vehicle produced (same camera, plates within 2 edits, best reads within 2 s); see the docstring. Check on the replay: from the same reads, it stores 887 sightings on these two cameras; the worker's own logs of the runs (`*.worker.log` beside each track log) show 888.

## 1. The shipped rule: sightings per pass

The shipped tracker stores each track's vote as soon as it has 3 reads (or its hold of about 1 s ends with 2); the pass's later tracks are dropped as repeats unless they read two or more characters differently (or one dropped or added), and then the same vehicle is stored again.

| Camera | Passes | Reads per pass, median / p90 | Sightings stored | Sightings exact | Extra sightings of a pass already stored | Passes whose first sighting is exact |
|---|---|---|---|---|---|---|
| AMD-TRAF-001 | 199 | 3 / 8 | 205 | 191/205 = 93.2% | 6 | 186/199 = 93.5% |
| AMD-TRAF-002 | 674 | 6 / 9 | 682 | 661/682 = 96.9% | 8 | 661/674 = 98.1% |

## 2. One plate per pass, voted over more of its reads

Exact passes when each pass stores one plate, voted over its first k reads; fixes and breaks are paired against the shipped first sighting, both cameras together. At about 4.5 analysed frames per second, k reads arrive about (k - 1) / 4.5 s after the first (3 reads ~0.4 s, 5 ~0.9 s, 7 ~1.3 s); the whole pass waits until the vehicle has left.

| Rule | AMD-TRAF-001 | AMD-TRAF-002 | fixes | breaks |
|---|---|---|---|---|
| shipped (first sighting of the pass) | 186/199 = 93.5% | 661/674 = 98.1% | - | - |
| first 3 reads of the pass | 190/199 = 95.5% | 661/674 = 98.1% | 4 | 0 |
| first 5 reads | 191/199 = 96.0% | 661/674 = 98.1% | 5 | 0 |
| first 7 reads | 191/199 = 96.0% | 661/674 = 98.1% | 5 | 0 |
| whole pass | 191/199 = 96.0% | 661/674 = 98.1% | 5 | 0 |
| whole pass, length tie by weight | 191/199 = 96.0% | 661/674 = 98.1% | 6 | 1 |
| whole pass, equal weights | 187/199 = 94.0% | 659/674 = 97.8% | 6 | 7 |
| whole pass, confidence squared | 191/199 = 96.0% | 662/674 = 98.2% | 6 | 0 |

A late correction (store the first track as now, so alerts keep their latency, then correct the sighting when the pass ends if the whole-pass vote differs) is the `whole pass` row's fixes and breaks.

## 3. At a lower analysis rate

Every s-th read of a pass is kept (s = 1, 2, 3: about 4.5, 2.3 and 1.5 analysed frames per second), each offset one trial. The first track is the first 3 kept reads. The shipped worker stores a one-read track only below 2 analysed frames per second (`SLOW_FPS`) and only at confidence >= 0.6 (`SINGLE_READ_CONF`); the other rows are alternatives. Capture = trials whose pass stored an exact plate, over passes the worker stored at 4.5 (a vehicle read once at 4.5 is not in the log: the worker drops such a track before logging it); precision = exact over trials that stored a plate.

| Frames per second (approx.) | One-read track stored at | Camera | Trials | Capture | Precision | Exact among one-read sightings |
|---|---|---|---|---|---|---|
| 4.5 | never (shipped) | AMD-TRAF-001 | 199 | 190/199 = 95.5% | 190/199 = 95.5% | - |
| 4.5 | never (shipped) | AMD-TRAF-002 | 674 | 661/674 = 98.1% | 661/674 = 98.1% | - |
| 2.2 | never (shipped) | AMD-TRAF-001 | 398 | 204/398 = 51.3% | 204/215 = 94.9% | - |
| 2.2 | never (shipped) | AMD-TRAF-002 | 1348 | 959/1348 = 71.1% | 959/969 = 99.0% | - |
| 2.2 | >= 0.9 (alternative) | AMD-TRAF-001 | 398 | 260/398 = 65.3% | 260/271 = 95.9% | 56/56 = 100.0% |
| 2.2 | >= 0.9 (alternative) | AMD-TRAF-002 | 1348 | 1134/1348 = 84.1% | 1134/1146 = 99.0% | 175/177 = 98.9% |
| 1.5 | >= 0.6 (shipped) | AMD-TRAF-001 | 597 | 389/597 = 65.2% | 389/415 = 93.7% | 198/212 = 93.4% |
| 1.5 | >= 0.6 (shipped) | AMD-TRAF-002 | 2022 | 1747/2022 = 86.4% | 1747/1771 = 98.6% | 596/617 = 96.6% |
| 1.5 | >= 0.8 (alternative) | AMD-TRAF-001 | 597 | 313/597 = 52.4% | 313/327 = 95.7% | 122/124 = 98.4% |
| 1.5 | >= 0.8 (alternative) | AMD-TRAF-002 | 2022 | 1584/2022 = 78.3% | 1584/1594 = 99.4% | 433/440 = 98.4% |
| 1.5 | >= 0.9 (alternative) | AMD-TRAF-001 | 597 | 278/597 = 46.6% | 278/290 = 95.9% | 87/87 = 100.0% |
| 1.5 | >= 0.9 (alternative) | AMD-TRAF-002 | 2022 | 1485/2022 = 73.4% | 1485/1491 = 99.6% | 334/337 = 99.1% |
| 1.5 | never (alternative) | AMD-TRAF-001 | 597 | 191/597 = 32.0% | 191/203 = 94.1% | - |
| 1.5 | never (alternative) | AMD-TRAF-002 | 2022 | 1151/2022 = 56.9% | 1151/1154 = 99.7% | - |

## 4. Which sightings could skip review

An auto band is the set of stored sightings trusted without a person; the rest would go to review. First track of each pass (the plate the shipped worker stores first), both cameras together; at 1.5 the shipped one-read rule (>= 0.6) applies.

| Frames per second (approx.) | Auto band | Sightings in band | Exact in band | Exact below band |
|---|---|---|---|---|
| 4.5 | stored confidence >= 0.9 (as the review page bands it) | 745/873 = 85.3% | 739/745 = 99.2% | 112/128 = 87.5% |
| 4.5 | stored confidence >= 0.9 and 2+ reads | 745/873 = 85.3% | 739/745 = 99.2% | 112/128 = 87.5% |
| 4.5 | 2+ reads equal to the stored plate | 836/873 = 95.8% | 827/836 = 98.9% | 24/37 = 64.9% |
| 4.5 | 3 reads, all equal | 606/873 = 69.4% | 606/606 = 100.0% | 245/267 = 91.8% |
| 1.5 | stored confidence >= 0.9 (as the review page bands it) | 1469/2186 = 67.2% | 1461/1469 = 99.5% | 675/717 = 94.1% |
| 1.5 | stored confidence >= 0.9 and 2+ reads | 1042/2186 = 47.7% | 1037/1042 = 99.5% | 1099/1144 = 96.1% |
| 1.5 | 2+ reads equal to the stored plate | 1294/2186 = 59.2% | 1293/1294 = 99.9% | 843/892 = 94.5% |
| 1.5 | 3 reads, all equal | 557/2186 = 25.5% | 557/557 = 100.0% | 1579/1629 = 96.9% |

## 5. Length ties in one track

Tracks whose reads split evenly between two lengths (the shipped vote then takes the length read first): 14 of 1631. Breaking the tie by summed confidence instead: 7 fixes, 1 breaks, 0 other changes. The painted plates are clean and nearly all the same length, so ties are rare here; on real plates a dropped character was 7 of 19 standard-layout misses (`pipeline_diag.md`).

## Caveats

- Synthetic registrations in one clean font (painted on Pexels stock footage, or drawn): real plates' errors are not in these reads, and accuracy here sits near its ceiling on AMD-TRAF-002. Compare rules with each other, not with the sandbox.
- Passes are rebuilt from the tracks' best-read times; a read's own time is not logged. Two vehicles with plates two edits apart in view together would be one pass (the painted plates are chosen to differ more).
- Section 3 thins reads, not frames, and ignores the longer hold at a low rate; it is an estimate of the direction, to be confirmed with a live run at DETECT_FPS=1.5 (TRACK_LOG on, own feeds only).
- The logs are from the 24 Sep worker (before the not-a-plate rule and the fixed-text rule); neither changes a painted plate's reads.
