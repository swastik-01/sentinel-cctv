# Privacy, proportionality and the DPDP Act — design position

Sentinel processes video of the public on behalf of the state. That is lawful for law enforcement
purposes, and it is also exactly the kind of processing where design choices, not policy documents,
determine whether the system is defensible. This note records the choices.

## 1. No face recognition — by design, not by omission

The platform does **not** implement facial recognition, and the flag `ENABLE_FACE_RECOGNITION`
exists only so the choice is visible in configuration. Detecting that a person is present is not
recognising who they are: Sentinel does the first (a box that becomes a number and is then
discarded, section 2.1, or a note that someone is inside an area an operator has marked, section
2.2) and does not do the second. Reasons:

- **Proportionality.** Vehicle-based tracking answers the operational questions in the problem
  statement (stolen vehicles, BOLO, movement history) without identifying anyone. Where the platform
  detects people it only *counts* them, or records that someone is inside a drawn zone. No face is
  matched, no body or gait signature is stored, no person is tracked within or across cameras, and
  no image of a person is retained.
- **Accuracy is uneven across demographics** in published evaluations, and a false match in a
  policing context has consequences a false plate read does not.
- **DPDP Act 2023** treats biometric identifiers as sensitive. Wide-area biometric matching of
  people who are not suspects is hard to justify under purpose limitation and data minimisation.

Wanted and missing persons are still supported: watchlist entries of those kinds match on an
associated vehicle registration, which is how such alerts are operationalised today.

## 2. Data minimisation

- Analytics workers store **metadata**, not footage: plate text, timestamp, camera, a small plate
  crop for evidence; for vehicle and person detection, a count per class per camera per minute; for
  an intrusion zone, the zone, how many and for how long. Video stays on the department's own
  recorder under its own retention. A plate crop is the only pixel data the platform keeps, because
  a registration number is the only thing an investigator needs to verify by eye.
- Plate crops are files on the analysing node's disk, named in the sighting. The API serves one
  only to a signed-in user who holds the search or alert permission (or the review permission, on the
  plate review page, 2.5), and only for a camera inside that user's department or district; a crop outside the user's scope answers "not found", because
  its existence is itself information. `scripts/security_checks.py` tests a missing token, a missing
  permission and a path outside the crop store. Full frames are referenced by URI only if the source
  system supports it, and are never copied into the platform by default.
- Sightings and count rows are partitioned by month, so retention is a partition drop, not a
  row-by-row delete. **In the proof of concept retention is manual:** no scheduled job drops
  partitions yet, dropping one would not delete the crop files its rows point to, deleting a camera
  removes its sighting rows (the database cascades) but leaves its crop files on disk until someone
  removes them, and alerts (plate and intrusion) sit in one table that is not partitioned. Dropping a
  month's partitions and that month's crops together, on the period the Home Department sets (section
  7), and removing a deleted camera's crops with it, are design.
- Two columns added to each sighting on 8 Oct, `reads` (how many reads stood behind the stored plate)
  and `agreement` (how far the vote agreed, 0–1), are a count and a share: no new personal data. The
  "check the crop" mark they support (HLD 7.5: a read below confidence 0.9, or a watchlist alert on a
  one-character match) is computed from the stored confidence when a sighting is read, not stored, and
  suppresses nothing.

### 2.1 Vehicle and person counting

**Purpose.** Control-room situational awareness: congestion at junctions, crowding at bus depots,
hospital entrances and event venues, and deciding where to send traffic or patrol staff. These are
questions about how many, never about who.

**What is stored.** One row per camera per minute: how many frames were analysed, and per class
(person, car, motorcycle, bus, truck, bicycle) the number of detections and the most seen in one
frame. No bounding box, no image, no track identity and no label linking a count to anyone. A person
detection exists in worker memory for one frame and is then a number. The smoke test checks that
no count row carries a box, track or label. The counts-only worker (HLD 5.4), which since 7 Oct counts
most cameras from their keyframes at about one frame a second, writes the same row plus a note of how
the camera was sampled (`profile`), and nothing else.

**What it is never used for.** Person detections do not feed the watchlist, plate alerts or any
search. There is no endpoint that lists individual detections, only aggregates. The one other use
of the same boxes is the intrusion zone (2.2), which asks only whether someone is inside an area.

**Low counts.** At a quiet gate, "1 person, 02:14" with a camera and a timestamp is closer to a
presence signal than a junction's count is. The mitigations are structural: counts are per minute,
not per frame; counting runs only on cameras where analytics is switched on in the registry (a
per-camera flag, the Registry's *Analyse* box, so a `private_shared` feed is not counted unless the
department chooses to); reading counts needs `reports.read`; and counts go when their monthly
partition is dropped (manual in the PoC, section 2).

**Vehicle type and colour** are written onto the plate sighting they describe, so they inherit that
sighting's retention, scoping and audit. Colour is a heuristic, left blank when unsure. Neither can
be verified from the retained evidence, because the kept crop is the plate, not the vehicle, and
the report says so.

### 2.2 Intrusion zones

**Purpose.** Areas that should be empty at certain hours: a depot yard at night, a perimeter, a
closed gate. The question is whether someone is there, never who.

**What triggers it.** A user who may edit the camera draws a polygon on its live picture (Video
wall → *zones*), chooses the classes that count (person by default; vehicle classes can be added),
a minimum dwell (3 s by default), optional armed hours in IST (outside them the zone is ignored) and
a severity. The worker tests the boxes the object detector already produces for the counts: a box
is inside when its ground point (the bottom centre, where a person stands) lies inside the polygon.
Presence for the dwell time, while armed, raises one event per occupancy, and the API turns it into
an alert at most once per zone per camera per 120 s. Identity is never an input.

**What is stored.** The zone lives in the camera's registry record (its tags), and every change is
audited (`camera.zones`, section 3). The event and its alert hold the zone, the classes and how many of each
were inside at most, the dwell, when the occupancy began and when the alert condition was met, and
the severity. No box, crop, frame or track of the person is stored or sent: the event leaves the
worker without them. Checked in the database on 24 Sep 2026: none of the 33 intrusion rows stored up
to then carried a box or a track id.

**Seeing who it is.** The alert card links to the camera's live view. The operator looks at the
live picture, as after a phone call; nothing about the person enters the platform. Live views are
not yet audited one by one (section 3).

**Where it runs.** Only on cameras that are analysed with object detection on; the worker reads the
zones when it starts. A zone over a public footpath, armed all day, would turn presence detection
into monitoring of passers-by. Zones belong on areas that are restricted at the hours they are armed.
That is a supervisory decision, and the audit trail records who made it.

**What was measured.** One demonstration zone on one clip: a kerb strip marked as a simulated
restricted area on `AMD-TRAF-001`, Pexels stock footage looping every 60 s. Over 15 minutes it
raised 14 events, one per loop, each with one or two people inside the zone, and 6 alerts after the
120 s cooldown. An offline replay of one loop gave 1 event; its saved frame shows a pedestrian inside the zone;
motorcycle riders on the carriageway beside it did not trigger it. That shows the mechanism end to
end. It is not a false-alarm rate.

### 2.3 Data held at the edge during an outage

When the link from an analytics node to the core is down, the node keeps analysing and holds what
it needs on its own disk, in three places under `data/spool/<worker id>/` (one folder per worker
process since 8 Oct, so a plate worker and a counts-only worker on one machine never replay each
other's files). Each holds less than the database does.

| Where | Holds | Lifetime |
|---|---|---|
| `edge-watchlist.json`, the node's copy of the watchlist | Active vehicle entries only: plate, kind (stolen, BOLO, …) and severity, plus the matching rule. No names, reasons, case references or sources | Overwritten every 60 s while the core answers; kept through an outage, so a restarted worker still has it. An entry that expires during an outage stays in the copy until the link returns |
| `local-alerts.jsonl`, hits recorded during an outage | Plate read, camera, sighting time, the watchlist plate it matched, its kind and severity, and whether the match was exact. Each hit is also a line in the worker's log, with the plate masked there (2.6) | No rotation in the PoC: the file grows until cleared by hand. Rotating it, and clearing entries once the replayed alerts are closed, is design |
| the folder's batch files, batches the core could not take | Sighting rows as they would have been sent (plate, times, confidences, vehicle type and colour, the plate's box, track id, crop path; the crop itself is already in the crop store), and count and intrusion rows | Bounded at 512 MB per worker (`SPOOL_MAX_MB`); past that, the oldest batches are dropped with a warning. Each file is deleted as soon as the core accepts it. A batch the core rejects as malformed (since 8 Oct also one whose event times carry no timezone or lie more than 14 days from now) moves to `rejected/` beside it and stays there until someone inspects and deletes it |

Local hits follow the core's matching rule (exact, or one character off) and its cooldown of one
per entry per camera per 120 s. The control-room alert is raised when the spooled sightings replay,
with the time the vehicle was actually seen. In the PoC these are plain files on the node's disk;
the production design encrypts the whole disk of every edge node (HLD 11.4).

### 2.4 Evaluation tooling, not product

These tools exist to measure the pipeline. None is part of the product, and none is for real
feeds without a decision about the data it writes.

- **`TRACK_LOG`** is a worker setting, off by default. When set, the worker appends every plate
  track it closes to a JSONL file: camera, time, every OCR read of the plate, the voted plate and the
  best single read. It was used on stock footage with synthetic plates to compare the character vote
  with the best single read (`bench/results/plate_choice.md`). The file holds plate reads outside the
  database's partitions, scoping and audit, so it must never be enabled on real feeds without a
  retention decision.
- **`bench/zone_check.py`** replays a clip file through the worker's detector and zone logic and
  saves the frame at each intrusion event with the zone and the triggering person's box drawn, so the
  event can be checked by eye. Those frames show people. It was run on the Pexels stock footage only,
  and it is not for government feeds, whose terms allow live streaming only.
- **`bench/sandbox_eye.py`** measured plate accuracy on the organisers' sandbox by comparing each stored
  sighting with its own evidence crop. Its contact sheets and labels hold real registrations, so they
  stay on the team's machine (`data/gov-sandbox/eye`, outside the repository); only totals are published.
  Real registrations appear in the government-feed report because the organisers ask for plates with
  timestamps. Still frames taken to choose which sandbox cameras to analyse were deleted after the review.
  With `score --from-db` it reads the verdicts people record on the plate review page (2.5) and, again,
  publishes totals only.
- **The frozen plate-reading test sets** (`bench/ocr_sets.py`, under `data/ocr-eval`, outside the
  repository) hold copies of stored sandbox evidence crops with the blind reviewer's readings, so the
  plate reader can be re-scored on the same real plates (`bench/ocr_ab.py`, `bench/blind_errors.py`).
  They are test-only: nothing is trained on them, and no change is adopted on their evidence alone
  (`bench/ocr_gates.md`). Only counts and rates are published; plate text stays on the team's machine.

### 2.5 Plate review

People check Sentinel's stored reads against their evidence crops on the control room's *Plate
review* page (HLD 7.8). It captures nothing new: it shows crops the platform already keeps.

- **Who sees the crops.** Administrators, supervisors and auditors (`reviews.read`, `reviews.write`);
  not operators or department nodal officers. Scoping applies as for every crop: a camera outside the
  reviewer's department or district is not offered. The queue is chosen by camera and time, never by
  plate (and, since 8 Oct, by band: a "Below 0.9, unchecked" filter puts the reads the control room marks
  "check the crop" first, HLD 7.5), and crops are served by sighting id, because a crop's file name
  carries the plate. In a blind
  check the page receives no plate text or confidence until the reviewer has answered.
  `scripts/security_checks.py` tests the refusals and the blind queue.
- **Audit.** Every review is written to the audit trail as `plate.review`, with the reviewer, the
  sighting id, the mode and the verdict; a reviewer's later change to their own reading as `plate.review.edit`, with the
  first and the new verdict; each listing of readings in Results (plate by plate) as `plate.review.list`. The plate
  text is left out, so the audit log does not become a second list of registrations.
- **Results, plate by plate.** Since 9 Oct, Results lists each review's reading beside Sentinel's read: a reviewer's
  own reviews, whose reads the page has already shown them, unless they ask for everyone's. Everyone's shows reads
  of crops they may not have checked, so those crops then leave their blind queue and a blind check of them is refused.
- **The labels are personal data.** What a reviewer types is a registration, tied to a camera and a
  time. The readings stay in the database (`plate_reviews`), behind the same access as sightings, and
  only totals leave it (`bench/sandbox_eye.py score --from-db`). A review keeps a copy of the stored
  read, so its result outlives the sighting: reviews need their own retention period, set with the
  sightings' (section 7). In the PoC they are kept.
- **Reuse.** Each review is also a labelled example that could later retrain the plate reader, but only
  through the adoption gates written in advance in `bench/ocr_gates.md`. No real crop has been used for
  training, and the organisers' sandbox footage is not trained on.

### 2.6 Logs

Log files leave the database's scoping, audit and retention, so since 8 Oct they carry no whole
registration where the platform writes one:

- The API's access log is off (`scripts/api.ps1` starts uvicorn with `--no-access-log`). It wrote every
  request line to a file under the user's temporary folder, including each plate searched and the token a
  browser then carried in a URL for the event WebSocket and evidence crops (HLD 11.4). Since 8 Oct no token
  travels in a URL: crops are fetched with the Authorization header, and the event WebSocket takes its token in its
  first message.
- The analytics worker's log masks each plate it stores to the state code and the last two characters
  (`GJ******34`), in the sighting line and the local-alert line alike, and since 8 Oct the warning that a
  read was muted as fixed text (the same text at the same spot again, HLD 7.1) masks the read and the stored
  text the same way; what it logs about counts and the not-a-plate rule is numbers.
- What still holds plate text outside the database, by design and listed here: the local-alerts file and
  the spool batches (2.3), the evidence crops' file names (2.5), the evaluation files (2.4), and the
  detection report the organisers ask for, whose reads CSV since 8 Oct also carries each crop file's
  SHA-256 so a reader can check later that a crop is the one the report showed (an integrity check, not a
  signature).

## 3. Purpose limitation and audit

- Every movement query is written to an **append-only audit log** with the operator identity, the
  plate, the time window and the stated investigative purpose (optional in the PoC). A plate search
  is logged with the operator, the plate and the number of results. Listing a camera's recent
  sightings without naming a plate, which also shows plates, is audited since 8 Oct (`sightings.recent`,
  with the camera and the number of rows, never the plates), as is a watchlist check of one plate
  (`watchlist.check`, with the plate, like a search) and an export of the camera registry
  (`camera.export`, with the row count). Database rules make UPDATE and DELETE on the log no-ops.
- Adding a plate to the watchlist also looks back over the last 24 hours of sightings (exact reads
  and, for a plate added by hand, reads one character off), so a vehicle that passed before it was
  listed raises one alert, marked retrospective. The look-back is part of the audited
  `watchlist.create` record, with the plate and how many earlier sightings it found.
- Drawing or changing an intrusion zone is audited (`camera.zones`), with the ids of the zones
  that resulted.
- Every plate review is audited (`plate.review`, a change to one `plate.review.edit`, a listing of them
  `plate.review.list`) with the sighting id or the listing's scope, mode and verdict, never the plate text (2.5).
- Live-video views are not yet audited one by one: in the proof of concept the media relay is
  open to viewers on the local network. In production the relay asks the API whether a user may
  watch a camera (HLD 11.2), which is where each view is authorised and logged.
- The `auditor` role can read the log and reports, including the aggregate vehicle and person
  counts, but cannot view footage or search plates: oversight without operational access. It can
  check stored plate crops on the plate review page (2.5), which offers them by camera and time, never
  by plate. Counts, fleet
  and plate-reading quality reports are not audited per read; they are aggregates with no personal data
  (the quality report holds counts, medians and rates per camera, never plate text or a crop), and
  auditing a 30-second dashboard refresh would bury the plate searches the log exists to protect.

## 4. Role-based and departmental scoping

- Roles: admin, supervisor, operator, department nodal officer, auditor. Permissions are explicit
  lists, not implied by rank.
- A department nodal officer sees only their department's cameras. A district-scoped user sees only
  their district. Scoping is applied in the query layer, not the UI, so the API enforces it, and it
  covers evidence crops and zones too. Department scoping is tested end to end. District scoping is
  implemented but not yet tested; on 8 Oct a fault was fixed in which a user with a district and no
  department counted as statewide and saw every district.

## 5. Watchlists are sourced, not typed

Watchlist entries carry a `source` (VAHAN, eGujCop, manual) and a `source_ref` (FIR number or
upstream record id), an expiry (`valid_until`), and the creating user. An alert therefore always
traces back to a document, and a stale entry expires instead of paging the control room forever.
The copy that analytics nodes keep for outages (2.3) carries only plate, kind and severity: the
names, reasons and references stay in the core.

## 6. Public-facing private cameras

Where societies, malls or shops share feeds, the registry marks them `ownership = private_shared`
and the same audit and scoping rules apply. Consent and terms are a policy matter for the
department; the platform's job is to make the sharing visible and revocable.

## 7. What this does not solve

- Legal basis and retention periods are set by the Home Department, not by software. Until they
  are, the PoC keeps everything (section 2).
- The audit log is only as good as the review process around it. We recommend a monthly sampled
  review by the auditor role and a quarterly report to the DGP's office.
- Model bias in plate OCR (e.g. older or damaged plates) is a data problem; we log confidence
  scores so it can be measured, and we surface fuzzy matches as such rather than as certainties.
- The person and vehicle detector (stock COCO weights) has its own bias surface: it misses people
  in dense crowds, at night and at small sizes, and has no class for auto-rickshaws. For counts, a
  miss costs a number, not a wrongful stop. For an intrusion zone, a miss is a missed alert and a
  false detection sends an operator to the live view; neither rate is measured beyond the one clip
  in 2.2.
- Edge files (2.3) are unencrypted in the PoC, the local alert file is not rotated, and a deleted
  camera's crop files stay on disk (section 2). Logs no longer carry whole plates (2.6); the local
  alert file and the spool still do.
