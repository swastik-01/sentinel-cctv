# Not-a-plate rule on real cameras: reads dropped live

Generated 2026-10-08 09:22 IST by `bench/plate_gate_live.py` from `data/rotation-capture/worker_001_CAM06-CAM07.log` (26 Sep 15:51–18:06 IST, 135 min, 199 status lines, every stream up on 114 of them). Counts only. The rule: a read that fits a plate layout only after more than one digit was turned into a letter is dropped (`MAX_LETTERS_FROM_DIGITS=1`, `worker.check_read`).

| Camera | Sightings stored | Reads dropped as not a plate (of reads passing the gate) | Fixed-text drops |
|---|---:|---|---:|
| CAM06 | 81 | 0 (no drop logged) | 2 |
| CAM07 | 30 | 0 (no drop logged) | 0 |

Single confident reads accepted on slow cameras: 24. The worker logs the per-camera drop count only when it is above zero, so '0 (no drop logged)' means no read was dropped as not a plate in the whole run; how many reads passed the gate is then not in the log.

Limits: one run on the two sandbox cameras that read plates; the hoarding whose phone number the rule was written for is in CAM06's view, so a zero here is the rule holding against it, not a general false-positive rate on text; letter-only signage is not covered by the rule.
