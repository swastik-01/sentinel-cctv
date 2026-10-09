# OCR fine-tune: adoption gates (pre-registered)

Written 2026-09-25 22:45 IST, before any fine-tuned candidate was trained to completion or scored. The baseline is the
shipped `cct-xs-v2-global-model` (fast-plate-ocr 1.1.0); its numbers are in `bench/results/ocr_baseline.md`. A candidate
is adopted only if it passes every gate below. The gates are not changed after a candidate's result is seen; a
candidate that fails is recorded as failed.

**Candidate.** The published `cct_xs_v2_global.keras` fine-tuned on synthetic Indian-format plates from
`bench/plategen.py` (`data/ocr-train/train.csv`, validation `val.csv`), CPU only, 10 slots, the plate-only head,
`plate_config_india.yaml`. No real crop (sandbox or own-feed) is used for training. The real sets below are test-only
and frozen (`bench/ocr_sets.py` refuses to rebuild a set).

**Gate 0: integrity.** The exported ONNX has input `input` [N,64,128,3] uint8 with a dynamic batch and output `plate`
[N,10,37]. A load self-check reads a synthetic plate. CPU time per crop is at most 1.25x the baseline, measured back to
back on the same laptop with the worker stopped. `pytest` passes after the integration change.

**Gate 1: real frozen sets, non-inferiority only.** Scored with `bench/ocr_ab.py` (product preprocessing, weakest
character confidence, `normalise_plate`, the worker gate).
- `sandbox-v1` (real Gujarat plates, CAM06): breaks ≤ fixes on exact; passes-and-wrong for the candidate ≤ the baseline.
- `reject-v1` (real non-plate text, CAM05): crops passing the gate ≤ the baseline.
- `ownfeed-v1` (synthetic plates painted on stock footage): group-bootstrap 95% interval of the exact-rate difference
  has a lower bound above −1.0 point; the passes-and-wrong difference has an upper bound below +0.5 point.

**Gate 2: held-out synthetic set** (`data/ocr-train/test.csv`, never trained on; one third in a font kept out of
training). The candidate is better on exact, McNemar p < 0.05, and not significantly worse on the held-out font or on
two-line plates taken alone.

**Gate 3: live product run on own feeds.** AMD-TRAF-001 and AMD-TRAF-002 on one worker under the conditions of
`bench/results/anpr_eval_current.md`; baseline and candidate in alternating 10-minute windows (A B A B) in one session,
scored by `scripts/anpr_eval.py`. The candidate's stored-sighting exact rate and capture are no worse than the
same-session baseline.

**What may be claimed.** If adopted: non-inferiority on the real sets and the measured gain on synthetic plates. A gain
on real Gujarat plates is claimed only with McNemar p < 0.05, fixes > breaks and a bootstrap interval above zero on a
real set, which `sandbox-v1` (28 crops, 15 vehicles, one camera) is too small to show. If adopted, every document that
names the model, its slots or its accuracy is re-measured and updated together.

## Addendum 1: a blind-read real set (2026-09-26 13:38 IST, before training starts)

Written before the fine-tune run `ft1` was started, so before any candidate had been trained or scored on this set;
no candidate has been scored on any real set. Gates 0 to 3 above are unchanged. This adds one real test set to Gate 1,
and a candidate must pass it as well as every gate above.

**The set.** `data/ocr-eval/sandbox-blind-v1`, frozen on 26 Sep by `bench/ocr_sets.py blind`: 120 vehicle-plate
crops in 55 groups (107 one-line, 13 two-line; CAM06 92, CAM07 27, CAM12 1). Each is the stored best crop of a sandbox
sighting that a team member read blind on the Plate review page (`plate_reviews`, mode `blind`), and their reading is
the true plate. The 24 hoarding reviews (not a plate) are left out. The baseline on it is in
`bench/results/ocr_baseline_blind.md`: single crop exact 88/120, passes-and-wrong 31/120.

**Gate 1 addition.** Scored with `bench/ocr_ab.py` like the other sets, the candidate against the baseline, both
re-reading the same crops:
- `sandbox-blind-v1`: breaks ≤ fixes on exact; passes-and-wrong for the candidate ≤ the baseline.
- A gain on real Gujarat plates may be claimed from this set only with McNemar p < 0.05 on exact (paired), fixes >
  breaks, and a group-bootstrap 95% interval of the exact-rate difference with a lower bound above 0. The exact test
  needs at least 6 fixes with no break, 8 with one, or 10 with two; anything less is non-inferiority only.

**How it is read.**
- The comparison is single crop against single crop. The stored read (the track's vote, made by the baseline) is
  reported beside it for context and is not the bar a candidate must clear.
- The answers stay as frozen. 9 of the 120 are not in `normalise_plate`'s form, so exact is at most 111/120 for any
  model; they count against both models equally. If a second blind review adjudicates the disputed readings, it is
  frozen as `sandbox-blind-v2` and reported beside v1; it does not replace v1 for this candidate's decision.
- The set is not independent of `sandbox-v1`: it holds all 28 of its crops. Both gates apply.
- It holds only sightings Sentinel stored with the baseline, so it leans towards the baseline. That is accepted: it
  makes the gate harder for a candidate, not easier.
- Test only. These are the organisers' sandbox crops and are never used for training, validation, checkpoint choice or
  tuning of any threshold.

## Addendum 2: the worker's full gate, a fresh real set, and no adoption before the submission (2026-09-26 16:15 IST)

(Time corrected at 16:45 IST: the heading first said 16:40, a time not yet reached when the file was saved at 16:15.)

Written while `ft1` was in its second epoch, before any fine-tuned candidate had been exported or scored on any set.
Gates 0 to 3 and Addendum 1 are unchanged, except as follows.

- **The gate is the worker's `check_read`.** "The worker gate" in Gate 1 means the product's gate. Since 26 Sep that
  includes the letters-from-digits rule (`MAX_LETTERS_FROM_DIGITS`, default 1). `bench/ocr_ab.py` now applies it,
  and it is re-checked today on the shipped model: reject-v1 0 of 23 crops pass (the older harness counted 23 of 23);
  sandbox-blind-v1 still 88/120 exact, 119/120 passing and 31/120 passing and wrong
  (`bench/results/ocr_baseline_checkread.md`, all four sets, 16:40 IST). The reject-v1 gate therefore
  requires the candidate to let 0 of 23 through. Baseline and candidate are always scored in one `ocr_ab.py` run.
- **`sandbox-fresh-v1` joins Gate 1** once it is frozen as `bench/pipeline_gates.md` defines it (new blind reviews of
  sandbox sightings stored after v1, freeze by 27 Sep 10:00 IST). There: breaks ≤ fixes on exact, and passes-and-wrong
  for the candidate ≤ the baseline, on all rows and on new vehicles alone. No candidate is scored on those crops before
  the freeze. If the set is not frozen by 3 Oct, this gate lapses and the report says so.
- **A real-plate gain** is claimed only if Addendum 1's criteria hold on `sandbox-blind-v1` and fixes > breaks on
  `sandbox-fresh-v1`.
- **Not before the submission.** Whatever it scores, no candidate replaces the shipped model before the 27 Sep
  submission: the pack describes the shipped build, and Gate 3's live run cannot be done while the sandbox capture
  holds the GPU. Adoption is for the 12–13 Oct finale, with every gate passed by 9 Oct 18:00 IST.
