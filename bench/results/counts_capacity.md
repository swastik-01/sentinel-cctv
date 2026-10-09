# Counts-only worker: cameras counted at once on one laptop

Generated 2026-10-07 21:28 IST by `bench/counts_capacity.py`. Machine: Intel64 Family 6 Model 165 Stepping 2, GenuineIntel, 6 logical CPUs, GPU NVIDIA GeForce GTX 1650 Ti; detector yolo11n on cuda (fp16=False, imgsz 640), batch up to 16, gathered for up to 0.5 s; at most 1 frame/s per stream, keyframes only. Streams: RTSP sessions through the local relay, cycling over 14 simulator cameras (AMD-AMC-001, AMD-AMC-002, AMD-GSRTC-001, AMD-HLTH-001, AMD-POL-001, AMD-TRAF-001, AMD-TRAF-002, GNR-GSRTC-001, GNR-HLTH-001, GNR-PNCHT-001, GNR-PNCHT-002, GNR-POL-001, GNR-POL-002, MHS-POL-001): H.264 and H.265, 704x576 to 1920x1080, 12-25 fps, keyframes every 1-2 s. 15 s to connect, then 45 s measured per row. The relay's own CPU is not included; no plate worker ran at the same time.

| Streams | Frames/s per stream (median, min) | Silent streams | CPU cores | GPU busy | Detector ms/frame | Mean batch | Reconnects/errors |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | 0.67, 0.4 | 0 | 0.47 | 11.0% | 24.1 | 4.3 | 0 |
| 20 | 0.82, 0.4 | 0 | 0.95 | 11.8% | 13.9 | 9.3 | 0 |
| 30 | 0.82, 0.4 | 0 | 1.56 | 12% | 12.8 | 11.7 | 0 |
| 40 | 0.78, 0.4 | 0 | 2.46 | 13.2% | 25.4 | 10.6 | 0 |
| 50 | 0.34, 0.3 | 0 | 3.21 | 12.6% | 58.3 | 12.7 | 0 |

A stream's rate is capped by its keyframe interval: these cameras send a keyframe every 1-2 s, so 0.5-1 frame/s per stream is the most this profile can count. Counts are per minute, so that is enough; a camera whose keyframes are further apart is counted less often.
