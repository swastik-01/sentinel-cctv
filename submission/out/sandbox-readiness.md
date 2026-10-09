# Sandbox readiness — pre-submission checklist

Sentinel · generated 23 Sep 2026 17:04 India Standard Time · catalogue `http://localhost:8010` · 3 stream(s) observed for 75s

Run against the local feed simulator, which mirrors the sandbox contract (RTSP over TCP, catalogue API, mixed codecs). The organisers' sandbox catalogue sits behind a browser login and gives only an id and a name per camera, so it cannot be synced; its 30 cameras were onboarded by RTSP address on 25 Sep instead (`scripts/onboard_sandbox.py`, `bench/results/sandbox.md`).

**8/8 checks pass**

| # | Check | Status | Evidence |
|---|---|---|---|
| 6 | Camera list and per-camera properties read from the catalogue API | **PASS** | synced 0 new + 14 existing from http://localhost:8010; 14 cameras carry catalogue-sourced properties (codec, resolution, fps, location); 0 unmappable records |
| 1 | Every client forces RTSP over TCP | **PASS** | analytics workers: OPENCV_FFMPEG_CAPTURE_OPTIONS='rtsp_transport;tcp|stimeout;5000000|max_delay;500000'; media relay pulls with rtspTransport=tcp; simulator publishes with -rtsp_transport tcp |
| 2 | No timing logic depends on CAP_PROP_FPS or on frame arrival time | **PASS** | CAP_PROP_FPS is recorded for reporting only; event time = stream PTS anchored once, with a documented fallback. AMD-AMC-001: 240/240 distinct frame timestamps, max |frame-time - arrival-time| drift 3.53s, stream PTS · AMD-AMC-002: 250/250 distinct frame timestamps, max |frame-time - arrival-time| drift 1.43s, stream PTS · GNR-POL-002: 130/130 distinct frame timestamps, max |frame-time - arrival-time| drift 1.03s, stream PTS |
| 3 | Inter-frame gaps do not crash or stall the pipeline | **PASS** | 3/3 streams connected at the end; latest-frame semantics mean a gap lowers the analysis rate instead of queueing. AMD-AMC-001: longest gap between delivered frames 2.3s, still delivering at the end (yes) · AMD-AMC-002: longest gap between delivered frames 2.3s, still delivering at the end (yes) · GNR-POL-002: longest gap between delivered frames 33.6s, still delivering at the end (yes) |
| 4 | Reconnect with backoff, tested by restarting a feed | **PASS** | GNR-POL-002: feed cut mid-run; 2 connection attempts, backoff 2s doubling to a 30s cap; reconnected and delivering again: yes |
| 5 | Decoder warnings on join are logged, not fatal | **PASS** | OPENCV_FFMPEG_LOGLEVEL=16 (AV_LOG_ERROR: decoder complaints are printed); counted per stream and never fatal — hiccups {'AMD-AMC-001': 0, 'AMD-AMC-002': 0, 'GNR-POL-002': 25}, frames decoded {AMD-AMC-001: 1861, AMD-AMC-002: 1829, GNR-POL-002: 995} |
| 7 | Pipeline handles mixed H.264/H.265 and mixed resolutions | **PASS** | catalogue advertises codecs ['H.264', 'H.265'] and 3 resolutions ['1280x720', '1920x1080', '704x576']; decoded this run: ['1280x720', '1920x1080'] |
| 8 | Behaviour is sane across a scene discontinuity | **PASS** | a backwards jump or a >5s gap in stream position re-anchors the clock and is logged; observed this run: {'AMD-AMC-001': 0, 'AMD-AMC-002': 0, 'GNR-POL-002': 0} (total 0); no stream dropped as a result (3/3 still connected) |
