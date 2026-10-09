# Finale plate-pipeline changes: what passed its gate, what did not, what was not built

The gates are pre-registered in `bench/pipeline_gates.md` (26 Sep 2026); the decision date was 9 Oct 18:00 IST. This
index was written on 8 Oct 2026 from the script-produced files it cites; it adds no number of its own.

| Change | Built | Gate result | Adopted | Evidence |
|---|---|---|---|---|
| G3 confidence marking: reads below 0.9 and one-character alerts marked "check the crop"; `reads` and `agreement` stored | Yes (8 Oct; API setting `CONFIDENCE_MARKING`) | **PASS**: T (pytest `test_marking.py`; live `bench/g3_check.py` with marking off and on, 5 + 7 checks); L wiring pair (B's marked share 161 of 748 scored sightings = anpr_eval's below-0.9 count exactly; median latency 1.68 s against A's 2.25 s, 4 and 3 alerts); F not run (sandbox-fresh-v1 not frozen) | **Yes**, default on from 8 Oct; `false` restores the 26 Sep behaviour. No claim that confidence separates right from wrong reads beyond the 120 blind-checked plates (69 of 81 exact at >= 0.9 against 21 of 39 below) | `bench/results/g3_wiring.md`, `.json`; `data/g3/` (logs, check files) |
| OCR fine-tune ft1 (`bench/ocr_gates.md`) | Yes (26 Sep) | Gate 0 and Gate 1 on the four frozen sets PASS; non-inferior only on real plates (sandbox-blind-v1 88 → 89 of 120, 8 fixed / 7 broken, p = 1.0; 69 → 66 exact among the 81 at >= 0.9); Gate 1's fresh-set leg lapsed (set never frozen); Gates 2 and 3 not run | **No** | `bench/results/ocr_ft1.md` |
| G0 instrumentation | No | not run | No | — |
| G2 one-read acceptance at any rate; length tie-break | No | not run | No | — |
| G2b longer third-read hold | No (needs G0) | not run | No | — |
| G4 evidence crop agreeing with the stored plate | No | not run | No | — |
| G5 plate detector at 960 px | No (needs G0, finale hardware, a capacity re-run) | not run | No | — |
| G6 analysis rate on plate cameras | No (needs G0) | not run | No | — |
| YOLOX detectors (`bench/detector_gates.md`) | Not trained | not run | No | — |

So the plate pipeline that runs at the finale is the 26 Sep build plus G3's marking: every accuracy, capture and
latency figure in the submission pack still describes it. The not-a-plate rule's live figure from the 26 Sep
capture log is in `bench/results/plate_gate_live.md` (0 reads dropped in 135 minutes on CAM06/CAM07, 111 sightings
stored).
