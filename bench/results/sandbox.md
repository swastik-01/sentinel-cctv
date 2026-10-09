# Sandbox cameras: onboarding and analytics on the organisers' feeds

Generated 2026-09-25 23:48 IST by `bench/sandbox_summary.py` (read-only database access).
Source: the organisers' sandbox camera grid (<sandbox-grid>): 30 cameras, recorded footage replayed as live streams on a common timeline, looping. Onboarded over RTSP (TCP) with the team's credentials by `scripts/onboard_sandbox.py`; relayed on demand by MediaMTX; analysed on the GTX 1650 Ti laptop, 4 cameras at a time, by `scripts/rotate_worker.py`.

The sandbox catalogue (`cameras.json`) gives only an id and a name per camera. Department, district and position are our reading of the names and of the pictures (`data/gov-sandbox/locations.json`), approximate, and recorded in each camera's address field; a camera we could not place has no position. Nothing here is the organisers' data beyond the id, the name and the streams.

**Onboarding.** 30 cameras onboarded by stream URL; probe time per camera 1.0–2.2 s, median 1.1 s (first onboarding 2026-09-25 19:57 IST). Codecs: H.264, H.265; resolutions 960x576, 1280x720, 1280x960, 1920x1080, 2560x1440. Placed on the map: 24 of 30.

**Analysis.** 17 rotation runs from 2026-09-25T20:07:49 to 2026-09-25T23:48:08 IST (run logs in `data/rotation/`); each camera's minutes below.

| Camera | Name | Dept (ours) | Codec, resolution | Placed | Minutes analysed | Frames analysed (objects) | Vehicles avg / peak in view | People avg / peak | Plate reads (distinct) | Intrusion alerts |
|---|---|---|---|---|---|---|---|---|---|---|
| CAM01 | 01 Chiman bhai Bridge | HOME | H.264 1920x1080 | no | 24 | 2,164 | 3.6 / 12 | 0.1 / 3 | 0 (0) | 0 |
| CAM02 | 02 Janpath | HOME | H.264 1920x1080 | no | 18 | 2,684 | 1.9 / 8 | 0.3 / 4 | 0 (0) | 0 |
| CAM03 | 03 O.N.G.C. Office | HOME | H.264 1280x720 | yes | 24 | 2,091 | 0.0 / 2 | 0.0 / 2 | 0 (0) | 0 |
| CAM04 | 04 Paldi Circle | HOME | H.264 1920x1080 | yes | 24 | 2,741 | 2.8 / 10 | 1.1 / 9 | 0 (0) | 0 |
| CAM05 | 05 Visat teen Rasta | HOME | H.264 1920x1080 | yes | 18 | 2,649 | 2.8 / 10 | 0.2 / 3 | 24 (3) | 0 |
| CAM06 | 06 Timbavadi gate-Junagadh | HOME | H.265 1920x1080 | yes | 24 | 2,049 | 2.0 / 8 | 2.5 / 10 | 69 (60) | 0 |
| CAM07 | 07 hero-showroom-gir-somnath | HOME | H.264 1920x1080 | yes | 24 | 1,022 | 0.0 / 2 | 0.1 / 2 | 6 (6) | 0 |
| CAM08 | 08 majewadi-gate-junagadh | HOME | H.264 1920x1080 | yes | 24 | 260 | 0.0 / 1 | 0.0 / 1 | 0 (0) | 0 |
| CAM09 | 09 new-bypass-near-by-circle-junagadh-2 | HOME | H.264 1920x1080 | yes | 24 | 2,347 | 0.0 / 2 | 0.0 / 1 | 0 (0) | 0 |
| CAM10 | 10 char-chowk-road-2-junagadh | HOME | H.264 1920x1080 | yes | 24 | 1,844 | 2.8 / 9 | 2.3 / 10 | 0 (0) | 0 |
| CAM11 | 11 dolatpara-junagadh | HOME | H.264 1920x1080 | yes | 18 | 1,981 | 1.5 / 11 | 0.6 / 8 | 0 (0) | 0 |
| CAM12 | 12 Tri Mandir Adalaj Tollnaka | HOME | H.265 1280x720 | yes | 36 | 3,940 | 0.1 / 3 | 0.1 / 3 | 1 (1) | 0 |
| CAM13 | 13 CN Vidhyalaya | HOME | H.264 1920x1080 | yes | 24 | 2,682 | 2.2 / 10 | 0.5 / 4 | 0 (0) | 0 |
| CAM14 | 14 Delight RLVD | HOME | H.264 1920x1080 | no | 36 | 3,289 | 2.0 / 12 | 0.3 / 4 | 0 (0) | 0 |
| CAM15 | 15 Suvidha park | HOME | H.264 1920x1080 | yes | 36 | 2,019 | 1.2 / 6 | 0.4 / 3 | 0 (0) | 0 |
| CAM16 | 16 Visat P2 | HOME | H.264 1920x1080 | yes | 36 | 3,718 | 2.6 / 10 | 0.2 / 4 | 0 (0) | 0 |
| CAM17 | 17 Rajkot Bus Port CCTV | GSRTC | H.265 1920x1080 | yes | 48 | 5,472 | 1.0 / 5 | 0.8 / 8 | 0 (0) | 15 |
| CAM18 | 18 Rajkot CCTV | HOME | H.265 1920x1080 | yes | 48 | 5,855 | 1.4 / 8 | 1.7 / 9 | 0 (0) | 16 |
| CAM19 | 19 KHAPARIA GRAM PANCHAYAT , TALUKA GANDEVI, DISTRICT NAVSARI | PNCHT | H.264 1280x720 | yes | 24 | 556 | 0.0 / 1 | 0.3 / 5 | 0 (0) | 0 |
| CAM20 | 20 Mohanpura | HOME | H.264 1280x720 | no | 24 | 728 | 0.0 / 2 | 0.0 / 1 | 0 (0) | 0 |
| CAM21 | 23 Patan Dethali Char Rasta | HOME | H.264 1920x1080 | yes | 24 | 1,248 | 0.0 / 1 | 0.0 / 1 | 0 (0) | 0 |
| CAM22 | 28 BK Mervada tran Rasta | HOME | H.265 1920x1080 | no | 24 | 2,673 | 0.0 / 0 | 0.0 / 1 | 0 (0) | 0 |
| CAM23 | 30 kheram | HOME | H.264 1280x720 | no | 24 | 740 | 0.2 / 2 | 0.2 / 3 | 0 (0) | 0 |
| CAM24 | 33 dehgam | HOME | H.264 960x576 | yes | 24 | 949 | 0.1 / 2 | 0.0 / 2 | 0 (0) | 0 |
| CAM25 | 34 dhanori | HEALTH | H.264 1280x960 | yes | 24 | 2,795 | 0.1 / 3 | 0.2 / 3 | 0 (0) | 0 |
| CAM26 | 35 TANKAL | HEALTH | H.265 2560x1440 | yes | 24 | 2,044 | 0.0 / 1 | 0.0 / 0 | 0 (0) | 0 |
| CAM27 | 36 bilimora | GSRTC | H.264 1280x960 | yes | 24 | 1,950 | 0.2 / 2 | 0.0 / 1 | 0 (0) | 0 |
| CAM28 | 37 bilimora | GSRTC | H.264 1280x960 | yes | 24 | 1,645 | 0.0 / 0 | 0.3 / 3 | 0 (0) | 0 |
| CAM29 | 38 bilimora | GSRTC | H.264 1280x960 | yes | 24 | 1,626 | 0.0 / 1 | 1.0 / 4 | 0 (0) | 0 |
| CAM30 | Gandhidham Rambaugh p2 | HEALTH | H.264 1920x1080 | yes | 18 | 931 | 3.7 / 12 | 1.1 / 7 | 0 (0) | 0 |

Totals: 66,692 frames analysed for objects; 100 plate reads on 4 camera(s); 31 intrusion alerts on 2 camera(s).

Definitions: a frame analysed is one frame the object detector ran on (per-minute count rows). Average in view is detections per analysed frame; peak is the most in any single frame. A plate read is one stored sighting (a vehicle's pass, voted across its reads). Intrusion alerts come from two demo zones we drew (CAM17 walkway, CAM18 junction corner: simulated restricted areas), at most one per zone per 120 s.
