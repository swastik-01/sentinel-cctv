# Sentinel — &lt;TEAM NAME&gt;

<p class="lb-head"><span class="gu">સેન્ટિનલ — ગુજરાત પોલીસ માટે</span> · Gujarat Police Innovation Challenge 2026 · Grand finale, i-Hub Gandhinagar, 12–13 October 2026</p>

**What Sentinel is.** One registry, one map and one viewer for Gujarat's government cameras, with plate reading where a camera's view allows it and vehicle and person counts everywhere else.
It is Model 2 (unified viewing and selective analytics) on the mandatory Model 1 foundation (registry and GIS): it connects to cameras, recorders and VMS re-streams directly, installs nothing on a department's side and replaces nothing.
Video stays with the departments; only metadata (plate reads, counts, alerts) crosses the network, and every search and operator action is audited. No facial recognition, by design.

## The live test, step by step

| Step | What the judges see | Where in Sentinel |
|---|---|---|
| **Onboard** | A government camera onboarded live from its stream address: probe → relay → register, about 2 s; the rest as a batch | Registry → *Add camera by stream URL*; `scripts/onboard_urls.py` |
| **View** | Every camera on one map and one video wall, H.264 and H.265 alike; Health grades each camera's plate-reading quality and says what would improve it | Map · Video wall · Health & Reports |
| **Read** | Plate reads with vehicle type and colour; vehicle and person counts per camera per minute, on every camera at once | Overview · Health & Reports |
| **Alert** | A watchlist entry raises a live alert with its evidence crop about a second after the first read; near misses labelled; a read below confidence 0.9 says "check the crop" | Watchlist · Alerts |
| **Trace** | The registration given on the spot: a 24-hour look-back with one retrospective alert, then its journey as stops and legs, near misses marked, implausible legs flagged | Vehicle search → journey view |
| **Report** | Detected plates with timestamps as PDF and CSV (a SHA-256 per crop); the session's audit trail | `scripts/detection_report.py` · Audit |

## Four numbers, with their conditions

| Number | Condition |
|---|---|
| **30 of 30** government cameras onboarded, 1.0–2.2 s each | The organisers' sandbox, 25 Sep 2026, by RTSP address; H.264 and H.265, 960×576 to 2560×1440; all 30 viewed and counted, 4 at a time in rotation on one laptop (`bench/results/sandbox.md`) |
| **90 of 120** real Gujarat plates stored exactly right (75.0%); 107 within one character | Blind check by one team member on the Plate review page, 26 Sep, on the 2 of 30 views where plates are readable (CAM06, CAM07). Precision on stored reads only: capture on real plates is unmeasured. At Sentinel's confidence ≥ 0.9, 69 of 81 exact (`sandbox_review.md`). On stock footage with synthetic plates: 96.8% exact, 91.2% capture (`anpr_eval_current.md`) |
| **1.06 s** median from the first read of a vehicle to its alert (p95 1.94 s) | 31 alerts, 4 cameras, worker and API on one laptop and one clock, 24 Sep; excludes camera transport and the browser (`latency.md`) |
| **40 streams** counted at once on one laptop at 2.46 CPU cores, GPU 13% busy | Counts-only worker from keyframes, 0.78 frame/s per stream, 7 Oct; no plate worker running at the same time; 50 streams saturate; count accuracy unmeasured (`counts_capacity.md`) |

## Architecture

![Department estates untouched; district edges relay and analyse; only metadata reaches the state core.](diagrams/d1-architecture.svg)

Sized for 80,000 cameras by a capacity model (`bench/capacity.py`, Plan for Scale): 248 edge GPU nodes, about 2.7 Mbps of metadata statewide against 320 Gbps to carry every stream centrally, ₹100.7 crore over five years (₹210 per camera per month).
Tier shares, streams per node and unit prices are assumptions, labelled as such; the pilot measures them. The core was run at statewide size on one laptop: 706 sightings a second matched against 100,000 watchlist entries, a floor, not a sizing (`core_scale.md`).

## Said plainly

- **VAHAN and eGujCop are mock adapters** over fixture files behind one adapter contract; SARTHI, AFIS and NAFIS are declared, awaiting access.
- **Plates are read on 2 of the 30 sandbox views.** The other 28 are overview or red-light views where plates are too small; they are counted, and the Health page says what would make them readable (zoom, shutter, infrared, re-aim). The grade describes the camera; it does not predict whether a given read is right.
- **People are counted, never identified.** An intrusion alert holds the zone, the count and the dwell, never a box, image or track.
- **Since the submission (26 Sep → 10 Oct):** the counts-only worker and the two-laptop set-up were built and measured; the "check the crop" confidence marking passed its pre-registered gate on 8 Oct and is on; the OCR fine-tune was non-inferior on real plates and not adopted; the YOLOX detectors were not trained (the pilot's plan). Every accuracy, capture and latency figure above still describes the build that runs.

## Contacts

&lt;TEAM NAME&gt; · &lt;name, role, phone, email&gt; · &lt;name, role, phone, email&gt; · Documents: HLD, Plan for Scale, privacy note, demo videos, `bench/results/` (every figure's conditions)
