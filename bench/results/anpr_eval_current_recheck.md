# ANPR accuracy against simulator ground truth

Generated 2026-09-26 16:39 IST by `scripts/anpr_eval.py` (read-only database access).
Window: 2026-09-24 01:29 to 2026-09-24 01:39 IST, sightings by frame time.
Reproduce: `uv run --no-sync python scripts/anpr_eval.py --since 2026-09-24T01:29:16+05:30 --until 2026-09-24T01:39:17+05:30 --camera AMD-TRAF-001 --camera AMD-TRAF-002 --camera AMD-POL-001 --camera AMD-AMC-001` (while those sightings are kept: `demo_prep.py` without `--keep-sightings` deletes them).
Conditions: 24 Sep 01:29-01:39 IST: the window and sightings of anpr_eval_current.md, re-scored on 26 Sep after the confidence-band fix (ocr_conf is REAL; tracks stored at exactly 0.9 had fallen into 0.7-0.9). Only the confidence tables differ from anpr_eval_current.md; every other number is identical. Worker as there: 4 cameras on one worker, HW_DECODE=auto (D3D11), object detection on, ~4.5 analysed fps per camera; GTX 1650 Ti laptop

**These plates are synthetic registrations, not real Gujarat plates.** On the two stock-footage cameras the vehicles and scenes are real (Pexels stock footage, not Gujarat CCTV; the Ahmedabad locations are simulated) but every plate the painter found carries a synthetic registration in a clean font on a white plate; the other cameras show drawn rectangles. Precision on real plates is unmeasured.

| Camera | Footage | Class, view | anpr_viable | Stream | Sightings | Precision (exact) | Within one character | Capture rate, plates shown >= 1 s | Capture rate, every plate | Median plate box width (px) | Active minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMD-TRAF-001 | stock footage, painted plates | ptz, 3840x2160 of the source scaled 0.50x | no | 1920x1080 h264 25 fps | 193 | 90.2% (174/193) | 96.9% (187/193) | 21.7% (28/129) | 11.1% (30/271) | 55 | 11 |
| AMD-TRAF-002 | stock footage, painted plates | anpr, 1440x810 of the source scaled 1.33x | yes | 1920x1080 h265 25 fps | 681 | 96.8% (659/681) | 97.4% (663/681) | 91.2% (62/68) | 67.2% (84/125) | 106 | 11 |
| AMD-AMC-001 | synthetic (drawn) | anpr, scene close, plate drawn ~368 px wide | yes | 1920x1080 h264 25 fps | 48 | 29.2% (14/48) | 91.7% (44/48) | 75.0% (3/4) | 75.0% (3/4) | 436 | 11 |
| AMD-POL-001 | synthetic (drawn) | anpr, scene mid, plate drawn ~200 px wide | yes | 1280x720 h264 25 fps | 8 | 100.0% (8/8) | 100.0% (8/8) | 100.0% (3/3) | 100.0% (3/3) | 224 | 4 |
| **All 2 stock footage cameras, pooled** | | | | | 874 | 95.3% (833/874) | 97.3% (850/874) | 45.7% (90/197) | 28.8% (114/396) | | |
| **All 2 synthetic cameras, pooled** | | | | | 56 | 39.3% (22/56) | 92.9% (52/56) | 85.7% (6/7) | 85.7% (6/7) | | |

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

193 sightings from 2026-09-24 01:29 to 2026-09-24 01:39 IST; 41 distinct plates read, 11 of them not ground truth; 271 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 87 | 2.3% (2/87) |
| 0.5-1 s | 55 | 0.0% (0/55) |
| 1-2 s | 46 | 8.7% (4/46) |
| 2-5 s | 46 | 23.9% (11/46) |
| >= 5 s | 37 | 35.1% (13/37) |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 4 | 25.0% (1/4) |
| 0.5-0.7 | 37 | 64.9% (24/37) |
| 0.7-0.9 | 38 | 92.1% (35/38) |
| >= 0.9 | 114 | 100.0% (114/114) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ18MU6598` x3: nearest `GJ18HU6598`, 1 edit
- `GJ16TD5955` x2: nearest `GJ18TD5955`, 1 edit
- `GJ05CM3468` x2: nearest `GJ05CH3468`, 1 edit
- `GJ05VD2496` x2: nearest `GJ05VB2496`, 1 edit
- `GJ05EM3468` x2: nearest `GJ05CH3468`, 2 edits

### AMD-TRAF-002 (Paldi Char Rasta, Ahmedabad (stock traffic footage))

681 sightings from 2026-09-24 01:29 to 2026-09-24 01:39 IST; 95 distinct plates read, 11 of them not ground truth; 125 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 31 | 22.6% (7/31) |
| 0.5-1 s | 26 | 57.7% (15/26) |
| 1-2 s | 34 | 85.3% (29/34) |
| 2-5 s | 34 | 97.1% (33/34) |
| >= 5 s | 0 | n/a |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 2 | 0.0% (0/2) |
| 0.5-0.7 | 24 | 75.0% (18/24) |
| 0.7-0.9 | 41 | 87.8% (36/41) |
| >= 0.9 | 614 | 98.5% (605/614) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ84AC4013` x5: nearest `GJ38AC4013`, 2 edits
- `GJ87A3614` x3: nearest `GJ18TA3614`, 2 edits
- `GJ05V6645` x2: nearest `GJ05VJ6645`, 1 edit
- `GJ13PR0019` x2: nearest `GJ13PR8019`, 1 edit
- `GJ13P8019` x2: nearest `GJ13PR8019`, 1 edit

### AMD-AMC-001 (Income Tax Circle, Ashram Road)

48 sightings from 2026-09-24 01:29 to 2026-09-24 01:39 IST; 7 distinct plates read, 4 of them not ground truth; 4 ground-truth plates; 0 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 0 | n/a |
| 0.5-0.7 | 18 | 27.8% (5/18) |
| 0.7-0.9 | 4 | 25.0% (1/4) |
| >= 0.9 | 26 | 30.8% (8/26) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ11AB1234` x26: nearest `GJ01AB1234`, 1 edit
- `GJ11ZZ0001` x4: nearest `GJ01ZZ0001`, 1 edit
- `GJ01Z2000` x3: nearest `GJ01ZZ0001`, 2 edits
- `GJ01A8123` x1: nearest `GJ01AB1234`, 2 edits

### AMD-POL-001 (Sarkhej-Gandhinagar Highway Toll Approach)

8 sightings from 2026-09-24 01:29 to 2026-09-24 01:34 IST; 3 distinct plates read, 0 of them not ground truth; 3 ground-truth plates; 2 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 0 | n/a |
| 0.5-0.7 | 0 | n/a |
| 0.7-0.9 | 0 | n/a |
| >= 0.9 | 8 | 100.0% (8/8) |

## Caveats

- Plates are synthetic registrations painted onto stock footage (or drawn); not real Gujarat plates. Real plates vary in font, layout (two-row, high-security, hand-painted), dirt, glare and IR at night. Precision on real plates is unmeasured.
- The stock clips are 60 s of Pexels footage re-encoded at up to 4 Mbps (`realclip.py`), replayed in a loop: the same vehicles pass again every loop, so precision is over repeated passes of the same painted plates (the detail gives how many distinct plates were read), not over as many different vehicles as there are sightings.
- The painter (`feedsim/realclip.py`) replaces only the plates its detector finds. A plate it missed keeps its original characters, and a read of it counts here as a wrong read. Such reads would fall outside the "within one character" share: a real registration is very unlikely to be one character from a painted one.
- The worker's settings (streams per machine, achieved analysis rate, code version) are not stored with the sightings; they are only what the Conditions lines above say.
