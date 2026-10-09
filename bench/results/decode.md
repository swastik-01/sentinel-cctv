# Video decode: software vs hardware (D3D11)

Measured 2026-09-23 19:22 UTC on DESKTOP-R2I8CQL (NVIDIA GeForce GTX 1650 Ti, Intel64 Family 6 Model 165 Stepping 2, GenuineIntel),
Windows-11-10.0.26200-SP0, by `sentinel-bench` with `HW_DECODE=off` and `HW_DECODE=auto`, 25 s per case,
two rounds in alternating order (software first, then hardware first) to spread thermal throttling across both.
Pipeline as in production: DETECTOR=both, DETECT_FPS=5.0, plate detector on cuda, OCR on CPU. Streams are the simulator's cameras (H.264 and H.265, 720p and 1080p), reused when more are asked for than exist.

| Streams | Analysed fps per stream, software | Hardware | Change | System CPU, software | Hardware | Per round (sw / hw) |
|---|---|---|---|---|---|---|
| 4 | 4.58 | 4.52 | -1% | 73% | 70% | 4.51, 4.66 / 4.54, 4.5 |
| 8 | 1.93 | 2.88 | +49% | 94% | 80% | 1.9, 1.96 / 2.83, 2.92 |
| 12 | 0.91 | 1.34 | +49% | 98% | 94% | 0.85, 0.96 / 1.43, 1.26 |

Analysed fps per stream is what reaches the plate detector (target 5). System CPU includes everything running on the
laptop (the API, database and simulator containers too). One laptop, one day: a direction and a size, not a node figure;
the Plan for Scale's streams-per-node for a server GPU stays an assumption until measured on that hardware.

Which decoder: on this laptop (Intel UHD integrated GPU + GTX 1650 Ti), OpenCV's D3D11 path opens the default adapter,
the Intel iGPU. Windows GPU-engine counters showed the VideoDecode load on that adapter and the NVIDIA decoder at 0%
(24 Sep). So this measures offloading decode from the CPU, not NVDEC; a server node's NVDEC is design until measured.
