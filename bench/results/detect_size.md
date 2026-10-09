# Plate detector input size on our own clips

Generated 2026-09-26 15:38 IST by `bench/detect_size.py`: every 25th frame of the 60 s clips `feedsim/media/AMD-TRAF-001.mp4` and `AMD-TRAF-002.mp4` (1920x1080, 25 fps; Pexels stock footage with synthetic registrations painted on, not real Gujarat plates), through the product's plate path at each detector size: YOLO plate detector (conf 0.35) plus the classical finder, padded crop, `PlateOCR`, the worker's gate. CPU only, 2 threads, below-normal priority, on the laptop while a live worker used the GPU. No tracker or vote: counts are per sampled frame. Counts and rates only.

| Camera | Detector size | Frames | Painted plates in those frames | YOLO boxes | Gated reads | Exact reads (of a plate painted in that frame) | Exact from YOLO / classical | Near (1-2 edits) | Other gated reads | Exact of gated reads | Painted plates read exactly at least once, of plates shown >= 1 s | Median box width of exact reads (px) | YOLO CPU ms per frame |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMD-TRAF-001 | 640 | 60 | 580 | 88 | 22 | 17/580 = 2.9% | 17 / 0 | 4 | 1 | 17/22 = 77.3% | 13/129 = 10.1% | 61 | 196 |
| AMD-TRAF-001 | 960 | 60 | 580 | 154 | 44 | 30/580 = 5.2% | 30 / 0 | 10 | 4 | 30/44 = 68.2% | 22/129 = 17.1% | 56 | 197 |
| AMD-TRAF-001 | 1280 | 60 | 580 | 290 | 47 | 34/580 = 5.9% | 34 / 0 | 8 | 5 | 34/47 = 72.3% | 23/129 = 17.8% | 56 | 348 |
| AMD-TRAF-002 | 640 | 60 | 144 | 100 | 96 | 89/144 = 61.8% | 88 / 1 | 3 | 4 | 89/96 = 92.7% | 53/68 = 77.9% | 125 | 131 |
| AMD-TRAF-002 | 960 | 60 | 144 | 156 | 147 | 127/144 = 88.2% | 126 / 1 | 3 | 17 | 127/147 = 86.4% | 64/68 = 94.1% | 91 | 241 |
| AMD-TRAF-002 | 1280 | 60 | 144 | 162 | 155 | 132/144 = 91.7% | 131 / 1 | 2 | 21 | 132/155 = 85.2% | 65/68 = 95.6% | 88 | 318 |

## Reading it

- Exact reads over painted plates in the sampled frames is a per-frame read rate: a plate painted far away or half hidden counts in the denominator, so it is far below 100% at any size.
- Capture here is whether a single frame, sampled once a second, reads the plate; the product analyses about 4.5 frames a second and votes, so its capture (`anpr_eval_current.md`) is higher. Compare sizes, not levels.
- Other gated reads match no plate painted in that frame by 2 edits or fewer: a real plate the painter missed (its characters are unlabelled), a painted plate outside its logged frames, or text that is not a plate. The product's tracker needs 2 reads (or one confident read on a slow camera) before it stores any of them.
- The classical finder runs on a 960 px copy whatever the detector size; it is unioned in as in the product.
- CPU milliseconds are only for comparing sizes; on the GPU the cost ratio is similar (about the square of the size ratio) but the absolute time is far smaller.
