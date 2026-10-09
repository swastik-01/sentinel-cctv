# Capture quality by camera, checked against the blind reviews

Generated 2026-09-26 16:03 IST by `bench/quality_validate.py` (read-only), window 2026-01-01 00:00 to 2026-09-26 16:02 IST. Grades from `services/api/sentinel_api/capture_quality.py` (made at ingest and by `scripts/quality_backfill.py`): size cut-offs from published guidance (`docs/commercial-anpr.md`), blur, light and contrast cut-offs from our own stock-footage crops (`bench/results/quality_thresholds.md`). Nothing below was used to set them, and the grades and cut-offs were not changed after seeing it. The per-camera tier rules were changed after the first run of this file (not-a-plate captures left out, wording; see the end). Counts and rates only; intervals are 95% (Wilson).

- Graded sightings in the window: 8635 (good 4309, marginal 2199, poor 2127).
- Blind reviews in the window: 458, of which 0 have no grade (no crop). All blind reviews so far are by one team member.
- Re-grading the stored measurements gives back the stored grade for 8635 of 8635 sightings.

## By camera

Tiers and recommendations as the Health page computes them (`routers/quality.py` SQL, `camera_quality.py` rules): A at least 60% good and a median plate at least 100 px across, from 20 or more captures; C under 20% good, median characters under 10 px, or no plate read stored; B between. Captures a reviewer marked as not a plate (either review mode) are left out of the captures, grades and tier. Blind exact counts vehicle plates only (a crop reviewed as not a plate, or unreadable, is left out and counted apart).

| Camera | Tier | Why | Captures | Good / marginal / poor | Median plate px | Median char px | Main reasons (share of captures) | Blind exact | Not a plate (blind) | Recommendations |
|---|---|---|---|---|---|---|---|---|---|---|
| AMD-AMC-001 | A | 86% good, median plate 436 px | 1073 | 925 / 148 / 0 | 436 | 78 | low_confidence 14% | 20/31 | — | *model*: Crops are good but reads are wrong: retrain the reader with reviewed plates; *config*: Keep it ANPR-viable and analysed continuously |
| MHS-POL-001 | A | 77% good, median plate 436 px | 447 | 345 / 102 / 0 | 436 | 78 | low_confidence 23% | 10/22 | — | *model*: Crops are good but reads are wrong: retrain the reader with reviewed plates; *config*: Keep it ANPR-viable and analysed continuously |
| GNR-GSRTC-001 | A | 98% good, median plate 379 px | 419 | 409 / 10 / 0 | 379 | 52 | low_confidence 2% | 93/109 | — | *model*: Crops are good but reads are wrong: retrain the reader with reviewed plates; *config*: Keep it ANPR-viable and analysed continuously |
| AMD-POL-001 | A | 93% good, median plate 219 px | 249 | 231 / 18 / 0 | 219 | 29 | low_confidence 7% | 7/8 | — | *config*: Keep it ANPR-viable and analysed continuously |
| AMD-TRAF-002 | B | 46% good, median plate 120 px | 4953 | 2275 / 1726 / 952 | 120 | 26 | two_line 52%, small 27%, too_small 19%, oblique 3% | 113/120 | — | *camera*: Zoom in or move closer: plates need about 100-150 px across (now median 120 px; 46% of captures under size) |
| CAM06 | B | 55% good, median plate 104 px | 142 | 78 / 47 / 17 | 104 | 21 | small 27%, two_line 15%, too_small 12%, blurred 10% | 71/92 | — | *camera*: Zoom in or move closer: plates need about 100-150 px across (now median 104 px; 39% of captures under size); *model*: Crops are good but reads are wrong: retrain the reader with reviewed plates |
| CAM07 | B | 59% good, median plate 106 px | 56 | 33 / 22 / 1 | 106 | 22 | small 34%, low_confidence 9%, two_line 5%, low_contrast 2% | 19/27 | — | *camera*: Zoom in or move closer: plates need about 100-150 px across (now median 106 px; 36% of captures under size); *model*: Crops are good but reads are wrong: retrain the reader with reviewed plates |
| AMD-TRAF-001 | C | 0% of 1271 captures good | 1271 | 0 / 115 / 1156 | 58 | 15 | too_small 91%, two_line 52%, low_confidence 10%, small 9% | 19/24 | — | *camera*: Zoom in or move closer: plates need about 100-150 px across (now median 58 px; 100% of captures under size); *model*: Two-line plates: add two-line handling; *config*: Use for counts and viewing only; do not rely on plates |
| CAM12 | C | 0% of 1 capture good | 1 | 0 / 0 / 1 | 54 | 11 | blurred 100%, too_small 100% | 0/1 | — | *camera*: Zoom in or move closer: plates need about 100-150 px across (now median 54 px; 100% of captures under size); *camera*: Faster shutter (1/1000 s or less), higher bitrate, check focus; *config*: Marked ANPR-viable, but its captures do not bear that out: use for counts and viewing only until they do |
| CAM05 | C | its captures were reviewed as not plates | 0 | 0 / 0 / 0 | — | — | — | — | 24 | *config*: Use for counts and viewing only; do not rely on plates |

30 more cameras were enabled or analysed in the window with no graded capture (no plate read stored with a crop), config advice only: C, no plate read: CAM01, CAM02, CAM03, CAM04, CAM08, CAM09, CAM10, CAM11, CAM13, CAM14, CAM15, CAM16, CAM17, CAM18, CAM19, CAM20, CAM21, CAM22, CAM23, CAM24, CAM25, CAM26, CAM27, CAM28, CAM29, CAM30; not graded, not analysed in this window: AMD-AMC-002, GNR-PNCHT-002, GNR-POL-002; not graded, its reads have no crop to grade: GNR-POL-001.

## Do the grades predict a right read?

### Blind reviews of vehicle plates, by grade

Sandbox: the organisers' cameras, real Gujarat plates (in practice CAM06 and CAM07, and one read on CAM12). Own: our simulator's cameras (synthetic clips, and stock footage with synthetic plates painted on). *Image only* re-grades the same crops without the reader's confidence (reason `low_confidence`), so it shows what the size, blur, light and angle measurements say by themselves.

| Cameras | Grade | Exact (95% interval) | Image only: exact |
|---|---|---|---|
| sandbox | good | 53/66 = 80.3% (69–88%) | 54/69 = 78.3% (67–86%) |
| sandbox | marginal | 29/44 = 65.9% (51–78%) | 28/41 = 68.3% (53–80%) |
| sandbox | poor | 8/10 = 80.0% (49–94%) | 8/10 = 80.0% (49–94%) |
| sandbox | **all** | 90/120 = 75.0% (67–82%) | |
| own | good | 182/217 = 83.9% (78–88%) | 187/230 = 81.3% (76–86%) |
| own | marginal | 38/48 = 79.2% (66–88%) | 33/35 = 94.3% (81–98%) |
| own | poor | 42/49 = 85.7% (73–93%) | 42/49 = 85.7% (73–93%) |
| own | **all** | 262/314 = 83.4% (79–87%) | |

### Blind reviews by reason

A capture can carry several reasons, so the rows overlap; `(none)` is a capture graded good.

| Reason | Sandbox exact | Own exact |
|---|---|---|
| (none) | 53/66 = 80.3% (69–88%) | 182/217 = 83.9% (78–88%) |
| too_small | 8/10 = 80.0% (49–94%) | 42/49 = 85.7% (73–93%) |
| small | 23/35 = 65.7% (49–79%) | 27/28 = 96.4% (82–99%) |
| blurred | 6/9 = 66.7% (35–88%) | — |
| low_contrast | 1/2 = 50.0% (9–91%) | — |
| oblique | — | 2/3 = 66.7% (21–94%) |
| two_line | 11/13 = 84.6% (58–96%) | 68/74 = 91.9% (83–96%) |
| low_confidence | 1/6 = 16.7% (3–56%) | 7/20 = 35.0% (18–57%) |

### Our own cameras against the known plates

Every graded sighting on a camera whose plates are known, the stored read scored against them: exact, one character off, or further (far). Synthetic clips: every plate in view is known, so far is wrong. Stock clips: only the painted plates are known and other vehicles carry real plates, so far there includes reads that may be right and the exact rate is a floor.

| Clips | Grade | Sightings | Exact (95% interval) | One off | Far | Image only: exact |
|---|---|---|---|---|---|---|
| synthetic | good | 1910 | 1248/1910 = 65.3% (63–67%) | 552 | 110 | 1374/2188 = 62.8% (61–65%) |
| synthetic | marginal | 278 | 126/278 = 45.3% (40–51%) | 124 | 28 | — |
| synthetic | poor | 0 | — | 0 | 0 | — |
| synthetic | **all** | 2188 | 1374/2188 = 62.8% (61–65%) | 676 | 138 |  |
| stock | good | 2275 | 2255/2275 = 99.1% (99–99%) | 4 | 16 | 2306/2334 = 98.8% (98–99%) |
| stock | marginal | 1841 | 1795/1841 = 97.5% (97–98%) | 38 | 8 | 1744/1782 = 97.9% (97–98%) |
| stock | poor | 2108 | 1952/2108 = 92.6% (91–94%) | 134 | 22 | 1952/2108 = 92.6% (91–94%) |
| stock | **all** | 6224 | 6002/6224 = 96.4% (96–97%) | 176 | 46 |  |

Within each camera (one scene, so the grade is not standing in for the camera):

| Camera | Good: exact | Marginal: exact | Poor: exact |
|---|---|---|---|
| AMD-AMC-001 | 526/925 = 56.9% (54–60%) | 78/148 = 52.7% (45–61%) | — |
| AMD-POL-001 | 200/231 = 86.6% (82–90%) | 6/18 = 33.3% (16–56%) | — |
| AMD-TRAF-001 | — | 113/115 = 98.3% (94–100%) | 1044/1156 = 90.3% (88–92%) |
| AMD-TRAF-002 | 2255/2275 = 99.1% (99–99%) | 1682/1726 = 97.5% (97–98%) | 908/952 = 95.4% (94–97%) |
| GNR-GSRTC-001 | 360/409 = 88.0% (85–91%) | 1/10 = 10.0% (2–40%) | — |
| MHS-POL-001 | 162/345 = 47.0% (42–52%) | 41/102 = 40.2% (31–50%) | — |

### Crops that were not vehicle plates

Blind reviews typed as not a plate (or unreadable), by the grade their crop got. The grade measures the image, not what is in it.

| Cameras | Grade | Not a plate | Unreadable |
|---|---|---|---|
| sandbox | good | 13 | 0 |
| sandbox | marginal | 11 | 0 |

## What this shows

- Sandbox blind reviews: good 80.3% exact against poor 80.0% (no real difference); good 80.3% exact against marginal or poor 68.5% (good is read better but the intervals overlap).
- Own blind reviews: good 83.9% exact against poor 85.7% (good is **not** read better); good 83.9% exact against marginal or poor 82.5% (no real difference).
- Synthetic clips against the known plates: good 65.3% exact against marginal or poor 45.3% (good is read better and the intervals do not overlap).
- Stock clips against the known plates: good 99.1% exact against poor 92.6% (good is read better and the intervals do not overlap); good 99.1% exact against marginal or poor 94.9% (good is read better and the intervals do not overlap).

In plain words:

1. **On the blind reviews the grades do not separate readable from unreadable.** A poor capture was read exactly as often as a good one (sandbox poor 8/10 (80.0%) against good 53/66 (80.3%); own poor 42/49 (85.7%) against good 182/217 (83.9%)). The one strong signal is the reader's own confidence: captures with `low_confidence` were exact 1/6 (16.7%) on the sandbox and 7/20 (35.0%) on our own cameras. `small` on the sandbox (23/35 (65.7%) against 53/66 (80.3%) for captures with no reason) points the right way, but the intervals overlap.
2. **On our stock clips, with thousands of sightings, the grades order the error rate but poor is not unreadable**: good 2255/2275 (99.1%), marginal 1795/1841 (97.5%), poor 1952/2108 (92.6%) exact against the painted plates (a floor), and the same order inside AMD-TRAF-002 alone. Poor there is `too_small` (2108 of 2108) by the published size guidance, which is written for commercial readers; our reader still reads most of those painted, pure black-on-white plates. These are also the clips the blur and light cut-offs were measured on (from how reads survive degrading, not from the known plates), so they are not an independent test.
3. **Reader errors the image cannot show.** On the synthetic clips 2188 of 2188 captures are good by the image alone, yet 1374/2188 (62.8%) of the stored reads are exact. That is the reader, not the camera, and the camera report says so with its model recommendation (good crops, blind reads under 90% exact).
4. **Grades exist only for reads the worker stored.** A plate too small or blurred to read at all leaves no sighting, so it never gets a poor grade; the grade cannot show misses, and capture on real plates is unmeasured. Where a poor camera shows is in fewer plates per 1,000 frames, not in more wrong reads.

## Proposed fixes (not applied)

None of these is made here: the grades stay as set, and any change should be decided first and then checked on blind reviews made after it, not on the ones above.

1. **Count the reader's confidence as a problem, not only a note.** Today `low_confidence` alone makes a capture marginal and never poor; it is the only reason whose captures were read clearly worse (95% intervals clear of the good captures') in both review sets. Making it count towards poor like an image problem is a structural change to check on the next blind batch (a pre-registered gate, as in `bench/*_gates.md`), since this batch suggested it.
2. **Set our reader's own size floor on our own feed.** Keep the published sizes for the camera advice (they are what a commercial reader needs), but decide what makes a capture poor from a downscale sweep on the stock crops, as `bench/quality_thresholds.py` does for blur and light: shrink read crops step by step and find where the reads stop surviving. Not from the reviews above.
3. **Tier C is not proof a camera cannot read plates.** AMD-TRAF-001 is C on size alone, yet 1157/1271 (91.0%) of its stored reads match a painted plate exactly. Painted plates are cleaner than real ones at the same size, so this does not show real plates would read there; it shows size alone cannot settle the tier. Before calling a camera counts-only, the tier should weigh how many passing plates it reads (capture), which needs vehicles counted against plates read on the same frames.
4. **Small wording and evidence rules.** tier C is given on as little as one capture (CAM12 1): ask for 20 captures before grading C on grades, as A already does.

## Applied since the first run (26 Sep 2026)

Report rules only (`routers/quality.py`, `camera_quality.py`); the grades and cut-offs are unchanged, so every rate above is the same as before.

- Captures reviewed as not a plate are left out of a camera's captures, grades and tier, and counted apart (CAM05: 24, now tier C, "its captures were reviewed as not plates").
- The zoom advice quotes the share of captures under size next to the median.
- A camera with nothing graded in the window (not analysed, or reads with no crop) is marked not graded (`graded: false`) and gets no counts-only advice; the page shows it without a tier.
- "no plates seen" reads "no plate read"; a C camera the registry marks ANPR-viable says so; a C given on grades says how many captures it rests on.
- Not applied: C on fewer than 20 captures (a camera analysed for hours that stored one plate is counts-only in practice), and the proposed fixes above.
