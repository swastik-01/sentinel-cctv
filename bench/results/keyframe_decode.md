# Decoding every frame against keyframes only

Generated 2026-10-08 10:04 IST by `bench/keyframe_decode.py` on Intel64 Family 6 Model 165 Stepping 2, GenuineIntel, 6 logical CPUs; PyAV 19.0.1, software decode, RTSP over TCP through the local relay; 14 simulator streams at once (AMD-AMC-001, AMD-AMC-002, AMD-GSRTC-001, AMD-HLTH-001, AMD-POL-001, AMD-TRAF-001, AMD-TRAF-002, GNR-GSRTC-001, GNR-HLTH-001, GNR-PNCHT-001, GNR-PNCHT-002, GNR-POL-001, GNR-POL-002, MHS-POL-001), 25 s each mode. Only keyframes are converted to an image in both modes, so the difference is the decoder's work on the other frames. CPU is this process's user+system time over the wall time; the relay's own CPU is not included.

| Mode | Streams | CPU cores used | Keyframes per stream per second (median) |
|---|---:|---:|---:|
| every frame | 14 | 2.57 | 0.96 |
| keyframes only | 14 | 0.47 | 0.91 |

| Stream | Codec | Size | Decoded/s (every frame) | Keyframes/s |
|---|---|---|---:|---:|
| AMD-AMC-001 | h264 | 1920x1080 | 28.5 | 0.95 |
| AMD-AMC-002 | hevc | 1920x1080 | 28.5 | 0.91 |
| AMD-GSRTC-001 | hevc | 1280x720 | 16.9 | 0.55 |
| AMD-HLTH-001 | h264 | 704x576 | 13.1 | 0.48 |
| AMD-POL-001 | h264 | 1280x720 | 28.5 | 0.94 |
| AMD-TRAF-001 | h264 | 1920x1080 | 28.4 | 0.94 |
| AMD-TRAF-002 | hevc | 1920x1080 | 28.4 | 0.91 |
| GNR-GSRTC-001 | h264 | 1280x720 | 17.0 | 0.59 |
| GNR-HLTH-001 | h264 | 704x576 | 13.2 | 0.47 |
| GNR-PNCHT-001 | hevc | 1280x720 | 17.0 | 0.56 |
| GNR-PNCHT-002 | h264 | 1280x720 | 16.9 | 0.58 |
| GNR-POL-001 | h264 | 1920x1080 | 28.5 | 0.95 |
| GNR-POL-002 | hevc | 1280x720 | 28.7 | 0.92 |
| MHS-POL-001 | h264 | 1920x1080 | 28.4 | 0.95 |

The keyframe rate is set by each clip's encoder (one every 1-2 s here), so a counts-only analysis gets the same frames either way; what changes is the cost of getting them.
