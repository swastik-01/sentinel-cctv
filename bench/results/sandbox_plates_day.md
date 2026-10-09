# Sandbox cameras: can plates be read?

Generated 2026-09-26 06:50 IST by `bench/sandbox_plates.py`; frames read live 2026-09-26 06:34–06:50 IST through Sentinel's relay, 20 per camera about 0.5 s apart, held in memory only. The sandbox replays fixed recorded clips, each camera's from one time of day and looping, so the light a camera shows is its clip's, whatever the time of this run; the traffic depends on where its loop is.

Stages as the worker runs them: YOLO plate detector at confidence ≥ 0.35 (the worker uses 640 px; 1280 px shown for comparison), plus the classical text-line candidates at 640 px; OCR (`cct-xs-v2-global-model`) at confidence ≥ 0.35; then the Indian-plate format check.

Brightness is the mean grey level (0–255) of the frames read. It describes the camera's clip, not the time of day of this run: roughly, under 60 is a clip recorded at night.

| Camera | Frames | Frame size | Brightness | Plate boxes 640 px | Median width 640 (px) | Plate boxes 1280 px | Median width 1280 (px) | OCR ≥ floor (640 / 1280) | Valid Indian plates (640 / 1280) |
|---|---|---|---|---|---|---|---|---|---|
| CAM01 | 20 | 1920x1080 | 91 | 1 | 58 | 5 | 39 | 0 / 0 | 0 / 0 |
| CAM02 | 20 | 1920x1080 | 90 | 0 | — | 3 | 47 | 1 / 0 | 0 / 0 |
| CAM03 | 20 | 1280x720 | 71 | 5 | 87 | 1 | 87 | 0 / 0 | 0 / 0 |
| CAM04 | 20 | 1920x1080 | 88 | 2 | 45 | 0 | — | 0 / 0 | 0 / 0 |
| CAM05 | 20 | 1920x1080 | 95 | 2 | 69 | 1 | 76 | 6 / 0 | 5 / 0 |
| CAM06 | 20 | 1920x1080 | 93 | 2 | 56 | 7 | 55 | 1 / 2 | 0 / 0 |
| CAM07 | 20 | 1920x1080 | 46 | 1 | 80 | 15 | 45 | 1 / 3 | 0 / 0 |
| CAM08 | 20 | 1920x1080 | 81 | 6 | 57 | 6 | 44 | 1 / 0 | 0 / 0 |
| CAM09 | 20 | 1920x1080 | 4 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM10 | 20 | 1920x1080 | 85 | 6 | 54 | 3 | 29 | 0 / 0 | 0 / 0 |
| CAM11 | 20 | 1920x1080 | 99 | 2 | 67 | 23 | 38 | 0 / 0 | 0 / 0 |
| CAM12 | 20 | 1280x720 | 109 | 15 | 42 | 17 | 39 | 5 / 4 | 2 / 3 |
| CAM13 | 20 | 1920x1080 | 88 | 1 | 64 | 1 | 122 | 0 / 0 | 0 / 0 |
| CAM14 | 20 | 1920x1080 | 100 | 2 | 89 | 26 | 82 | 1 / 0 | 0 / 0 |
| CAM15 | 20 | 1920x1080 | 88 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM16 | 20 | 1920x1080 | 97 | 0 | — | 6 | 45 | 0 / 0 | 0 / 0 |
| CAM17 | 20 | 1920x1080 | 122 | 0 | — | 2 | 29 | 0 / 0 | 0 / 0 |
| CAM18 | 20 | 1920x1080 | 94 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM19 | 20 | 1280x720 | 67 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM20 | 20 | 1280x720 | 105 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM21 | 20 | 1920x1080 | 118 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM22 | 0 | | | | | | | | |
| CAM23 | 20 | 1280x720 | 67 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM24 | 20 | 960x576 | 130 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM25 | 20 | 1280x960 | 74 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM26 | 20 | 2560x1440 | 140 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM27 | 20 | 1280x960 | 92 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM28 | 20 | 1280x960 | 136 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM29 | 20 | 1280x960 | 119 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM30 | 6 | 1920x1080 | 89 | 0 | — | 6 | 46 | 0 / 0 | 0 / 0 |

Valid reads: 10 (CAM05 5, CAM12 5)

A valid read here is one frame's OCR output that passes the format check, before the worker's vote across a vehicle's reads; it is not checked against the true plate (the sandbox gives no ground truth).

*Wording corrected on 26 Sep 2026 evening to match the script (the sandbox replays fixed clips, so this run's clock time says nothing about the light); every number is from the original run, which was not repeated.*
