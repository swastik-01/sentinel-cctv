# Sandbox cameras: can plates be read?

Generated 2026-09-25 21:07 IST by `bench/sandbox_plates.py`; frames read live 2026-09-25 20:48–21:07 IST through Sentinel's relay, 20 per camera about 0.5 s apart, held in memory only. The sandbox replays fixed recorded clips, each camera's from one time of day and looping, so the light a camera shows is its clip's, whatever the time of this run; the traffic depends on where its loop is.

Stages as the worker runs them: YOLO plate detector at confidence ≥ 0.35 (the worker uses 640 px; 1280 px shown for comparison), plus the classical text-line candidates at 640 px; OCR (`cct-xs-v2-global-model`) at confidence ≥ 0.35; then the Indian-plate format check.

| Camera | Frames | Frame size | Plate boxes 640 px | Median width 640 (px) | Plate boxes 1280 px | Median width 1280 (px) | OCR ≥ floor (640 / 1280) | Valid Indian plates (640 / 1280) |
|---|---|---|---|---|---|---|---|---|
| CAM01 | 20 | 1920x1080 | 1 | 44 | 0 | — | 1 / 0 | 0 / 0 |
| CAM02 | 20 | 1920x1080 | 1 | 71 | 0 | — | 0 / 0 | 0 / 0 |
| CAM03 | 20 | 1280x720 | 5 | 87 | 3 | 85 | 0 / 0 | 0 / 0 |
| CAM04 | 20 | 1920x1080 | 0 | — | 1 | 20 | 0 / 0 | 0 / 0 |
| CAM05 | 20 | 1920x1080 | 1 | 40 | 5 | 46 | 20 / 0 | 19 / 0 |
| CAM06 | 20 | 1920x1080 | 3 | 68 | 7 | 52 | 3 / 3 | 3 / 0 |
| CAM07 | 0 | | | | | | | |
| CAM08 | 0 | | | | | | | |
| CAM09 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM10 | 20 | 1920x1080 | 0 | — | 1 | 106 | 0 / 0 | 0 / 0 |
| CAM11 | 20 | 1920x1080 | 2 | 50 | 2 | 40 | 0 / 0 | 0 / 0 |
| CAM12 | 20 | 1280x720 | 0 | — | 8 | 35 | 0 / 0 | 0 / 0 |
| CAM13 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM14 | 20 | 1920x1080 | 0 | — | 5 | 58 | 3 / 0 | 0 / 0 |
| CAM15 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM16 | 20 | 1920x1080 | 0 | — | 3 | 201 | 0 / 1 | 0 / 0 |
| CAM17 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM18 | 20 | 1920x1080 | 0 | — | 1 | 19 | 0 / 0 | 0 / 0 |
| CAM19 | 20 | 1280x720 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM20 | 20 | 1280x720 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM21 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM22 | 20 | 1920x1080 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM23 | 20 | 1280x720 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM24 | 20 | 960x576 | 0 | — | 0 | — | 5 / 0 | 0 / 0 |
| CAM25 | 20 | 1280x960 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM26 | 20 | 2560x1440 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM27 | 20 | 1280x960 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM28 | 20 | 1280x960 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM29 | 20 | 1280x960 | 0 | — | 0 | — | 0 / 0 | 0 / 0 |
| CAM30 | 20 | 1920x1080 | 12 | 59 | 17 | 61 | 0 / 1 | 0 / 0 |

Valid reads: 22 (CAM05 19, CAM06 3). The CAM05 reads are a hoarding's phone number taken for a plate (see `sandbox_eye.md`); raw reads are not listed because a read can be a real registration.

A valid read here is one frame's OCR output that passes the format check, before the worker's vote across a vehicle's reads; it is not checked against the true plate (the sandbox gives no ground truth).

*Wording corrected on 26 Sep 2026 evening to match the script (the sandbox replays fixed clips, so this run's clock time says nothing about the light); every number is from the original run, which was not repeated.*
