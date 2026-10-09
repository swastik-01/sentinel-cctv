# Licence-clean detectors: adoption gates (pre-registered)

Written 2026-09-26 10:55 IST, before any plate candidate is trained, before either candidate is built into the product,
and before any gate below is scored. A candidate is adopted only if it passes every gate that applies to it. The gates
are not changed after a result is seen; a candidate that fails is recorded as failed. Nothing here is done before the
27 Sep submission: until a candidate is adopted, the AGPL models are what runs, and every number in the pack is theirs.

## What is replaced, and why

- **Plate detector**: `morsetechlab/yolov11-license-plate-detection`, AGPL-3.0 on its model card, which also says the
  same source images appear in its training and test splits and its "reported metrics ... are likely overestimated"
  (https://huggingface.co/morsetechlab/yolov11-license-plate-detection). The pack has never quoted those metrics.
- **COCO vehicle/person detector**: `yolo11n.pt` from the `ultralytics/assets` releases, AGPL-3.0
  (https://api.github.com/repos/ultralytics/assets).
- **The Ultralytics library** that runs both: AGPL-3.0 (https://raw.githubusercontent.com/ultralytics/ultralytics/main/LICENSE).
  The worker imports it, so the product stays under AGPL obligations until both detectors are replaced and the
  dependency is removed.

## Candidates (fixed now)

- **P, plate**: YOLOX-Tiny fine-tuned from the official COCO checkpoint `yolox_tiny.pth` (release 0.1.1rc0, 40,755,013
  bytes), one class, trained with hard-negative images (no boxes). FP32 throughout (GTX 16xx cards NaN in FP16). Two
  inference builds, 640×384 and 960×544 letterbox; the incumbent runs at 640 (640×384 on a 1080p frame). Exported to ONNX
  opset 17, run by ONNX Runtime's CUDA provider (`onnxruntime-gpu` 1.24.x, the CUDA 12 build; 1.30 needs CUDA 13).
  YOLOX-S only if Tiny fails D1 on recall and the failure analysis (validation data only) points to capacity; S then
  faces every gate, speed included.
- **O, vehicles and people**: YOLOX-Tiny COCO as released (no fine-tune), 960×544 or 640×384, keeping `objects.py`'s
  classes (0 person, 1 bicycle, 2 car, 3 motorcycle, 5 bus, 7 truck).
- For each of P and O the adopted build is the fastest one that passes every gate.
- Integration: a shared ONNX Runtime YOLOX module (letterbox, grid decode, NMS in numpy/OpenCV); settings
  `PLATE_BACKEND` and `OBJECT_BACKEND` (`ultralytics` default, `yolox`) with model paths and input sizes. `DETECTOR`
  (`yolo | classical | both`) keeps its meaning: `yolo` is whichever learned plate model the backend names.
  Ultralytics is imported only when a backend asks for it.

## Licence facts (each opened on 26 Sep at the URL given)

| Item | Licence / terms | Source |
|---|---|---|
| YOLOX code | Apache-2.0, "Copyright (c) 2021-2022 Megvii Inc." | https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/LICENSE |
| YOLOX weights | Release assets of the same repository; no separate weights licence, so the repository's Apache-2.0 is our reading | https://github.com/Megvii-BaseDetection/YOLOX/releases/tag/0.1.1rc0 |
| YOLOX training data | COCO train2017, 300 epochs; "we found ImageNet pre-training is no more beneficial, we thus train all the following models from scratch" (sec. 2.1) | https://arxiv.org/abs/2107.08430 |
| COCO | Annotations CC BY 4.0; "The COCO Consortium does not own the copyright of the images. Use of the images must abide by the Flickr Terms of Use"; users "accept full responsibility" | https://cocodataset.org/dataset/termsofuse.htm |
| ONNX Runtime | MIT; `onnxruntime-gpu` 1.24.4 MIT with CUDA 12 extras, 1.30.0 with CUDA 13 extras | https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE, https://pypi.org/pypi/onnxruntime-gpu/1.24.4/json |
| PyTorch (training only; already in the worker) | BSD-3 | https://raw.githubusercontent.com/pytorch/pytorch/main/LICENSE |
| OpenCV, ONNX | Apache-2.0 | https://raw.githubusercontent.com/opencv/opencv/4.x/LICENSE, https://raw.githubusercontent.com/onnx/onnx/main/LICENSE |
| fast-plate-ocr (not replaced) | MIT code; the README does not say what the `cct-xs-v2-global-model` weights were trained on | https://github.com/ankandrew/fast-plate-ocr |

The COCO lineage is shared by every COCO-pretrained detector, the current YOLO11n included: COCO's images come under
Flickr's terms, not a licence the dataset grants. We disclose it; if counsel rules out COCO lineage, P can be trained
from scratch at an accuracy and time cost, and O has no pretrained alternative. The OCR's training data is undocumented,
so "licence-clean" is never claimed for the OCR.

## Training data for P

**Train**, one manifest row per image (source, URL, licence, author where given, sha256, group, split), perceptual-hash
de-duplication across all sources before splitting, splits by photo group, clip or site:

| Source | Terms read | Use |
|---|---|---|
| Open Images V7, "Vehicle registration plate" (/m/01jfm_) | Annotations "licensed by Google LLC under CC BY 4.0"; images "listed as having a CC BY 2.0 license" with "no representations or warranties" (https://storage.googleapis.com/openimages/web/factsfigures_v7.html) | Train split for training, validation split for validation; keep author and OriginalURL; drop any image whose metadata licence is not CC BY 2.0 |
| CCPD | MIT (https://raw.githubusercontent.com/detectRecog/CCPD/master/LICENSE); README: "This dataset is open-source under MIT license" | At most 4,000 train images (3,000 Base, 1,000 from DB/Blur/Tilt/Rotate) so Chinese plates do not dominate; drop images where v0 finds a second, unlabelled plate |
| UC3M-LP | CC BY 4.0 (https://zenodo.org/api/records/17152029) | Its own 1,580 / 395 split; polygons to boxes |
| Nepali private plates | CC BY 4.0; "Prior permission was obtained from the parking spaces, building owners, and vehicle owners" (https://huggingface.co/datasets/mukulboro/nepali-private-license-plates) | The 1,172 original photos only, never the augmented copies |
| Mendeley, Dhaka "Vehicle License Plate Detection Dataset" | CC BY 4.0; collected in Dhaka, Ashulia and Narsingdi, 20 Oct to 2 Nov 2024 (https://data.mendeley.com/datasets/nntnnzffw4/3) | Needs boxes. The page says 2,947 images, the download holds 2,962 files: count again on conversion. 300 held out for T5 |
| Mendeley, Foggy-Hazy License Plates | CC BY 4.0; "manually collected using Canon-DSLR-1500D ... Jaipur, Delhi, and Gurugram" (https://data.mendeley.com/datasets/p3jr4555tf/1) | Needs boxes |
| Synthetic Indian plates | Our renderer, SIL OFL fonts only (no Windows fonts; no DejaVu, which the own-feed test plates use) | At most 20% of plate boxes, always alongside hard negatives |
| Hard negatives | Open Images Billboard, Poster, Traffic sign, Whiteboard images where the plate class is verified absent | About 1,500 box-free images |
| Own footage | Ours, if the team decides to record (consent is the team's call); never at a sandbox site; boxes only, no plate text | One site held out as T2 |

**Test only**: NightLPBD (CC BY 4.0, "for any purpose (academic or commercial)", but the card does not say who took the
photos: https://huggingface.co/datasets/thasan3003/NightLPBD_Nighttime_License_Plates_of_Bangladesh; its train split
may move to training only if the authors confirm in writing before v1 training starts, its test split stays test);
the raw Pexels sources of AMD-TRAF-001/002 (T1); Kaggle "Gujarat Vehicle Number Plates" (Apache-2.0 as declared,
photographer not stated; not re-read here, it needs a Kaggle login).

**Excluded from training**: all Pexels footage. The licence allows commercial use and modification
(https://www.pexels.com/license/), but the terms of service (§8) say "Data mining, extraction, scraping and the use of
programs or robots for automatic data collection ... is strictly prohibited for all unauthorised purposes, including
without limitation for machine learning purposes" and "Bulk, large-scale or systematic copying of Content is strictly
prohibited unless explicit permission has been granted by us" (https://www.pexels.com/terms-of-service/). Also
excluded: Roboflow `license-plate-recognition-rxg4e` (the incumbent's training set, so not even a fair test);
academic-only, non-commercial or no-derivatives sets; sets scraped from Google Images, YouTube or platesmania; sets
labelled with the AGPL model; the organisers' sandbox (never downloaded, never trained on).

**Labels.** Never from the AGPL detector, including the boxes `realclip.py` paints. v0, trained on the sets that come
with boxes, pre-labels training images for people to correct. **Test-set boxes (T1, T2, T6) are drawn by hand with no
model's boxes shown**, so neither model is favoured. An ATTRIBUTION file (CC BY sources, authors where given, YOLOX's
Apache-2.0 notice) ships with the weights.

## Held-out tests (frozen before training; never trained on or tuned against)

- **T1**: about 380 frames of the raw Pexels 30608914 and 30609021 clips at 2 fps, scaled to 1920 px wide as the product
  sees a 1080p stream; every plate boxed by hand.
- **T2**: the held-out own-footage site, day and night (only if footage is recorded).
- **T3**: Kaggle Gujarat, 355 images (only if obtained).
- **T4**: Open Images test (2,065 images), UC3M-LP test (395), CCPD Challenge (1,000). Reported, not gated: the
  incumbent's training set probably overlaps Open Images.
- **T5**: NightLPBD test (190) and 300 held-out Dhaka Bikes, CNG and Bus images: two-line and night plates.
- **T6**: 300 plate-free frames of hoardings, shop signs and phone numbers (own footage, else Open Images Billboard and
  Poster test-split images with the plate class verified absent).
- **T7**: synthetic simulator frames with exact boxes from `synth.py`'s geometry (the demo depends on them).

## Gates

**L: licence (P).** Every training image has a manifest row from the Train list; none from Test only or Excluded; no
label from the AGPL model; no sandbox or Pexels frame; the ATTRIBUTION file exists. O uses YOLOX's released weights
unchanged.

**D0: integrity (P and O).**
- ONNX against PyTorch: max absolute difference ≤ 5e-3 on 20 frames; FP32; no NaN on the GTX 1650 Ti.
- The runtime change (`fast-plate-ocr[onnx]` to `fast-plate-ocr` plus `onnxruntime-gpu` 1.24.x; the two packages install
  the same module, and the OCR stays on the CPU provider): `bench/ocr_ab.py` reads on sandbox-v1, reject-v1 and
  ownfeed-v1 identical to the stored runs in `data/ocr-eval/runs`, and `bench/plate_gate.py`'s tables unchanged.
  Otherwise every OCR figure in the documents is re-measured before adoption.
- With both backends on YOLOX the worker never imports `ultralytics` (a unit test on `sys.modules`).
- `pytest`, `smoke.py` 34/34, `security_checks.py` 19/19.

**D1: detection on held-out tests (P).** Recall at IoU 0.5 on plates at least 30 px wide, and false positives per image.
The incumbent runs at its product settings (640, confidence 0.35); the candidate at the threshold that maximises F1 on
its validation split, fixed before any test is scored.
- T1: the 95% bootstrap interval (resampling runs of 10 consecutive frames) of candidate minus incumbent recall has a
  lower bound above −3 points.
- T2 (if recorded): the same bound. T3 (if obtained): lower bound above −5 points.
- T5: candidate recall at least incumbent − 3 points.
- T6: false positives per image no higher than the incumbent's, and false-positive crops that then pass the OCR gate
  and the not-a-plate rule no more than the incumbent's.
- T7: recall ≥ 0.98 and at least incumbent − 1 point.

**D2: the product on own feeds (P, and O on its own).** AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001, AMD-AMC-001 under the
conditions of `bench/results/anpr_eval_current.md` (one worker, `HW_DECODE=auto`, object detection on,
`STATIC_TEXT_WINDOW_S=0`, mains power); baseline and candidate in alternating 10-minute windows (A B A B) in one
session, scored by `scripts/anpr_eval.py`, pooled per arm.
- Capture of plates shown ≥ 1 s: candidate at least baseline − 3 plates on AMD-TRAF-002 (of 68) and on AMD-TRAF-001
  (of 129).
- Exact precision over attributable sightings (within 2 edits of a ground-truth plate), both stock cameras pooled: at
  least baseline − 1.5 points.
- Unattributed sightings (3 or more edits from every ground-truth plate) are checked by crop as real unpainted plate,
  not a plate, or garbled; not-a-plate at most baseline + 2.
- Bias: `realclip.py` painted only the plates the AGPL detector found, and left the rest as they were. This test can show
  non-inferiority, never a gain, and a better detector will read some real Mumbai registrations.
- Before the first candidate run, `anpr_eval.py` gains an option that counts but never prints unattributed reads
  (today it prints the five most frequent wrong reads verbatim); the candidate runs' unattributed sightings are deleted
  after the check. No plate text leaves `data/`.

**D3: live sandbox yield (P).** Organisers' sandbox, live only. CAM06 and CAM07, alternating 15-minute windows (A B A B)
in one session: plates stored per 1,000 analysed frames at least 0.9 × baseline, pooled; share of stored plates exact
in the team's blind check (Plate review) at least baseline − 5 points; not-a-plate sightings no more than baseline. If
the sandbox cannot be reached after 27 Sep, D3 is recorded as not run: P may then become the default only if T2 ran and
passed; otherwise P stays behind its setting (off) through the finale, and the documents say the licence-clean plate
detector is not yet checked on government feeds.

**D4: speed (P and O as they would ship).** Mains power, other workloads stopped, baseline and candidate back to back
in one session, best of three rounds.
- P: time per 1080p frame at batch 4, letterbox to boxes included, at most 1.3 × the incumbent at its product settings.
- O: time per frame reported, not gated on its own.
- End to end: 4 cameras under the D2 conditions, analysed fps per camera at least 0.9 × baseline; 8 cameras with
  hardware decode (conditions of `bench/results/decode.md`) at least 0.85 × baseline; object frames per count window
  at least 0.9 × baseline; `latency_report.py` median first read to alert at most baseline + 0.25 s and p95 at most
  baseline + 0.5 s; peak GPU memory at most 3.3 GB of 4 GB.

**D5: counts and vehicle type (O).** Boxes checked by a person on 40 frames (20 per stock clip, every 3 s from the loop
start, at the 1080p the product sees): person, bicycle, car, motorcycle, bus, truck; objects under 12 px tall or more
than half hidden are ignored. The 24 frames of the research proxy may seed boxes but are not among the 40; the
candidate's `MIN_OBJECT_CONF` is set on those 24 to match the incumbent's precision there, then fixed.
- Vehicles (all five classes as one) and persons, each: recall at least the incumbent's, precision at least incumbent
  − 3 points.
- Vehicle type on matched vehicle boxes: accuracy at least incumbent − 2 points.
- In the D2 run: sightings with a vehicle type and with a colour, each at least baseline − 3 points; no class the
  baseline counts drops to zero; `detection_report.py` per-class counts shown side by side (reported, not gated: a
  detector that sees more counts more).
- The intrusion demo zone on its stock clip still raises its alert in a 10-minute run.
- The research proxy found most of the accuracy gain comes from the larger input (YOLO11n at 960×544 was also far
  better than at 640). The reason to switch is the licence, and the claim must say so.

## Decision

- O is decided on its own (L does not apply; D0, D2, D4, D5), **by 2 Oct 2026**.
- P needs L and D0 to D4. **Decision by 9 Oct 2026 18:00 IST**; code freeze 10 Oct. Undecided by then: the finale runs
  the AGPL plate model, and the documents keep today's disclosure.
- Candidates: P-v1, and at most one retry P-v2 after a failure, analysed on validation data only; T1 to T7 are never
  used to tune.
- Only when P and O are both adopted and `ultralytics` is gone from the worker's dependencies may any document say
  "licence-clean detection", and then only for detection (not the OCR).
- If adopted, every document that names the detectors, their licences or a number they produce (anpr_eval, detection
  report, latency, decode, capacity) is re-measured and updated together, and the HLD version bumped.

## Schedule (estimates, not measurements)

| When | Work |
|---|---|
| 27 Sep | Submission. No detector change in the product. |
| 28 Sep | Downloads (about 15 to 25 GB without Pexels), converters, manifest, de-duplication, splits; the `anpr_eval.py` redaction option. |
| 29 Sep | O: ONNX Runtime backend, tests, runtime package swap (needs the user's go: it changes `pyproject.toml` and `uv.lock`), D0 OCR parity, the 40 hand-checked frames. P: a 30-minute calibration run measures images per second and peak VRAM at batch 4 and 8 (640 input, FP32); the plan below is re-derived from it. |
| 29–30 Sep night | P-v0 on Open Images, CCPD (4,000), UC3M-LP and Nepali: about 13,000 images × 30 epochs. At an assumed 10 to 15 images/s on the GTX 1650 Ti, 7 to 11 h. |
| 30 Sep – 2 Oct | O gates and decision. |
| 30 Sep – 4 Oct | Labelling with v0 pre-labels (Dhaka, Foggy; own footage if recorded) and T1, T6 by hand: about 20 to 25 person-hours, the team's. Synthetic plate renderer. P backend in `detect.py`. |
| 4 – 6 Oct | P-v1 fine-tuned from v0 on the full mix (about 20,000 to 23,000 images × 30 epochs): 11 to 19 h on the laptop (two nights), or 2 to 4 h on a rented GPU. |
| 6 – 8 Oct | Gates D0 to D4 (about 5 h of GPU), blind review for D3. |
| 9 Oct | Decision; documents if adopted. |

All training on mains power (the research timings were taken on battery). About 20 to 30 GPU hours in total on the
laptop, which also runs the sandbox and demo work: book the nights.
