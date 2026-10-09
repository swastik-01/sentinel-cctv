# Capture-quality cut-offs from our own feed

Measured 2026-09-26 15:10 by `bench/quality_thresholds.py` on the stored evidence crops of AMD-TRAF-001, AMD-TRAF-002 (Pexels stock footage with synthetic plates painted on by `feedsim/realclip.py`; no real registration). Metrics from `capture_quality.assess()`: the plate box is recovered by undoing the worker's 15% padding; sharpness is the variance of the Laplacian with the plate resized to 64 px high, divided by the plate's grey variance; brightness (mean grey), contrast (grey standard deviation) and the clipped share (pixels at 5 or less or 250 or more) are on the plate, not the padding. The sandbox crops and the blind reviews were not used.

- Crops: 6228 (AMD-TRAF-001 1272, AMD-TRAF-002 4956); 4041 pass the size guidance (characters >= 10 px, plate >= 75 px).
- Layout by box shape: 2977 one-line, 3251 two-line; 221 oblique by the box-shape rule.
- Degradation sweep: 400 of the sized crops sampled (seed 7); 377 of them read as a valid Indian plate at confidence >= 0.6 by `PlateOCR` (CPU) and were swept. A read survives a step when it equals the reader's read of the untouched crop. Each degraded crop is re-encoded as JPEG 85, as the worker stores crops (step 0 is that re-encoding alone, the control); darkening and flattening add 2 grey levels of noise. Glare is judged on brightness: a veil of added grey washes the characters out, and the painted plates' white is already at 255, so the share of saturated pixels would start at an ideal real plates do not share.

## Cut-offs: where fewer than 80% of reads survive

| constant | degradation | value | reached |
|---|---|---|---|
| BLUR_BELOW | blur (sharpness below) | 0.0572 | yes |
| DARK_BELOW | dark (brightness below) | 57.2 | yes |
| FLAT_BELOW | flat (contrast below) | 45.1 | yes |
| GLARE_ABOVE | veil (brightness above) | 217 | yes |

Survival by step (step 0 is the control, re-encoded only; blur steps are sigma as a share of the plate height, dark and flat steps multiply the grey or its spread, veil steps add grey levels):

**blur**

| step | median sharpness | reads surviving |
|---|---|---|
| 0 | 0.309 | 100.0% |
| 0.004 | 0.308 | 99.2% |
| 0.008 | 0.23 | 98.9% |
| 0.012 | 0.128 | 98.1% |
| 0.016 | 0.083 | 91.2% |
| 0.02 | 0.055 | 79.0% |
| 0.025 | 0.037 | 60.7% |
| 0.03 | 0.027 | 50.9% |
| 0.04 | 0.016 | 36.3% |
| 0.06 | 0.008 | 0.0% |

**dark**

| step | median brightness | reads surviving |
|---|---|---|
| 0 | 155 | 100.0% |
| 0.7 | 108 | 96.6% |
| 0.5 | 77.4 | 91.5% |
| 0.35 | 54.1 | 78.2% |
| 0.25 | 38.6 | 64.7% |
| 0.18 | 27.7 | 45.1% |
| 0.12 | 18.4 | 21.0% |
| 0.08 | 12.2 | 8.5% |
| 0.05 | 7.6 | 0.3% |

**flat**

| step | median contrast | reads surviving |
|---|---|---|
| 0 | 110 | 100.0% |
| 0.7 | 77.4 | 96.3% |
| 0.5 | 55.3 | 90.5% |
| 0.35 | 38.7 | 73.5% |
| 0.25 | 27.7 | 54.6% |
| 0.18 | 19.9 | 35.8% |
| 0.12 | 13.3 | 17.2% |
| 0.08 | 8.9 | 2.1% |
| 0.05 | 5.6 | 0.0% |

**veil**

| step | median brightness | reads surviving |
|---|---|---|
| 0 | 155 | 100.0% |
| 30 | 171 | 98.7% |
| 60 | 184 | 98.1% |
| 90 | 198 | 94.7% |
| 120 | 210 | 90.2% |
| 150 | 222 | 72.4% |
| 180 | 233 | 23.6% |
| 210 | 243 | 5.3% |
| 230 | 249 | 0.3% |

## Percentiles

For reference. A low percentile here would be a cut-off at the painted plates' ideal: their p5 contrast is close to the largest grey spread an image can have (127.5), which ordinary plates under CCTV do not reach, so the cut-offs above come from the sweep instead.

### Crops that pass the size guidance (4041 crops)

| metric | p1 | p2 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p98 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plate_w | 75 | 75 | 77 | 80 | 89 | 140 | 174 | 194 | 201 | 210 | 215 |
| char_h | 14 | 16 | 18 | 19 | 21 | 29 | 37 | 43 | 46 | 50 | 53 |
| ratio | 0.206 | 0.237 | 0.253 | 0.269 | 0.298 | 0.358 | 0.667 | 0.715 | 0.738 | 0.771 | 0.797 |
| sharpness | 0.093 | 0.107 | 0.13 | 0.155 | 0.211 | 0.301 | 0.389 | 0.55 | 0.691 | 0.87 | 1.08 |
| brightness | 115 | 118 | 122 | 128 | 138 | 155 | 166 | 174 | 179 | 184 | 187 |
| contrast | 90.7 | 94.4 | 98.7 | 102 | 106 | 110 | 115 | 118 | 119 | 120 | 121 |
| clipped | 0.291 | 0.319 | 0.349 | 0.386 | 0.493 | 0.616 | 0.73 | 0.788 | 0.813 | 0.836 | 0.846 |

### All crops (6228 crops)

| metric | p1 | p2 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p98 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plate_w | 39 | 43 | 49 | 54 | 65 | 88 | 158 | 187 | 198 | 205 | 211 |
| char_h | 8 | 8 | 10 | 13 | 16 | 22 | 32 | 40 | 45 | 48.5 | 52 |
| ratio | 0.233 | 0.245 | 0.263 | 0.28 | 0.324 | 0.469 | 0.667 | 0.727 | 0.771 | 1.17 | 1.33 |
| sharpness | 0.078 | 0.0855 | 0.105 | 0.127 | 0.182 | 0.273 | 0.376 | 0.541 | 0.728 | 0.978 | 1.1 |
| brightness | 103 | 109 | 117 | 122 | 134 | 151 | 164 | 172 | 178 | 184 | 187 |
| contrast | 85.4 | 88 | 91.6 | 95.4 | 103 | 108 | 114 | 117 | 119 | 120 | 121 |
| clipped | 0.134 | 0.151 | 0.199 | 0.288 | 0.381 | 0.547 | 0.698 | 0.765 | 0.801 | 0.828 | 0.84 |

### AMD-TRAF-001 (1272 crops)

| metric | p1 | p2 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p98 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plate_w | 39 | 39 | 42 | 45 | 52 | 58 | 63 | 69 | 76 | 81.2 | 85.3 |
| char_h | 8 | 8 | 8 | 8 | 10 | 15 | 17 | 19 | 20 | 29 | 29 |
| ratio | 0.328 | 0.343 | 0.359 | 0.377 | 0.412 | 0.455 | 0.529 | 0.628 | 0.808 | 1.22 | 1.25 |
| sharpness | 0.07 | 0.073 | 0.0806 | 0.093 | 0.113 | 0.146 | 0.228 | 0.502 | 0.743 | 1.11 | 1.29 |
| brightness | 86.9 | 97.3 | 103 | 110 | 122 | 142 | 162 | 177 | 182 | 185 | 188 |
| contrast | 79.4 | 81.4 | 86.2 | 88.3 | 92.1 | 96.5 | 101 | 105 | 107 | 109 | 110 |
| clipped | 0.109 | 0.117 | 0.134 | 0.151 | 0.202 | 0.322 | 0.406 | 0.482 | 0.596 | 0.637 | 0.701 |

### AMD-TRAF-002 (4956 crops)

| metric | p1 | p2 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p98 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plate_w | 43 | 53 | 60 | 65 | 78 | 119 | 167 | 190 | 200 | 208 | 214 |
| char_h | 12 | 12 | 13 | 15 | 19 | 26 | 35 | 41 | 46 | 50 | 52 |
| ratio | 0.209 | 0.242 | 0.256 | 0.274 | 0.308 | 0.522 | 0.682 | 0.731 | 0.769 | 1.03 | 1.5 |
| sharpness | 0.096 | 0.111 | 0.134 | 0.165 | 0.221 | 0.301 | 0.384 | 0.549 | 0.728 | 0.909 | 1.08 |
| brightness | 115 | 117 | 122 | 127 | 138 | 153 | 164 | 172 | 177 | 182 | 187 |
| contrast | 94.3 | 96.3 | 99.1 | 102 | 106 | 110 | 115 | 118 | 119 | 120 | 121 |
| clipped | 0.278 | 0.294 | 0.322 | 0.355 | 0.466 | 0.607 | 0.717 | 0.777 | 0.806 | 0.832 | 0.844 |

