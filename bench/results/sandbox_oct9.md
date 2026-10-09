# The organisers' sandbox, reconnected (9 Oct 2026)

Session 2026-10-09 08:00–08:40 (UTC+0530), by `bench/sandbox_oct9.py` from the audit log and the stored sightings and counts of a native test stack on one laptop (GTX 1650; no Docker), the API on a real broker. Cameras came from the camera grid's catalogue (`/cameras.json`: an id and a name each) and were onboarded by `scripts/onboard_sandbox.py` through Sentinel's own URL onboarding (probe, relay, register), one at a time, 10 s apart, relayed on demand over RTSP/TCP. Consume only; nothing downloaded; no crop used to train or tune. Counts, times and codecs only.

## Onboarding

- **30 of 30** sandbox cameras onboarded; 1 attempt(s) failed first (CAM19; a single retry later succeeded where it now shows onboarded).
- Probe time (stream ready through the relay): median 1.0 s, range 0.9–2.9 s.
- Codecs: H.264 24, H.265 6; resolutions: 1280x720 5, 1280x960 4, 1920x1080 19, 2560x1440 1, 960x576 1.

## Video wall (12:14–12:27)

`submission/build/wall_probe.mjs` as an operator's browser (no media permission), 4 cameras at a time on a 2x2 wall with a pause between batches, each tile watched for 40 s: **14 of 30** showed a picture in that time. The transport is the tile's badge: *webrtc* is the camera's own stream (for an H.265 camera, the registered preview); *preview* is the relay's transcoded profile, which the player tries when the camera's own stream connects but shows nothing in 15 s; *hls* is the last resort. The last three columns are the relay's own log for each camera during the probe: lost RTP packets (gaps in what the organisers' server sent; the relay reads over TCP), its connection to their server timing out, and the preview transcoder failing to start within its 20 s.

| Camera | Codec | Resolution | Wall | RTP packets lost | Source timeouts | Preview start timeouts |
|---|---|---|---|---|---|---|
| CAM01 | H.264 | 1920x1080 | picture after 1.6 s (webrtc, 1920 px wide) | 0 | 1 | 0 |
| CAM02 | H.264 | 1920x1080 | picture after 1.6 s (webrtc, 1920 px wide) | 408 | 0 | 0 |
| CAM03 | H.264 | 1280x720 | picture after 2.6 s (webrtc, 1280 px wide) | 297 | 1 | 0 |
| CAM04 | H.264 | 1920x1080 | picture after 4.1 s (webrtc, 1920 px wide) | 7018 | 0 | 0 |
| CAM05 | H.264 | 1920x1080 | picture after 1.0 s (webrtc, 1920 px wide) | 1508 | 0 | 0 |
| CAM06 | H.265 | 1920x1080 | picture after 36.7 s (hls, 640 px wide) | 11247 | 0 | 0 |
| CAM07 | H.264 | 1920x1080 | no picture in 40 s | 25469 | 0 | 1 |
| CAM08 | H.264 | 1920x1080 | no picture in 40 s | 39206 | 1 | 1 |
| CAM09 | H.264 | 1920x1080 | picture after 31.7 s (preview, 640 px wide) | 5191 | 1 | 0 |
| CAM10 | H.264 | 1920x1080 | no picture in 40 s | 13166 | 1 | 1 |
| CAM11 | H.264 | 1920x1080 | picture after 30.7 s (preview, 640 px wide) | 23898 | 0 | 0 |
| CAM12 | H.265 | 1280x720 | picture after 9.2 s (webrtc, 640 px wide) | 5753 | 0 | 0 |
| CAM13 | H.264 | 1920x1080 | picture after 1.0 s (webrtc, 1920 px wide) | 3136 | 0 | 0 |
| CAM14 | H.264 | 1920x1080 | picture after 1.0 s (webrtc, 1920 px wide) | 170 | 1 | 0 |
| CAM15 | H.264 | 1920x1080 | no picture in 40 s | 0 | 2 | 1 |
| CAM16 | H.264 | 1920x1080 | no picture in 40 s | 394 | 2 | 0 |
| CAM17 | H.265 | 1920x1080 | no picture in 40 s | 0 | 1 | 1 |
| CAM18 | H.265 | 1920x1080 | picture after 27.6 s (hls, 640 px wide) | 2352 | 1 | 0 |
| CAM19 | H.264 | 1280x720 | picture after 12.2 s (webrtc, 1280 px wide) | 26614 | 0 | 0 |
| CAM20 | H.264 | 1280x720 | picture after 14.8 s (webrtc, 1280 px wide) | 0 | 1 | 0 |
| CAM21 | H.264 | 1920x1080 | no picture in 40 s | 3646 | 0 | 1 |
| CAM22 | H.265 | 1920x1080 | no picture in 40 s | 0 | 0 | 0 |
| CAM23 | H.264 | 1280x720 | no picture in 40 s | 2707 | 1 | 1 |
| CAM24 | H.264 | 960x576 | no picture in 40 s | 0 | 0 | 1 |
| CAM25 | H.264 | 1280x960 | no picture in 40 s | 9259 | 1 | 1 |
| CAM26 | H.265 | 2560x1440 | no picture in 40 s | 0 | 1 | 0 |
| CAM27 | H.264 | 1280x960 | no picture in 40 s | 736 | 1 | 1 |
| CAM28 | H.264 | 1280x960 | no picture in 40 s | 2962 | 1 | 1 |
| CAM29 | H.264 | 1280x960 | no picture in 40 s | 4701 | 0 | 1 |
| CAM30 | H.264 | 1920x1080 | no picture in 40 s | 201 | 1 | 1 |

Of the 16 without a picture, 15 had source trouble logged by the relay in the probe window. One probe at one time of day: the sandbox's feeds change through the day, so this is a snapshot of them, not of every session.

## Workers

From 08:15: the plate worker on the cameras below with sightings, the counts-only worker (keyframes) on the cameras with count rows. Sightings are counted, never read here; they wait in the Plate review page's blind queue for a person to read.

| Camera | Sightings stored | of which at confidence ≥ 0.9 | Count rows | Frames analysed per minute, from the count rows |
|---|---|---|---|---|
| CAM01 | — | — | 15 | 55 |
| CAM02 | — | — | 15 | 56 |
| CAM03 | — | — | 15 | 45 |
| CAM04 | — | — | 15 | 53 |
| CAM05 | — | — | 15 | 44 |
| CAM06 | 24 | 16 | 15 | 180 |
| CAM07 | 8 | 4 | 15 | 166 |

Alerts on sandbox cameras in the session: 1, of which 1 retrospective (a plate already read, put on the watchlist afterwards, raises one at once), 1 with the sighting's evidence crop.

One session, one laptop, the organisers' looping replay: a check that the integration works on their feeds, not a measure of accuracy (no sighting here has been read by a person yet).
