# Sandbox cameras in two runs, 25 Sep evening and 26 Sep morning: plate sightings stored

Generated 2026-09-26 17:28 IST by `bench/sandbox_daynight.py` (read-only). The 25 Sep evening run: the rotation 25 Sep 20:07–23:48 IST (D:\GitHub\GP\data\rotation); the 26 Sep morning run: 26 Sep 06:51–07:58 IST (D:\GitHub\GP\data\rotation-day). The times are our clock. The sandbox replays fixed recorded clips: each camera's picture carries its own recording date and time, from one time of day (one camera always shows the same June 2026 evening, whatever our clock says), and the footage repeats (identical readings of the same plates recurred between runs hours apart; bench/results/sandbox_loop.md). So the two runs replayed the same footage at different points of each loop: they are two samples of the same clips, not day against night, and what a camera shows (traffic, light) depends on its clip and where the loop is. A sighting is one stored plate (a vehicle's pass, voted across its reads), counted only inside that camera's analysis windows. Whether it is right: the tables at the end (blind check on the plate review page, `sandbox_review.md`). CAM05's sightings are mostly a hoarding's phone number (filtered since 21:12 on 25 Sep).

Frames analysed are the frames the object detector ran on in those windows: they show how much of a window the camera actually streamed (an outage leaves minutes but no frames), so plates per 1,000 frames is the fairer comparison.

| Camera | Evening: minutes | Evening: frames | Evening: plates | Evening: per 1,000 frames | Morning: minutes | Morning: frames | Morning: plates | Morning: per 1,000 frames |
|---|---|---|---|---|---|---|---|---|
| CAM03 | 24 | 2,091 | 0 | 0.0 | 15 | 1,240 | 0 | 0.0 |
| CAM06 | 24 | 2,049 | 69 | 33.7 | 30 | 2,027 | 23 | 11.3 |
| CAM07 | 24 | 1,022 | 6 | 5.9 | 30 | 2,452 | 22 | 9.0 |
| CAM08 | 24 | 260 | 0 | 0.0 | 15 | 849 | 0 | 0.0 |
| CAM10 | 24 | 1,844 | 0 | 0.0 | 15 | 950 | 0 | 0.0 |
| CAM11 | 18 | 1,981 | 0 | 0.0 | 15 | 24 | 0 | 0.0 |
| CAM12 | 36 | 3,940 | 1 | 0.3 | 30 | 1,925 | 0 | 0.0 |
| CAM14 | 36 | 3,289 | 0 | 0.0 | 30 | 1,483 | 0 | 0.0 |

Same cameras, totals: 25 Sep evening run 76 plates in 16,476 frames (210 camera-minutes); 26 Sep morning run 45 plates in 10,950 frames (181 camera-minutes). Both runs replayed the same looping footage, so a difference between them is where each camera's loop was, not the time of day.

**Were they right? Blind check by a person** on the Plate review page: the reviewer saw only the crop, typed the plate, and the server compared that reading with the stored read (`sandbox_review.md`):

| Run | Plates judged | Exact | Within one character | Wrong | Unreadable (left out) | Not a plate |
|---|---|---|---|---|---|---|
| 25 Sep evening run | 75 | 54 (72.0%) | 68 (90.7%) | 7 | 0 | 24 |
| 26 Sep morning run | 45 | 36 (80.0%) | 39 (86.7%) | 6 | 0 | 0 |

Earlier, not blind: each stored plate checked against its own crop by our AI coding assistant, with the stored read in view (`sandbox_eye.md`). It left unreadable crops out and came out more optimistic than the blind check above:

| Run | Plates judged | Exact | Within one character | Wrong | Unreadable (left out) | Not a plate |
|---|---|---|---|---|---|---|
| 25 Sep evening run | 66 | 55 (83.3%) | 59 (89.4%) | 7 | 10 | 24 |
| 26 Sep morning run | 41 | 37 (90.2%) | 37 (90.2%) | 4 | 4 | 0 |
