# Plate pipeline: where stored reads go wrong

Generated 2026-09-26 15:40 IST by `bench/pipeline_diag.py` from data already collected (read-only database access, worker logs, stored OCR runs). No worker was run and no camera was read for it. Counts and rates only: no plate text is written here. Read with `pipeline_review.md`.

## 1. Sandbox: the team's blind review of stored sightings

144 blind reviews by `admin` on the sandbox cameras (exact 90, not_a_plate 24, one_off 17, wrong 13); the 120 vehicle plates are analysed below. Reads per track come from the worker logs that stored them (`data/rotation*/`), matched on camera, plate and second. Analysed frames per second per camera in the worker runs that took CAM06, CAM07, CAM12: median 1.3, quartiles 0.9-2.0, over 255 status lines (our own-feed reference run: about 4.5). A track closes at 3 reads (`CONFIRM_READS`), so no track has more.

### Reads behind each stored plate

| Reads in the track | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| 1 | 32 | 24/32 = 75.0% | 30/32 = 93.8% | 2 |
| 2 | 25 | 15/25 = 60.0% | 19/25 = 76.0% | 6 |
| 3 | 61 | 51/61 = 83.6% | 58/61 = 95.1% | 3 |
| not in a log | 2 | 0/2 = 0.0% | 0/2 = 0.0% | 2 |

### Plate box width (stream pixels, 1920x1080 or 1280x720)

| Box width | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| 50-65 px | 7 | 5/7 = 71.4% | 6/7 = 85.7% | 1 |
| 65-80 px | 4 | 4/4 = 100.0% | 4/4 = 100.0% | 0 |
| 80-100 px | 34 | 22/34 = 64.7% | 26/34 = 76.5% | 8 |
| >= 100 px | 75 | 59/75 = 78.7% | 71/75 = 94.7% | 4 |

### Stored confidence as a routing threshold

The stored confidence is the best read's weakest character, raised to 0.6 + 0.1 x reads (at most 0.99) when three or more reads agree on every character (`tracker.py`). A track closes at 3 reads, so three agreeing reads whose best was below 0.9 are stored at exactly 0.9: 14 plates, 12/14 = 85.7% exact. Confidences are rounded to 3 decimals (the column is REAL: 0.9 comes back as 0.8999999761).

| Auto band (stored confidence >=) | plates in band | share of plates | exact in band | within one in band | exact below band |
|---|---|---|---|---|---|
| 0.6 | 114 | 114/120 = 95.0% | 89/114 = 78.1% | 105/114 = 92.1% | 1/6 = 16.7% |
| 0.7 | 101 | 101/120 = 84.2% | 82/101 = 81.2% | 93/101 = 92.1% | 8/19 = 42.1% |
| 0.8 | 93 | 93/120 = 77.5% | 76/93 = 81.7% | 86/93 = 92.5% | 14/27 = 51.9% |
| 0.9 | 81 | 81/120 = 67.5% | 69/81 = 85.2% | 79/81 = 97.5% | 21/39 = 53.8% |
| 0.95 | 57 | 57/120 = 47.5% | 48/57 = 84.2% | 56/57 = 98.2% | 42/63 = 66.7% |
| 0.98 | 39 | 39/120 = 32.5% | 36/39 = 92.3% | 39/39 = 100.0% | 54/81 = 66.7% |

### Confidence and reads together

A 1-read track is stored only on a camera analysed below 2 frames per second and only at confidence >= 0.6 (`SLOW_FPS`, `SINGLE_READ_CONF`); 2 reads are stored at any confidence that passed the gate (0.35). With two reads the per-character vote (each read weighted by its weakest character) always follows the more confident read.

| Track | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| 1 read(s), conf 0.6-0.9 | 13 | 8/13 = 61.5% | 11/13 = 84.6% | 2 |
| 1 read(s), conf >= 0.9 | 19 | 16/19 = 84.2% | 19/19 = 100.0% | 0 |
| 2 read(s), conf < 0.6 | 5 | 1/5 = 20.0% | 2/5 = 40.0% | 3 |
| 2 read(s), conf 0.6-0.9 | 9 | 5/9 = 55.6% | 6/9 = 66.7% | 3 |
| 2 read(s), conf >= 0.9 | 11 | 9/11 = 81.8% | 11/11 = 100.0% | 0 |
| 3 read(s), conf < 0.6 | 1 | 0/1 = 0.0% | 0/1 = 0.0% | 1 |
| 3 read(s), conf 0.6-0.9 | 10 | 7/10 = 70.0% | 9/10 = 90.0% | 1 |
| 3 read(s), conf >= 0.9 | 50 | 44/50 = 88.0% | 49/50 = 98.0% | 1 |


### One vehicle stored twice

All 121 sightings the worker stored on CAM06, CAM07, CAM12 over the reviewed period: 3 pairs within 10 s on one camera whose plates are 1-2 edits apart, involving 5 sightings (5/121 = 4.1%). Pairs with both sightings reviewed: later exact, earlier not 2, earlier exact, later not 1.

### Detector confidence (YOLO box, or the classical finder's 0.45-0.9)

| Detector confidence | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| < 0.5 | 16 | 9/16 = 56.2% | 10/16 = 62.5% | 6 |
| 0.5-0.7 | 99 | 78/99 = 78.8% | 92/99 = 92.9% | 7 |
| >= 0.7 | 5 | 3/5 = 60.0% | 5/5 = 100.0% | 0 |

### What the non-exact reads got wrong

19 plates stored not exact whose true plate (the reviewer's reading) is in the standard layout; the rest are in the layout table below. Positions are the true plate's.

| Kind of error (per plate) | plates |
|---|---|
| same length, substitutions only | 12 |
| read shorter (dropped characters) | 7 |

| Substituted character, part of the registration | characters |
|---|---|
| series | 10 |
| number | 6 |
| RTO | 3 |
| state | 1 |

| Substitution pair | characters |
|---|---|
| other pair | 13 |
| look-alike pair | 7 |

| Dropped or added character | characters |
|---|---|
| inside (dropped) | 5 |
| first or last character (dropped) | 2 |

Of the 7 stored reads shorter than the true plate, 7 have a one-letter series where the true plate has two, and a number that starts with the digit look-alike of the true plate's last series letter: the OCR lost a digit and `normalise_plate` filled the 4-digit number from the series, which leaves a valid-looking plate that passes the gate. The watchlist's fuzzy match compares plates of the same length only, so such a read cannot raise the alert for its true plate. Where the alignment below puts a dropped character is one of several equally short explanations.

| Dropped or added character, part of the registration | characters |
|---|---|
| number (dropped) | 6 |
| series (dropped) | 1 |

### Layout of the true plates

`normalise_plate` accepts SS 00 L{1,3} 0000 and BH plates only; a plate in any other form can never be stored exactly.

| True plate layout | plates | stored exact | one off | wrong |
|---|---|---|---|---|
| standard or BH layout | 109 | 90 | 12 | 7 |
| standard once a look-alike is read by position (a digit typed for a letter, or back) | 8 | 0 | 4 | 4 |
| other (extra or missing characters) | 2 | 0 | 0 | 2 |
| number part shorter than 4 digits | 1 | 0 | 1 | 0 |

## 2. Own feeds: stored sightings against the painted plates

The worker run of 26 Sep 11:05-11:15 IST (`data/plate-gate-confirm/worker.env`: 4 cameras on one worker, HW_DECODE=auto, object detection on, DETECT_FPS=5; analysed frames per second per camera: median 1.1, quartiles 1.0-3.2, over 18 status lines, so part of it ran the slow-camera single-read path, below 2). AMD-TRAF-001/002 only (stock footage, synthetic plates painted on); sightings within 2 edits of a painted plate (689), so real unpainted plates are left out. Wrong here means 2 edits.

### AMD-TRAF-001

| Reads in the track | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| 1 | 53 | 48/53 = 90.6% | 50/53 = 94.3% | 3 |
| 2 | 41 | 35/41 = 85.4% | 40/41 = 97.6% | 1 |
| 3 | 44 | 43/44 = 97.7% | 44/44 = 100.0% | 0 |

| Box width | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| < 50 px | 28 | 24/28 = 85.7% | 26/28 = 92.9% | 2 |
| 50-65 px | 76 | 69/76 = 90.8% | 75/76 = 98.7% | 1 |
| 65-80 px | 25 | 25/25 = 100.0% | 25/25 = 100.0% | 0 |
| 80-100 px | 9 | 8/9 = 88.9% | 8/9 = 88.9% | 1 |

| Stored confidence | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| < 0.7 | 39 | 30/39 = 76.9% | 36/39 = 92.3% | 3 |
| 0.7-0.9 | 36 | 33/36 = 91.7% | 35/36 = 97.2% | 1 |
| >= 0.9 | 63 | 63/63 = 100.0% | 63/63 = 100.0% | 0 |

### AMD-TRAF-002

| Reads in the track | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| 1 | 158 | 156/158 = 98.7% | 157/158 = 99.4% | 1 |
| 2 | 143 | 140/143 = 97.9% | 143/143 = 100.0% | 0 |
| 3 | 247 | 244/247 = 98.8% | 247/247 = 100.0% | 0 |
| 4+ | 3 | 3/3 = 100.0% | 3/3 = 100.0% | 0 |

| Box width | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| < 50 px | 4 | 3/4 = 75.0% | 3/4 = 75.0% | 1 |
| 50-65 px | 67 | 66/67 = 98.5% | 67/67 = 100.0% | 0 |
| 65-80 px | 102 | 102/102 = 100.0% | 102/102 = 100.0% | 0 |
| 80-100 px | 93 | 93/93 = 100.0% | 93/93 = 100.0% | 0 |
| >= 100 px | 285 | 279/285 = 97.9% | 285/285 = 100.0% | 0 |

| Stored confidence | plates | exact | within one | wrong (2+ edits) |
|---|---|---|---|---|
| < 0.7 | 46 | 41/46 = 89.1% | 45/46 = 97.8% | 1 |
| 0.7-0.9 | 84 | 84/84 = 100.0% | 84/84 = 100.0% | 0 |
| >= 0.9 | 421 | 418/421 = 99.3% | 421/421 = 100.0% | 0 |

### One vehicle stored twice

All 689 sightings the worker stored on AMD-TRAF-001/002 in the run: 0 pairs within 10 s on one camera whose plates are 1-2 edits apart, involving 0 sightings (0/689 = 0.0%): .

## 3. Own feeds, per read: does crop size or sharpness add to OCR confidence?

`ownfeed-v1`: 5528 evidence crops from AMD-TRAF-001/002 (synthetic plates painted on stock footage), each read once by the shipped OCR in the stored baseline run (`data/ocr-eval/runs`). Width is the padded crop in stream pixels; sharpness is the variance of the Laplacian after resizing to the OCR's 128x64 input. The set is biased towards reads the product got nearly right (labelled by matching the stored read within 2 edits), and every crop is already the best-confidence read of its track.

| Crop width | reads | exact |
|---|---|---|
| < 70 px | 987 | 855/987 = 86.6% |
| 70-90 px | 980 | 941/980 = 96.0% |
| 90-110 px | 1006 | 997/1006 = 99.1% |
| 110-140 px | 448 | 445/448 = 99.3% |
| >= 140 px | 2107 | 2070/2107 = 98.2% |

| Sharpness | reads | exact |
|---|---|---|
| lowest quarter | 1382 | 1251/1382 = 90.5% |
| second quarter | 1382 | 1336/1382 = 96.7% |
| third quarter | 1380 | 1357/1380 = 98.3% |
| highest quarter | 1384 | 1364/1384 = 98.6% |

Within one confidence band, does the sharper or larger half read better?

| OCR confidence | reads | exact, blurrier half | exact, sharper half | exact, narrower half | exact, wider half |
|---|---|---|---|---|---|
| 0-0.7 | 886 | 332/441 = 75.3% | 420/445 = 94.4% | 328/432 = 75.9% | 424/454 = 93.4% |
| 0.7-0.9 | 1436 | 665/710 = 93.7% | 713/726 = 98.2% | 666/711 = 93.7% | 712/725 = 98.2% |
| 0.9-1 | 3206 | 1590/1603 = 99.2% | 1588/1603 = 99.1% | 1561/1574 = 99.2% | 1617/1632 = 99.1% |

## Caveats

- Section 1 is one reviewer's reading of 120 plates on three sandbox cameras (mostly CAM06), 55 vehicles or fewer; the per-row counts are small, so read them as directions, not rates.
- Reads per track are matched from the worker's log lines; a sighting whose line was not found is counted apart. The log's confidence is the stored one.
- Sections 2 and 3 are synthetic plates in one clean font painted on Pexels stock footage: real plates' errors (fonts, dirt, glare, two-line layouts, night IR) are not in them.
- Section 2's run was at a low and variable analysis rate; `anpr_eval_current.md` is the reference run at about 4.5 frames per second per camera.
