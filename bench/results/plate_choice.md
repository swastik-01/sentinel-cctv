# Plate choice per track: vote or best single read

Measured 24 Sep 2026, 01:16-01:27 IST, by `bench/plate_choice.py` on track logs (TRACK_LOG) from two 5-minute runs of the
worker on AMD-POL-001, AMD-AMC-001, AMD-TRAF-001, AMD-TRAF-002 (GTX 1650 Ti laptop, object detection on): one with
software decode (sw_decode_tracks), one with hardware decode (hw_decode_tracks). A track is up to ~3 reads of one
vehicle (the confirmation window); sightings are fewer, because repeats of a plate still in view are suppressed.

## sw_decode_tracks.jsonl (2389 tracks)

| Camera | Tracks | vote | best read | best if confident, else vote |
|---|---|---|---|---|
| AMD-AMC-001 | 971 | 62.4% (606/971) | 64.8% (629/971) | 65.0% (631/971) |
| AMD-POL-001 | 629 | 99.2% (624/629) | 98.4% (619/629) | 98.6% (620/629) |
| AMD-TRAF-001 | 149 | 94.6% (141/149) | 94.0% (140/149) | 92.6% (138/149) |
| AMD-TRAF-002 | 640 | 98.0% (627/640) | 98.1% (628/640) | 98.1% (628/640) |
| **all** | | **83.6%** (1998/2389) | **84.4%** (2016/2389) | **84.4%** (2017/2389) |

## hw_decode_tracks.jsonl (2502 tracks)

| Camera | Tracks | vote | best read | best if confident, else vote |
|---|---|---|---|---|
| AMD-AMC-001 | 1013 | 63.1% (639/1013) | 63.8% (646/1013) | 64.8% (656/1013) |
| AMD-POL-001 | 647 | 99.2% (642/647) | 99.1% (641/647) | 99.5% (644/647) |
| AMD-TRAF-001 | 151 | 96.0% (145/151) | 93.4% (141/151) | 92.7% (140/151) |
| AMD-TRAF-002 | 691 | 98.6% (681/691) | 98.8% (683/691) | 98.7% (682/691) |
| **all** | | **84.2%** (2107/2502) | **84.4%** (2111/2502) | **84.8%** (2122/2502) |

Exact = the track's reported plate is one of that camera's ground-truth plates (synthetic registrations
painted on stock footage, or drawn by the simulator). Same tracks for every rule; only the choice differs.
