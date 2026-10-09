# ANPR accuracy against simulator ground truth

Generated 2026-09-24 01:15 IST by `scripts/anpr_eval.py` (read-only database access).
Window: 2026-09-24 01:00 to 2026-09-24 01:15 IST, sightings by frame time.
Reproduce: `uv run --no-sync python scripts/anpr_eval.py --since 2026-09-24T01:00:13+05:30 --until 2026-09-24T01:15:14+05:30 --camera AMD-TRAF-001 --camera AMD-TRAF-002 --camera AMD-POL-001 --camera AMD-AMC-001` (while those sightings are kept: `demo_prep.py` without `--keep-sightings` deletes them).
Conditions: 24 Sep 01:00-01:15 IST: worker of 24 Sep (stores the per-character vote across a track's reads; adaptive confirmation hold); 4 cameras (AMD-POL-001, AMD-AMC-001, AMD-TRAF-001, AMD-TRAF-002) on one worker with HW_DECODE=auto (D3D11) and object detection on; ~4.5 analysed fps per camera; GTX 1650 Ti laptop

**These plates are synthetic registrations, not real Gujarat plates.** On the two stock-footage cameras the vehicles and scenes are real (Pexels stock footage, not Gujarat CCTV; the Ahmedabad locations are simulated) but every plate the painter found carries a synthetic registration in a clean font on a white plate; the other cameras show drawn rectangles. Precision on real plates is unmeasured.

| Camera | Footage | Class, view | anpr_viable | Stream | Sightings | Precision (exact) | Within one character | Capture rate, plates shown >= 1 s | Capture rate, every plate | Median plate box width (px) | Active minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMD-TRAF-001 | stock footage, painted plates | ptz, 3840x2160 of the source scaled 0.50x | no | 1920x1080 h264 25 fps | 324 | 91.0% (295/324) | 96.9% (314/324) | 22.5% (29/129) | 11.4% (31/271) | 56 | 16 |
| AMD-TRAF-002 | stock footage, painted plates | anpr, 1440x810 of the source scaled 1.33x | yes | 1920x1080 h265 25 fps | 1059 | 97.1% (1028/1059) | 98.1% (1039/1059) | 94.1% (64/68) | 69.6% (87/125) | 100 | 16 |
| AMD-AMC-001 | synthetic (drawn) | anpr, scene close, plate drawn ~368 px wide | yes | 1920x1080 h264 25 fps | 115 | 49.6% (57/115) | 83.5% (96/115) | 100.0% (4/4) | 100.0% (4/4) | 436 | 16 |
| AMD-POL-001 | synthetic (drawn) | anpr, scene mid, plate drawn ~200 px wide | yes | 1280x720 h264 25 fps | 17 | 35.3% (6/17) | 88.2% (15/17) | 100.0% (3/3) | 100.0% (3/3) | 241 | 13 |
| **All 2 stock footage cameras, pooled** | | | | | 1383 | 95.7% (1323/1383) | 97.8% (1353/1383) | 47.2% (93/197) | 29.8% (118/396) | | |
| **All 2 synthetic cameras, pooled** | | | | | 132 | 47.7% (63/132) | 84.1% (111/132) | 100.0% (7/7) | 100.0% (7/7) | | |

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

324 sightings from 2026-09-24 01:00 to 2026-09-24 01:15 IST; 46 distinct plates read, 15 of them not ground truth; 271 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 87 | 2.3% (2/87) |
| 0.5-1 s | 55 | 0.0% (0/55) |
| 1-2 s | 46 | 8.7% (4/46) |
| 2-5 s | 46 | 26.1% (12/46) |
| >= 5 s | 37 | 35.1% (13/37) |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 5 | 20.0% (1/5) |
| 0.5-0.7 | 46 | 58.7% (27/46) |
| 0.7-0.9 | 117 | 94.9% (111/117) |
| >= 0.9 | 156 | 100.0% (156/156) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ05S3469` x4: nearest `GJ05SL3469`, 1 edit
- `GJ05VD2496` x4: nearest `GJ05VB2496`, 1 edit
- `GJ16NP1715` x4: nearest `GJ18NP1715`, 1 edit
- `GJ05CM3468` x3: nearest `GJ05CH3468`, 1 edit
- `GJ16MK3152` x2: nearest `GJ16NK9152`, 2 edits

### AMD-TRAF-002 (Paldi Char Rasta, Ahmedabad (stock traffic footage))

1059 sightings from 2026-09-24 01:00 to 2026-09-24 01:15 IST; 99 distinct plates read, 12 of them not ground truth; 125 ground-truth plates; 0 injected (non-worker) rows left out.

| Time painted on screen | Plates | Captured exactly |
|---|---|---|
| 0-0.5 s | 31 | 29.0% (9/31) |
| 0.5-1 s | 26 | 53.8% (14/26) |
| 1-2 s | 34 | 88.2% (30/34) |
| 2-5 s | 34 | 100.0% (34/34) |
| >= 5 s | 0 | n/a |

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 4 | 0.0% (0/4) |
| 0.5-0.7 | 47 | 66.0% (31/47) |
| 0.7-0.9 | 362 | 98.9% (358/362) |
| >= 0.9 | 646 | 98.9% (639/646) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ06FY2044` x6: nearest `GJ06FV2044`, 1 edit
- `GJ13W8306` x5: nearest `GJ13WF8306`, 1 edit
- `GJ06F2044` x3: nearest `GJ06FV2044`, 1 edit
- `GJ84AC4013` x3: nearest `GJ38AC4013`, 2 edits
- `GJ18S2975` x2: nearest `GJ18JS2975`, 1 edit

### AMD-AMC-001 (Income Tax Circle, Ashram Road)

115 sightings from 2026-09-24 01:00 to 2026-09-24 01:15 IST; 11 distinct plates read, 7 of them not ground truth; 4 ground-truth plates; 0 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 4 | 0.0% (0/4) |
| 0.5-0.7 | 51 | 52.9% (27/51) |
| 0.7-0.9 | 60 | 50.0% (30/60) |
| >= 0.9 | 0 | n/a |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ11AB1234` x32: nearest `GJ01AB1234`, 1 edit
- `GJ01Z2000` x12: nearest `GJ01ZZ0001`, 2 edits
- `GJ05FF9012` x4: nearest `GJ05EF9012`, 1 edit
- `GJ11ZZ0001` x3: nearest `GJ01ZZ0001`, 1 edit
- `GJ01Z2006` x3: nearest `GJ01ZZ0001`, 3 edits

### AMD-POL-001 (Sarkhej-Gandhinagar Highway Toll Approach)

17 sightings from 2026-09-24 01:00 to 2026-09-24 01:14 IST; 7 distinct plates read, 4 of them not ground truth; 3 ground-truth plates; 0 injected (non-worker) rows left out.

| OCR confidence | Sightings | Exact |
|---|---|---|
| 0-0.5 | 1 | 0.0% (0/1) |
| 0.5-0.7 | 8 | 0.0% (0/8) |
| 0.7-0.9 | 6 | 66.7% (4/6) |
| >= 0.9 | 2 | 100.0% (2/2) |

Most frequent wrong reads (nearest ground-truth plate, edit distance):

- `GJ11ZZ0001` x8: nearest `GJ01ZZ0001`, 1 edit
- `GJ26HH3456` x1: nearest `GJ27GH3456`, 2 edits
- `LA27GH3456` x1: nearest `GJ27GH3456`, 2 edits
- `GJ27GH3455` x1: nearest `GJ27GH3456`, 1 edit

## Caveats

- Plates are synthetic registrations painted onto stock footage (or drawn); not real Gujarat plates. Real plates vary in font, layout (two-row, high-security, hand-painted), dirt, glare and IR at night. Precision on real plates is unmeasured.
- The stock clips are 60 s of Pexels footage re-encoded at up to 4 Mbps (`realclip.py`), replayed in a loop: the same vehicles pass again every loop, so precision is over repeated passes of the same painted plates (the detail gives how many distinct plates were read), not over as many different vehicles as there are sightings.
- The painter (`feedsim/realclip.py`) replaces only the plates its detector finds. A plate it missed keeps its original characters, and a read of it counts here as a wrong read. Such reads would fall outside the "within one character" share: a real registration is very unlikely to be one character from a painted one.
- The worker's settings (streams per machine, achieved analysis rate, code version) are not stored with the sightings; they are only what the Conditions lines above say.
