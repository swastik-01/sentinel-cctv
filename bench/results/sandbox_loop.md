# Does the sandbox footage repeat?

Generated 2026-09-26 19:18 IST by `bench/sandbox_loop.py` (read-only; counts only). Sightings on CAM06, CAM07 stored from 25 Sep 20:00 IST; analysis windows from the rotation logs (data/rotation, data/rotation-day, data/rotation-capture, data/rotation-all; a window still running has no end row yet and is left out). A repeat is the same stored reading on the same camera at least 3 minutes after the last one. Misreads differ from pass to pass, so only repeats read identically both times are counted.

| Camera | Windows | From window | To window | Gaps this pair allows (min) | Repeats | Gaps seen (min) |
|---|---:|---|---|---|---:|---|
| CAM06 | 7 | 25 Sep 21:11–21:24 | 25 Sep 22:48–23:00 | 84 to 108 | 8 | 96, 96, 96, 96, 96, 96, 96, 96 |
| CAM06 | 7 | 25 Sep 21:11–21:24 | 26 Sep 14:58–15:35 | 1054 to 1103 | 1 | 1093 |
| CAM06 | 7 | 25 Sep 21:11–21:24 | 26 Sep 15:51–18:07 | 1108 to 1255 | 5 | 1241, 1241, 1241, 1241, 1241 |
| CAM06 | 7 | 25 Sep 21:11–21:24 | outside the logs | n/a | 1 | 1009 |
| CAM06 | 7 | 25 Sep 22:48–23:00 | 26 Sep 07:06–07:21 | 487 to 514 | 5 | 492, 492, 492, 495, 495 |
| CAM06 | 7 | 25 Sep 22:48–23:00 | 26 Sep 07:43–07:58 | 523 to 550 | 3 | 536, 536, 536 |
| CAM06 | 7 | 25 Sep 22:48–23:00 | 26 Sep 14:58–15:35 | 958 to 1007 | 1 | 997 |
| CAM06 | 7 | 25 Sep 22:48–23:00 | 26 Sep 15:51–18:07 | 1012 to 1159 | 13 | 1036, 1081, 1116, 1116, 1116, 1116, 1116, 1116, 1146, 1146, 1146, 1146, 1146 |
| CAM06 | 7 | 25 Sep 22:48–23:00 | outside the logs | n/a | 5 | 880, 880, 880, 885, 885 |
| CAM06 | 7 | 26 Sep 07:06–07:21 | 26 Sep 07:43–07:58 | 21 to 51 | 2 | 46, 46 |
| CAM06 | 7 | 26 Sep 07:06–07:21 | outside the logs | n/a | 6 | 387, 387, 387, 387, 387, 422 |
| CAM06 | 7 | 26 Sep 07:43–07:58 | 26 Sep 15:51–18:07 | 473 to 624 | 4 | 580, 609, 609, 609 |
| CAM06 | 7 | 26 Sep 07:43–07:58 | outside the logs | n/a | 3 | 341, 341, 341 |
| CAM06 | 7 | 26 Sep 14:58–15:35 | 26 Sep 14:58–15:35 | 0 to 37 | 1 | 5 |
| CAM06 | 7 | 26 Sep 14:58–15:35 | 26 Sep 15:51–18:07 | 16 to 189 | 5 | 24, 82, 119, 119, 148 |
| CAM06 | 7 | 26 Sep 15:51–18:07 | 26 Sep 15:51–18:07 | 0 to 135 | 19 | 14, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 32, 33, 33, 35, 38, 64, 76 |
| CAM06 | 7 | outside the logs | 26 Sep 14:58–15:35 | n/a | 4 | 81, 82, 86, 112 |
| CAM06 | 7 | outside the logs | 26 Sep 15:51–18:07 | n/a | 9 | 122, 143, 148, 157, 157, 157, 157, 171, 260 |
| CAM06 | 7 | outside the logs | outside the logs | n/a | 14 | 3, 3, 8, 8, 8, 8, 8, 12, 12, 21, 21, 22, 22, 24 |
| CAM07 | 6 | 25 Sep 23:24–23:36 | 26 Sep 07:43–07:58 | 487 to 514 | 1 | 493 |
| CAM07 | 6 | 25 Sep 23:24–23:36 | 26 Sep 15:51–18:07 | 975 to 1123 | 2 | 1072, 1102 |
| CAM07 | 6 | 26 Sep 07:43–07:58 | outside the logs | n/a | 2 | 341, 341 |
| CAM07 | 6 | 26 Sep 15:51–18:07 | 26 Sep 15:51–18:07 | 0 to 135 | 6 | 30, 30, 30, 30, 30, 30 |
| CAM07 | 6 | outside the logs | 26 Sep 15:51–18:07 | n/a | 2 | 168, 168 |
| CAM07 | 6 | outside the logs | outside the logs | n/a | 3 | 34, 34, 35 |

Reading it: identical readings of the same plate recurring between windows hours apart show that the footage repeats. The gap itself is bounded by the window pair; a loop length is only identifiable where gaps cluster much more tightly than the pair allows, or where one continuous window is longer than the loop.

## The fresh sightings and the first blind set

Sightings on CAM06, CAM07 stored from 26 Sep 07:55:28 IST (sandbox-fresh-v1's window, to the time above): 188, with 119 distinct readings. 90 of them (48%) repeat exactly a reading stored in 25 Sep 21:00–26 Sep 07:55:28 IST, the window sandbox-blind-v1 was drawn from. That is a lower bound on re-read vehicles, since a misread differs from pass to pass: the fresh set re-reads the same looping footage and is not an independent sample of vehicles.
