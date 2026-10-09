# Plates stored from the organisers' sandbox, checked against their crops

Generated 2026-09-26 15:16 IST by `bench/sandbox_eye.py score` from 145 labelled of 145 stored sightings on the sandbox cameras (2026-09-25 21:06:49 to 2026-09-26 07:55:27 IST). Real Gujarat plates on government cameras (replayed recordings), not synthetic ones.

Method: the sandbox gives no ground truth, so each stored sighting was compared with its own evidence crop (the image of the best read) by the team's AI coding assistant (Claude, by Anthropic), with the stored read shown on each tile: not blind, and not a person. It is the earlier check, not the figure to quote: a team member later checked these sightings blind on the control room's Plate review page (144 reviews; `sandbox_review.md`). The crop is the best-read frame, so a plate that cannot be read in it is left out (unreadable). The labels hold real registrations and are kept locally (data/gov-sandbox/eye), not published.

| Verdict | Sightings |
|---|---|
| exact | 92 |
| one off | 4 |
| wrong | 11 |
| not a plate | 24 |
| unreadable | 14 |

**Exact, of every stored sighting a person could judge: 92/131 = 70.2%.** Within one character: 96/131 = 73.3%.
Of the sightings that were vehicle plates: exact 92/107 = 86.0%; within one character 96/107 = 89.7%.

| Camera | exact | one off | wrong | not a plate | unreadable |
|---|---|---|---|---|---|
| CAM05 | 0 | 0 | 0 | 24 | 0 |
| CAM06 | 72 | 3 | 7 | 0 | 10 |
| CAM07 | 20 | 1 | 4 | 0 | 3 |
| CAM12 | 0 | 0 | 0 | 0 | 1 |

Precision only: how many plates on screen were never stored (capture rate) needs every plate in the footage labelled, which the sandbox's live, unrecorded replay does not allow.
