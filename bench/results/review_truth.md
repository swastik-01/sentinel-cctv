# Blind review checked against known plates (blind mode)

Generated 2026-09-26 12:27 IST by `bench/review_truth.py` (read-only). Reviews on our own cameras, where the true plates are known: the synthetic clips' plates (`feedsim/cameras.yaml`) and the plates painted on the two stock clips (`feedsim/media/*.plates.json`; other vehicles there carry real, unlabelled plates, so a read matching none of the painted ones counts as 'far'). Reviewers: admin 226.

Each review is scored twice. *Reviewer*: the plate the person typed against the known plates. *Sentinel*: the stored read against the known plates. *Disagreements*: reviews the page graded one-off or wrong; the truth says whose reading was wrong.

| Camera | Reviews | Reviewer right | Reviewer one off | Sentinel right | Sentinel one off | Disagreements | …reviewer wrong | …Sentinel wrong | …both or unknown |
|---|---|---|---|---|---|---|---|---|---|
| AMD-AMC-001 | 31 | 31 (100.0%) | 0 | 20 (64.5%) | 10 | 11 | 0 | 11 | 0 |
| AMD-POL-001 | 8 | 8 (100.0%) | 0 | 7 (87.5%) | 1 | 1 | 0 | 1 | 0 |
| AMD-TRAF-001 | 24 | 24 (100.0%) | 0 | 19 (79.2%) | 5 | 5 | 0 | 5 | 0 |
| AMD-TRAF-002 | 120 | 117 (97.5%) | 3 | 116 (96.7%) | 4 | 7 | 3 | 4 | 0 |
| GNR-GSRTC-001 | 21 | 21 (100.0%) | 0 | 16 (76.2%) | 0 | 5 | 0 | 5 | 0 |
| MHS-POL-001 | 22 | 21 (95.5%) | 1 | 11 (50.0%) | 11 | 12 | 1 | 11 | 0 |
| **All** | 226 | 222 (98.2%) | 4 | 189 (83.6%) | 31 | 41 | 4 | 37 | 0 |
