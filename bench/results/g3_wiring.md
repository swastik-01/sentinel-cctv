# G3 confidence marking: L wiring pair and live T checks

Generated 2026-10-08T09:31+05:30 IST by `bench/g3_wiring.py` at commit `327cbcd`. Gate: `bench/pipeline_gates.md` G3. Worker: AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001, AMD-AMC-001; HW_DECODE=auto, object detection on, STATIC_TEXT_WINDOW_S=0, every other setting at its default; restarted between windows; the GTX 1650 Ti laptop on AC. A = API with CONFIDENCE_MARKING off (shipped), B = on. Scored: the two stock-footage cameras (synthetic plates), the worker's own tracks, as `scripts/anpr_eval.py` selects them. The laptop also ran the control room dev server and this session's tools during both windows (analysed fps below the 4.5 per camera of anpr_eval_current.md in both arms alike); the CPU was about 15% busy before the first window.

| Arm | Window (IST) | Scored sightings (anpr_eval / API) | Below 0.9 (anpr_eval) | Marked by the API | Exact | Alerts with latency | Median s | p95 s | Analysed fps (total, median) |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| A | 09:04–09:14 | 745 / 745 | 141 | 141 (read back with marking on) | 97.9% (729/745) | 3 | 2.246 | 2.611 | 9.0 |
| B | 09:19–09:29 | 748 / 748 | 161 | 161 | 97.2% (727/748) | 4 | 1.679 | 2.823 | 9.5 |

## Checks

- [PASS] A: API rows equal anpr_eval's scored rows
- [PASS] B: API rows equal anpr_eval's scored rows
- [PASS] B: marked share equals anpr_eval's below-0.9 share (exact)
- [PASS] B: median latency <= A + 0.2 s
- [PASS] T: alert count equal with marking off and on (same ingests)
- [PASS] T: live checks all passed, off and on

**Verdict: PASS.** The T block's pytest tests are in `services/api/tests/test_marking.py`; the live part (a 0.85 sighting marked, a 0.90 stored as REAL and read back not marked, a one-character alert marked, `reads` and `agreement` written, the alert count with marking off and on) is `bench/g3_check.py`, run with marking off at 2026-10-08T03:32:39+00:00 and on at 2026-10-08T03:47:43+00:00 (synthetic plates on two simulator cameras, removed afterwards). The F leg (the fresh sandbox set, by band) is not run: `sandbox-fresh-v1` is not frozen, so no claim that confidence separates right from wrong reads is made beyond the 120 blind-checked plates already reported; the marking ships as a review aid.
