Sentinel - Gujarat Police Innovation Challenge 2026
What these files show

Sentinel is working software. Every screen, video and report here comes from the real
platform (API, database, analytics worker) recorded live; nothing in the interface is mocked.
What differs is the camera feeds. The own-feed files ("1 - ...": screenshots, the first demo
video, the sample registry and the own-feed detection report) use Sentinel's feed simulator:

  - 12 synthetic cameras (drawn vehicles with synthetic Gujarat number plates)
  - 2 cameras replaying stock traffic footage (Pexels, free to use), AMD-TRAF-001 and
    AMD-TRAF-002, in which every number plate was replaced by a synthetic registration.
    The footage was filmed on a Mumbai road (its road signs are visible); the Ahmedabad
    names and map positions given to these cameras are simulated.
  - 1 camera onboarded by stream URL during the demo (GNR-MUNI-101)

Camera names, locations and vendors are illustrative. None of these is a government camera.

The exception is every file named "2 - Government feed ...": those come from the organisers'
sandbox camera grid, 30 government cameras replaying recorded footage as live streams, which
Sentinel onboarded and analysed on 25-26 Sep 2026. The sandbox's camera list gives only an id
and a name per camera; the departments and map positions Sentinel shows for them are our reading
of the names and pictures, approximate, and 6 of the 30 could not be placed at all.

FILES (as named in the shared folders)

  Sentinel-Solution.pdf (.pptx)    Solution presentation
  Sentinel-HLD.pdf                 High-level design (technical proposal), version 1.9
  Sentinel-Workflow-Diagrams.pdf   One captioned diagram per page
  Sentinel-Plan-for-Scale.pdf      Sizing, network, storage, DR, rollout and cost, 80,000 cameras
  Sentinel-Privacy-DPDP.pdf        Privacy position under the DPDP Act, 2023
  1 - Own feed demo.mp4            2:08 recording of the live control room on the simulator,
                                   captured 23 Sep 2026. Chapters: 1 - Own feed demo - chapters.txt
  1 - Own feed detection report.pdf
                                   Own-feed detection report: 9 minutes, 24 Sep 2026
                                   01:30-01:39 IST, 4 cameras, the same worker run as the
                                   accuracy figures below. Front page: one row per distinct
                                   plate (first and last seen, cameras in time order, reads,
                                   vehicle type and colour, watchlist status, best crop); plates
                                   one character apart are grouped as "possible same vehicle",
                                   never merged. Then a per-camera table, vehicle/person counts,
                                   the intrusion alerts, and an appendix of every read with its
                                   crop. 10 watchlist alerts (mock VAHAN and eGujCop records and
                                   one manual entry) and 4 intrusion alerts fall in the window.
  1 - Own feed detection report - plate reads.csv       every plate read, with frame time and camera
  1 - Own feed detection report - vehicles.csv          one row per distinct plate
  1 - Own feed detection report - counts.csv            vehicle and person counts per camera
  1 - Own feed detection report - intrusion alerts.csv  zone, what was inside and how many, dwell
  2 - Government feed demo.mp4     recording of the live control room on the organisers' sandbox
                                   cameras: registry, map, video wall, counts, intrusion alerts, a
                                   plate read on a sandbox camera added to the watchlist (the
                                   retrospective alert) and its history, and the report.
                                   It covers the evening run of 25 Sep (20:07-23:48 IST).
                                   Chapters: 2 - Government feed demo - chapters.txt
  2 - Government feed detection report.pdf (+ four CSVs, named as for the own feed)
                                   All 30 sandbox cameras, analysed 4 at a time in rotation;
                                   plates with timestamps and crops, vehicle and person counts
                                   per camera, intrusion alerts from two demo zones we drew
                                   (simulated restricted areas on CAM17 and CAM18). The evening
                                   run of 25 Sep, like the video, made before any review: of
                                   its 76 vehicle plates, 75 were checked blind afterwards and
                                   54 of those were exactly right (as described below).
  registry-cameras.csv             Model 1: sample camera-metadata dataset
  registry-gap-analysis.pdf        Model 1: sample gap-analysis report
  registry-api.md / .json          Model 1: registry API documentation
  sandbox-readiness.md             Sandbox checklist, run against the local simulator
  4 - Screenshots/                 overview, wall, alerts, search (journey view), health,
                                   registry, map, audit, zones (an intrusion zone drawn on the
                                   video wall), taken 24 Sep 2026; objects-AMD-TRAF-002 (what the
                                   vehicle/person detector finds in one frame), taken 23 Sep;
                                   scale-map (the map's clustered view over a synthetic
                                   80,000-camera test database used to load-test the core, 24 Sep:
                                   not real cameras; positions scattered around district centres,
                                   so a few clusters fall beyond the state border); 2 - Government
                                   feed - wall (four of the organisers' sandbox cameras on the
                                   video wall)

The video was captured before the features added on 24 Sep: working through a link outage,
intrusion zones and the journey view appear in the screenshots and the detection report, not in
the video.

The search screenshot flags one hop as an impossible speed. The simulator's clips loop, so the
same plate appears on cameras kilometres apart within seconds; the check exists to catch a
cloned plate or a misread, and here it is doing that job on simulated data. A stop without a
leg says why: first exact read, same camera, or possible misread.

MEASURED (one laptop, GTX 1650 Ti GPU, 24-26 Sep 2026)

  - The organisers' sandbox, 25 Sep: all 30 cameras onboarded by RTSP, probe 1.0-2.2 s
    each; vehicle and person counts on 30 cameras analysed in rotation.
  - Real Gujarat plates on the sandbox: 90 of 120 stored exactly right (75.0%),
    107 within one character (89.2%), 13 wrong; all but one on the 2 of 30
    sandbox views where plates are readable (CAM06 71 of 92, CAM07 19 of 27;
    the other on CAM12, 0 of 1).
    Checked blind by a team member on Sentinel's plate review page on 26 Sep:
    the page shows only the sighting's own crop, the reviewer types the plate,
    and the server compares it with the stored read. 144 of the 145 real
    sightings were checked; 24 were the hoarding described below (not a
    plate). The evening run of 25 Sep (all 30 cameras) gave 54 of 75; a
    morning run on 26 Sep (8 cameras) gave 36 of 45. The sandbox replays
    fixed recorded clips, each camera's from one time of day, in a loop, so
    both runs replayed the same footage: this is not a day and night
    comparison. By Sentinel's own
    confidence: at 0.9 or above 69 of 81 exact (85.2%) and 79 within one
    character; between 0.5 and 0.7 only 8 of 18. So high-confidence reads can
    pass and the rest go to a person, as commercial systems do.
    How far the check can be trusted: on our own cameras, where the true
    plates are known, the same blind check was right 222 times in 226
    (98.2%), and on the stock clip it found Sentinel right on 96.7% against
    96.8% from automated ground truth. One reviewer so far.
    An earlier check by our AI coding assistant, with the stored read in view
    (not blind), gave 92 of 107 (86.0%) after leaving 14 crops out as
    unreadable. It was optimistic: on the crops it judged readable, the blind
    reviewer found 80 exact where it found 92.
    Why the 30 misses missed: our AI assistant compared each missed crop
    with both readings. It judged 13 to be Sentinel's error (mostly a
    character dropped near the plate's end, or a digit or letter misread by
    the reading model), 13 the reviewer's (typing slips and look-alikes; 10 of those
    readings are not valid registrations as typed), 1 both and 3 unclear.
    That is an AI's judgement, not a person's, so the figure stays 90 of 120
    until a second team member checks the plates blind. 25 changes to how a
    crop is read, tried without training and scored by rules fixed in
    advance, did not beat the shipped reader on these plates.
    Precision only: plates that were never read cannot be counted on a live
    replay. Most sandbox cameras are wide overview and
    red-light views, several recorded at night, where plates were too small or blurred to read.
    Another 23 early reads were a hoarding's phone number taken for a plate; Sentinel
    now stores such fixed text once instead of again and again (1 in the
    hour and a half after the change).
  - Not a plate (added 26 Sep, after the government-feed video and report were
    made): a read is dropped when two or more of its letters had to be made from
    digits to fit a plate layout, which is how the hoarding's phone number became
    plate-like. Checked against gates written down before it was built, all
    passed: the hoarding caught in 23 of 23 saved crops and 24 of 24 stored
    sightings; no real sandbox plate lost (0 of 25 in a frozen set, 0 of the 92
    stored plates the AI check had labelled exact); on our own feed 4 of 5,307 correct reads
    lost and no vehicle; 1 of 1,723 held-out synthetic plates. Limits: the real
    non-plate evidence is one hoarding (3 texts, one camera) and the rule was
    chosen after seeing it; it stops numbers being taken for a plate, not signs
    made of letters. The government-feed report was made before the rule, so
    its 100 sightings still include the hoarding's 24 (CAM05); they are not
    counted in the 54 of 75.
  - Plate-reading quality by camera (added 26 Sep, after the government-feed
    video and report; not in the screenshots): the Health page grades every
    stored plate capture good, marginal or poor from its crop (size against
    published ANPR guidance, blur, light, contrast, layout, the reader's
    confidence) and gives each camera a tier (reads plates, marginal, counts
    only) with advice: zoom, shutter, infrared, re-aim, retrain the reader,
    or use it for counts. On the sandbox, CAM06 and CAM07 are marginal
    (median plates 104 and 106 pixels across) and the other 28 counts-only.
    Checked against the 120 blind-checked plates, the grade did not predict
    which reads were right (good 80.3%, marginal 65.9%, poor 80.0% exact);
    Sentinel's own confidence did. So it describes the camera, not a read.

  - Plate reading on the close stock-footage camera (AMD-TRAF-002), 10 minutes: 96.8% of
    stored plates exactly right (659/681), and 91.2% of the plates on screen for 1 s or more
    (62/68) read exactly at least once. On the wide camera (AMD-TRAF-001, not positioned for
    plate reading): 90.2% (174/193) and 21.7% (28/129). These plates are synthetic
    registrations in a clean font painted onto stock video, not real Gujarat plates.
  - First plate read to alert raised by the API: median 1.06 s, 95th percentile 1.94 s
    (31 alerts, 4 cameras, worker and API on the same machine and clock). Excludes the
    camera-to-worker network and the browser's display.
  - Link outage, one camera: API stopped for ~87 s; 21 sightings kept on disk and all
    replayed, and their alerts carried the original sighting time.
  - Watchlist matching: about 1 ms per plate read with 100,000 watchlist entries.
  - Hardware video decode (the laptop's integrated Intel GPU, not the NVIDIA card): 49% more
    analysed frames per stream than software decode, at 8 and at 12 streams.
  - The core at statewide size, on this one laptop: 80,000 registered cameras, 3 million
    sightings, 100,000 watchlist entries; 706 sightings a second ingested and matched,
    against a modelled statewide average of 556. A floor, not a sizing.
  - Intrusion zone: shown working on one stock clip and one zone. No false-alarm rate is
    claimed.
  - Tests: 34 end-to-end checks, 20 security checks and 245 unit tests, all passing
    (26 Sep).

NOT MEASURED OR NOT CONNECTED

  - How many plates on the sandbox cameras went unread (capture rate), and accuracy on the
    camera classes the sandbox does not include (dedicated ANPR cameras).
  - VAHAN and eGujCop watchlist data are mock adapters reading local fixture files, their
    fields modelled on the systems' published descriptions; SARTHI, AFIS and NAFIS are
    declared and awaiting access.
  - The 80,000-camera figures (edge nodes, bandwidth, cost) come from a capacity model whose
    assumptions are labelled in the Plan for Scale; they are estimates, not a deployment.
    The core has not been load-tested on server hardware at peak rates, or with several API
    instances and database replication.
