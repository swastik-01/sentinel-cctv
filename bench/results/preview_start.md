# Preview transcoder start on lossy sources: shipped command against a candidate

Measured 2026-10-09 12:30–12:40 (UTC+0530) by `bench/preview_start.py` on cameras CAM07, CAM08, CAM10 of the organisers' sandbox, read through Sentinel's relay on one laptop; 3 rounds, the two commands in alternating order within each camera, an attempt's window 30 s (the relay allows 20 s), 20 s between attempts.

Shipped: the preview command in `infra/mediamtx.yml`. Candidate: the same, with `-analyzeduration 20000000 -probesize 20000000 -fflags +discardcorrupt -err_detect ignore_err` before the input.

| Arm | Started within 20 s (the relay's limit) | Started within the window |
|---|---|---|
| shipped | 6 of 9, median 12.2 s | 6 of 9, median 12.2 s |
| candidate | 8 of 9, median 7.2 s | 8 of 9, median 7.2 s |

| Round | Camera | Arm | Seconds to a published preview |
|---|---|---|---|
| 1 | CAM07 | shipped | 4.5 |
| 1 | CAM07 | candidate | 2.1 |
| 1 | CAM08 | shipped | 13.9 |
| 1 | CAM08 | candidate | 3.0 |
| 1 | CAM10 | shipped | no start |
| 1 | CAM10 | candidate | 10.4 |
| 2 | CAM07 | candidate | 4.9 |
| 2 | CAM07 | shipped | 12.2 |
| 2 | CAM08 | candidate | 9.5 |
| 2 | CAM08 | shipped | 12.5 |
| 2 | CAM10 | candidate | no start |
| 2 | CAM10 | shipped | 5.3 |
| 3 | CAM07 | shipped | 12.3 |
| 3 | CAM07 | candidate | 8.1 |
| 3 | CAM08 | shipped | no start |
| 3 | CAM08 | candidate | 12.0 |
| 3 | CAM10 | shipped | no start |
| 3 | CAM10 | candidate | 6.3 |

The sandbox's feeds change through the day: the arms are compared within one session only.
