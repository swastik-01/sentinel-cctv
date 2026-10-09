# ANPR accuracy against simulator ground truth

Generated 2026-09-24 00:54 IST by `scripts/anpr_eval.py` (read-only database access).
Window: 2026-09-22 00:00 to 2026-09-24 00:00 IST, sightings by frame time.
Reproduce: `uv run --no-sync python scripts/anpr_eval.py --since 2026-09-22T00:00:00+05:30 --until 2026-09-24T00:00:00+05:30` (while those sightings are kept: `demo_prep.py` without `--keep-sightings` deletes them).
Conditions: sightings come from two worker sessions on 23 Sep 2026: 11:31-12:10 IST on the six cameras below, and 17:03-17:34 IST, on all six until 17:17 and then on the four synthetic ones only (their object counts stop at the same time); GTX 1650 Ti laptop; DETECT_FPS=5, DETECTOR=both, OCR_MODEL=cct-xs-v2-global-model, MIN_OCR_CONF=0.35 (.env, unchanged since 17 Sep).
Conditions: worker code of 23 Sep, before the 24 Sep tracker change: each sighting stored the track's best single OCR read. The current worker stores the per-character vote across the track's reads and accepts one confident read on cameras analysed below 2 fps; nothing has measured it on these cameras yet, so these numbers describe the earlier worker.
Conditions: the window ends at 24 Sep 00:00 IST so that it holds that worker only: the 27 AMD-AMC-001 sightings written during the 24 Sep store-and-forward test (00:01-00:03 IST, work-in-progress worker) are left out. It holds every worker sighting before them.

**These plates are synthetic registrations, not real Gujarat plates.** On the two stock-footage cameras the vehicles and scenes are real (Pexels stock footage, not Gujarat CCTV; the Ahmedabad locations are simulated) but every plate the painter found carries a synthetic registration in a clean font on a white plate; the other cameras show drawn rectangles. Precision on real plates is unmeasured.

| Camera | Footage | Class, view | anpr_viable | Stream | Sightings | Precision (exact) | Within one character | Capture rate, plates shown >= 1 s | Capture rate, every plate | Median plate box width (px) | Active minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMD-TRAF-001 | stock footage, painted plates | ptz, 3840x2160 of the source scaled 0.50x | no | 1920x1080 h264 25 fps | 410 | 90.2% (370/410) | 99.5% (408/410) | 21.7% (28/129) | 11.1% (30/271) | 60 | 52 |
| AMD-TRAF-002 | stock footage, painted plates | anpr, 1440x810 of the source scaled 1.33x | yes | 1920x1080 h265 25 fps | 1977 | 98.7% (1952/1977) | 99.4% (1965/1977) | 91.2% (62/68) | 60.8% (76/125) | 130 | 53 |
| AMD-AMC-001 | synthetic (drawn) | anpr, scene close, plate drawn ~368 px wide | yes | 1920x1080 h264 25 fps | 718 | 58.8% (422/718) | 96.5% (693/718) | 100.0% (4/4) | 100.0% (4/4) | 436 | 67 |
| AMD-POL-001 | synthetic (drawn) | anpr, scene mid, plate drawn ~200 px wide | yes | 1280x720 h264 25 fps | 184 | 88.6% (163/184) | 97.8% (180/184) | 100.0% (3/3) | 100.0% (3/3) | 214 | 59 |
| GNR-GSRTC-001 | synthetic (drawn) | fixed, scene close, plate drawn ~368 px wide | yes | 1280x720 h264 15 fps | 419 | 86.2% (361/419) | 86.2% (361/419) | 100.0% (3/3) | 100.0% (3/3) | 379 | 65 |
| MHS-POL-001 | synthetic (drawn) | anpr, scene close, plate drawn ~368 px wide | yes | 1920x1080 h264 25 fps | 447 | 45.4% (203/447) | 96.9% (433/447) | 100.0% (3/3) | 100.0% (3/3) | 436 | 65 |
| **All 2 stock footage cameras, pooled** | | | | | 2387 | 97.3% (2322/2387) | 99.4% (2373/2387) | 45.7% (90/197) | 26.8% (106/396) | | |
| **All 4 synthetic cameras, pooled** | | | | | 1768 | 65.0% (1149/1768) | 94.3% (1667/1768) | 100.0% (13/13) | 100.0% (13/13) | | |

No worker sightings in this window for: AMD-AMC-002, AMD-GSRTC-001, AMD-HLTH-001, GNR-HLTH-001, GNR-PNCHT-001, GNR-PNCHT-002, GNR-POL-001, GNR-POL-002 (not analysed in this window, or nothing read). They have ground truth and can be measured the same way.

## Definitions

- **Sighting**: one row the worker stored in `vehicle_sightings`, i.e. one confirmed plate track (several OCR reads of one vehicle), not one OCR read. A plate seen again on a later pass (the clips loop) is a new sighting. Rows the worker did not write (track id not starting with `<camera>-`, e.g. the smoke test's `smoke`) are left out and counted in the detail below.
- **Precision (exact)**: sightings whose stored `plate_norm` equals one of that camera's ground-truth plates, over all of that camera's sightings in the window.
- **Within one character**: same length and at most one character different from one of that camera's ground-truth plates (exact reads included). This is the watchlist's fuzzy rule (`FUZZY_MAX_EDITS=1`), so such a read would still raise the alert for its true plate (subject to the alert cooldown; the current API skips a one-character match on a sighting built from a single read).
- **Capture rate, plates shown >= 1 s**: distinct ground-truth plates read exactly at least once in the window, over distinct ground-truth plates the clip shows. The clips loop (every 60 s), so a plate counts as captured if it was read in any loop. For stock footage, "shows" means painted on screen for at least 1 s in total (`frames_painted` in `<CODE>.plates.json`). That ground truth does not record plate size or legibility, and a plate on screen can be far away, tiny, blurred or half-hidden, so the rate is a floor for legible plates, not the rate for legible plates. For synthetic clips every listed plate crosses the view several times a loop, so over a window of many loops their capture is all but certain and says little.
- **Capture rate, every plate**: the same over every plate the painter logged, including plates painted for a few frames only.
- **Ground-truth plate** (stock footage): a registration the painter assigned, not a vehicle. Its tracker gives a new registration to a plate it lost for more than 25 frames or that jumped past its gate, so one vehicle can carry two; a read of the second leaves the first uncaptured.
- **Median plate box width**: median width in stream pixels (the camera's resolution) of the detector's plate box on the sightings, i.e. of plates that were read, not of all plates shown.
- **Active minutes**: distinct clock minutes with at least one sighting on that camera; a rough proxy for how many loops the worker analysed, not a measurement of it.
- **Pooled**: sums over the cameras of that kind with sightings in the window, so busier cameras weigh more.

## Detail per camera

### AMD-TRAF-001 (Ashram Road Junction, Ahmedabad (stock traffic footage))

410 sightings from 2026-09-23 11:31 to 2026-09-23 17:17 IST; 48 distinct plates read, 18 of them not ground truth; 271 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 87 | 1.1% (1/87) |
| 0.5-1 s | 55 | 1.8% (1/55) |
| 1-2 s | 46 | 8.7% (4/46) |
| 2-5 s | 46 | 26.1% (12/46) |
| >= 5 s | 37 | 32.4% (12/37) |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 2 | 100.0% (2/2) |
| 0.5-0.7 | 92 | 71.7% (66/92) |
| 0.7-0.9 | 164 | 91.5% (150/164) |
| >= 0.9 | 152 | 100.0% (152/152) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ03LT3975` x8: nearest `GJ03LT5975`, 1 edit
- `GJ18UW4134` x5: nearest `GJ18UR4134`, 1 edit
- `GJ06VS2183` x3: nearest `GJ06YS2183`, 1 edit
- `GJ66YS2183` x3: nearest `GJ06YS2183`, 1 edit
- `GJ05EH3468` x3: nearest `GJ05CH3468`, 1 edit

### AMD-TRAF-002 (Paldi Char Rasta, Ahmedabad (stock traffic footage))

1977 sightings from 2026-09-23 11:31 to 2026-09-23 17:17 IST; 86 distinct plates read, 10 of them not ground truth; 125 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 31 | 6.5% (2/31) |
| 0.5-1 s | 26 | 46.2% (12/26) |
| 1-2 s | 34 | 85.3% (29/34) |
| 2-5 s | 34 | 97.1% (33/34) |
| >= 5 s | 0 | n/a |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 2 | 0.0% (0/2) |
| 0.5-0.7 | 132 | 93.9% (124/132) |
| 0.7-0.9 | 597 | 98.5% (588/597) |
| >= 0.9 | 1246 | 99.5% (1240/1246) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ06FY2044` x6: nearest `GJ06FV2044`, 1 edit
- `GJ88AC4013` x4: nearest `GJ38AC4013`, 1 edit
- `GJ05M0121` x4: nearest `GJ05MD1281`, 2 edits
- `GJ13P8019` x2: nearest `GJ13PR8019`, 1 edit
- `GJ05B1878` x2: nearest `GJ05BL8738`, 2 edits

### AMD-AMC-001 (Income Tax Circle, Ashram Road)

718 sightings from 2026-09-23 11:31 to 2026-09-23 17:34 IST; 13 distinct plates read, 9 of them not ground truth; 4 ground-truth plates; 2 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 17 | 11.8% (2/17) |
| 0.5-0.7 | 193 | 61.7% (119/193) |
| 0.7-0.9 | 471 | 56.1% (264/471) |
| >= 0.9 | 37 | 100.0% (37/37) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ11AB1234` x181: nearest `GJ01AB1234`, 1 edit
- `GJ11ZZ0001` x85: nearest `GJ01ZZ0001`, 1 edit
- `GJ01Z2000` x12: nearest `GJ01ZZ0001`, 2 edits
- `GJ12ZZ0001` x7: nearest `GJ01ZZ0001`, 2 edits
- `GJ01A8123` x5: nearest `GJ01AB1234`, 2 edits

### AMD-POL-001 (Sarkhej-Gandhinagar Highway Toll Approach)

184 sightings from 2026-09-23 11:31 to 2026-09-23 17:34 IST; 9 distinct plates read, 6 of them not ground truth; 3 ground-truth plates; 0 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 5 | 60.0% (3/5) |
| 0.5-0.7 | 20 | 40.0% (8/20) |
| 0.7-0.9 | 71 | 95.8% (68/71) |
| >= 0.9 | 88 | 95.5% (84/88) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ11ZZ0001` x10: nearest `GJ01ZZ0001`, 1 edit
- `GJ26GH3456` x5: nearest `GJ27GH3456`, 1 edit
- `GJ01Z2000` x3: nearest `GJ01ZZ0001`, 2 edits
- `GJ27GH3455` x1: nearest `GJ27GH3456`, 1 edit
- `GJ26HH3456` x1: nearest `GJ27GH3456`, 2 edits

### GNR-GSRTC-001 (Gandhinagar Bus Depot Gate)

419 sightings from 2026-09-23 11:31 to 2026-09-23 17:34 IST; 9 distinct plates read, 6 of them not ground truth; 3 ground-truth plates; 0 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 7 | 0.0% (0/7) |
| 0.5-0.7 | 15 | 33.3% (5/15) |
| 0.7-0.9 | 269 | 85.5% (230/269) |
| >= 0.9 | 128 | 98.4% (126/128) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ12ZZ0001` x42: nearest `GJ01ZZ0001`, 2 edits
- `GJ12ZO0011` x7: nearest `GJ01ZZ0001`, 4 edits
- `GJ01Z2000` x4: nearest `GJ01ZZ0001`, 2 edits
- `GJ01A8123` x3: nearest `GJ01AB1234`, 2 edits
- `GJ18C0568` x1: nearest `GJ18CD5678`, 2 edits

### MHS-POL-001 (Mehsana Highway Checkpost)

447 sightings from 2026-09-23 11:31 to 2026-09-23 17:34 IST; 10 distinct plates read, 7 of them not ground truth; 3 ground-truth plates; 1 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 18 | 5.6% (1/18) |
| 0.5-0.7 | 170 | 57.1% (97/170) |
| 0.7-0.9 | 258 | 40.3% (104/258) |
| >= 0.9 | 1 | 100.0% (1/1) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ06IK7890` x106: nearest `GJ06JK7890`, 1 edit
- `GJ11ZZ0001` x78: nearest `GJ01ZZ0001`, 1 edit
- `GJ06KK7890` x25: nearest `GJ06JK7890`, 1 edit
- `GJ05FF9012` x21: nearest `GJ05EF9012`, 1 edit
- `GJ01Z2000` x12: nearest `GJ01ZZ0001`, 2 edits

## Caveats

- Plates are synthetic registrations painted onto stock footage (or drawn); not real Gujarat plates. Real plates vary in font, layout (two-row, high-security, hand-painted), dirt, glare and IR at night. Precision on real plates is unmeasured.
- The stock clips are 60 s of Pexels footage re-encoded at up to 4 Mbps (`realclip.py`), replayed in a loop: the same vehicles pass again every loop, so precision is over repeated passes of the same painted plates (the detail gives how many distinct plates were read), not over as many different vehicles as there are sightings.
- The painter (`feedsim/realclip.py`) replaces only the plates its detector finds. A plate it missed keeps its original characters, and a read of it counts here as a wrong read. Such reads would fall outside the "within one character" share: a real registration is very unlikely to be one character from a painted one.
- The worker's settings (streams per machine, achieved analysis rate, code version) are not stored with the sightings; they are only what the Conditions lines above say.
