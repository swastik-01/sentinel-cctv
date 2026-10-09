# Counts-only worker on the sandbox cameras

Generated 2026-10-07 21:22 IST by `bench/counts_sandbox.py`. The organisers' sandbox cameras, read through the local relay from one laptop on its home internet connection. Counts only.

## Keyframe intervals (probe of 2026-10-07T21:22+05:30, 240.0 s, all cameras at once)

Each camera is read in sessions that reconnect after a drop; gaps are timed within a session.

| Camera | Codec | Size | Keyframes (gaps) | Interval median (s) | Max (s) | Sessions / drops | Profile it gets |
|---|---|---|---:|---:|---:|---|---|
| CAM01 | h264 | 1920x1080 | 115 (109 gaps) | 2.0 | 3.9 | 6 / 5 | keyframes |
| CAM02 | h264 | 1920x1080 | 217 (212 gaps) | 0.95 | 2.7 | 5 / 4 | keyframes |
| CAM05 | h264 | 1920x1080 | 218 (213 gaps) | 0.97 | 3.2 | 5 / 4 | keyframes |
| CAM06 | hevc | 1920x1080 | 142 (136 gaps) | 1.37 | 6.2 | 6 / 5 | keyframes |
| CAM07 | h264 | 0x0 | 6 (4 gaps) | 15.12 | 49.3 | 6 / 5 | every frame |
| CAM12 | hevc | 1280x720 | 105 (99 gaps) | 2.11 | 4.8 | 6 / 5 | keyframes |
| CAM17 | hevc | 1920x1080 | 19 (15 gaps) | 10.42 | 13.4 | 6 / 5 | every frame |
| CAM18 | hevc | 1920x1080 | 21 (15 gaps) | 10.24 | 31.4 | 6 / 5 | every frame |

A camera whose keyframes are more than 4 s apart is switched to decoding every frame (still counted at most about once a second), or it would be counted every 10-40 s and its zones would miss short presences.

## Frames counted per camera (07 Oct 21:13–21:17 IST)

| Camera | Windows | Frames | Frames per minute | Profile |
|---|---:|---:|---:|---|
| CAM01 | 3 | 46 | 15 | keyframes |
| CAM02 | 3 | 66 | 22 | keyframes |
| CAM05 | 3 | 103 | 34 | keyframes |
| CAM06 | 3 | 75 | 25 | keyframes |
| CAM12 | 3 | 42 | 14 | keyframes |
| CAM17 | 3 | 56 | 19 | every-frame |
| CAM18 | 3 | 61 | 20 | every-frame |

The counts run (7 cameras: CAM01, CAM02, CAM05, CAM06, CAM12, CAM17, CAM18; CAM07 left out, as it was not delivering) lasted about 3 minutes, during which the sandbox dropped every session at once at least twice; the frames lost to those drops and reconnects are in these figures. At most 1 frame/s per camera is counted, with 20% tolerance for keyframe jitter. CAM17 and CAM18 were switched to every-frame decoding on the open session.
