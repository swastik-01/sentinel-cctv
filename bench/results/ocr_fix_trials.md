# Plate OCR fix trials: 25 changes to how a crop is read, no training

Generated 2026-09-26T15:59:16+05:30 by `bench/ocr_tta.py`. fast-plate-ocr 1.1.0, onnxruntime 1.30.0, CPU only, 2 ONNX threads, batches of 8. Every candidate reads through the product's path: fast-plate-ocr's resize, `PlateOCR`'s decode and weakest-character confidence (`ocr.py`), `normalise_plate`, and the worker's `check_read` gate (weakest character >= 0.35, `looks_like_indian_plate`, and at most 1 digit turned into a letter). The shipped model is `cct-xs-v2-global-model`. Counts and rates only: no plate text is written here.

The candidates, their order and the reading rule below were fixed before any candidate was scored. Intervals are group bootstraps (2000 draws over vehicle groups) of the candidate's rate minus the shipped model's; fixed / broken are crops the candidate gets right that the shipped model gets wrong, and the reverse; McNemar is exact and two-sided; Holm adjusts it for the 25 candidates tried on the real set.

- `sandbox-blind-v1`: 120 crops in 55 groups. Plain read against `PlateOCR.read_many`: 120/120 identical (largest confidence difference 0.0).
- `sandbox-v1`: 28 crops in 15 groups. Plain read against `PlateOCR.read_many`: 28/28 identical (largest confidence difference 0.0). Not run here, since none of this set's plates fits their slots (exact is 0 by construction): 2 models, `argentinian-plates-cnn-model`, `argentinian-plates-cnn-synth-model`.
- `reject-v1`: 23 crops in 3 groups. Plain read against `PlateOCR.read_many`: 23/23 identical (largest confidence difference 0.0).
- `ownfeed-v1`: 5528 crops in 128 groups. Plain read against `PlateOCR.read_many`: 5528/5528 identical (largest confidence difference 0.0). Not run here, since none of this set's plates fits their slots (exact is 0 by construction): 7 models, `argentinian-plates-cnn-model`, `argentinian-plates-cnn-synth-model`, `cct-s-relu-v1-global-model`, `cct-s-v1-global-model`, `cct-xs-relu-v1-global-model`, `cct-xs-v1-global-model`, `european-plates-mobile-vit-v2-model`.

A smoke run on the first 24 crops of each set checked the harness before this run. No candidate, variant, combining rule or reading rule was changed after it; only the harness changed (a model exported for batches of one, timing order, and skipping a model none of a set's plates fits). The length split near the end was added after this run, as a diagnosis.

## Summary

- A gain on real plates by the pre-specified rule (fixed > broken, Holm-adjusted McNemar p < 0.05, group lower bound above 0, and non-inferior on every other set): none of the 25 candidates.
- Most net fixes on `sandbox-blind-v1`: TTA K=8, slot vote, exact 93/120 against 88/120 (fixed 6, broken 1, McNemar p = 0.125, Holm p = 1.000); over all sets: fails: ownfeed-v1 exact; CPU 10.37x the shipped read.
- More broken than fixed on `sandbox-blind-v1`: 15 of 25 candidates.
- Non-inferior on every set run: TTA K=5, slot vote (`sandbox-blind-v1` 89/120, fixed 3, broken 2; `ownfeed-v1` +0.04% (groups -0.6% to +0.6%); CPU 6.84x); TTA K=5, mean probabilities (`sandbox-blind-v1` 89/120, fixed 3, broken 2; `ownfeed-v1` +0.11% (groups -0.5% to +0.7%); CPU 6.77x); TTA K=5, tracker vote (`sandbox-blind-v1` 89/120, fixed 2, broken 1; `ownfeed-v1` +0.83% (groups +0.3% to +1.4%); CPU 6.78x); TTA K=8, tracker vote (`sandbox-blind-v1` 91/120, fixed 4, broken 1; `ownfeed-v1` +0.94% (groups +0.3% to +1.7%); CPU 10.33x); two-line halves (`sandbox-blind-v1` 88/120, fixed 0, broken 0; `ownfeed-v1` +0.38% (groups -0.0% to +1.0%); CPU 2.34x).
- `reject-v1` (hoarding text): the shipped read lets 0/23 through the gate; candidates letting more through: none.

## What was tried

1. **Test-time augmentation.** The crop plus K variants, in this fixed order: pad -5%, pad +10%, CLAHE, shift +2 px, shift -2 px, scale 1.1, rotate +3 deg, rotate -3 deg, scale 0.9. K=3 takes the first three, K=5 the first five, K=8 the first eight. Padding is changed in the worker's own unit (0.15 x the plate box height on each side): -5% trims 0.05 box heights, +10% adds a replicated 0.10. Shifts move the picture 2 px on both axes; scale and rotation turn about the centre. The reads are combined three ways: a vote per character slot weighted by each read's confidence (the slot's confidence is then the reads' mean probability for the winner); the mean of the slot probabilities; and the tracker's own vote over the reads that pass the gate, as if the variants were extra frames.
2. **Contrast alone.** CLAHE on lightness (clip 2.0, 4 x 2 tiles); gamma that brings the mean grey to the middle (0.5 to 2).
3. **Other hub models**, alone and in two ensembles with the shipped model (slot vote). The models, all from the fast-plate-ocr author's `arg-plates` release (the repository is MIT; the README gives no separate model licence and does not document the training data; the v2 region lists do not include India):

| Model | Slots | Input | Colour | Note |
|---|---|---|---|---|
| `cct-xs-v2-global-model` | 10 | 128 x 64 | rgb | CCT XS, v2 global; shipped |
| `cct-s-v2-global-model` | 10 | 128 x 64 | rgb | CCT S, v2 global; the README's recommended default |
| `cct-s-v1-global-model` | 9 | 128 x 64 | rgb | CCT S, v1 global |
| `cct-xs-v1-global-model` | 9 | 128 x 64 | rgb | CCT XS, v1 global |
| `argentinian-plates-cnn-model` | 7 | 140 x 70 | grayscale | CNN, Argentinian plates |
| `argentinian-plates-cnn-synth-model` | 7 | 140 x 70 | grayscale | CNN, Argentinian plates, real and synthetic data |
| `european-plates-mobile-vit-v2-model` | 9 | 140 x 70 | grayscale | MobileViT-2, European plates |
| `global-plates-mobile-vit-v2-model` | 9 | 140 x 70 | grayscale | MobileViT-2, global (65+ countries) |
| `cct-s-relu-v1-global-model` | 9 | 128 x 64 | rgb | CCT S, v1 global, ReLU |
| `cct-xs-relu-v1-global-model` | 9 | 128 x 64 | rgb | CCT XS, v1 global, ReLU |

   A model with fewer than 10 slots cannot read a 10-character plate, the common Gujarat form.
4. **Two-line halves.** A crop with h/w > 0.45 is also read as its top and bottom halves (each resized by the model as a one-line plate), joined; the joined read replaces the whole-crop read when its confidence (the weaker half's) is higher.
5. **Upscaling.** A crop under 128 px wide is enlarged to 128 px wide (cubic, or Lanczos) before the model's own linear resize.

## sandbox-blind-v1 (real sandbox plates, read blind by a team member)

Shipped model on the single crop: exact 88/120 = 73.3% (Wilson 64.8%–80.4%; groups 65.8%–81.0%); within one character 108/120; passes the gate 119/120, passes and is wrong 31/120. For context, the stored sighting (the track's vote over several frames) is exact on 90/120.

| Candidate | Trial | Exact | Change, groups 95% | Fixed / broken | McNemar p | Holm p | Within one | Passes and wrong | Two-line exact | By camera, fixed / broken | CPU ms per crop (x shipped) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| shipped model, as stored | baseline | 88/120 | | | | | 108 | 31 | 10/13 | | 6.75 (1.0x) |
| TTA K=3, slot vote | 1 TTA | 89/120 | +0.8% (-2.0% to +4.0%) | 2 / 1 | 1.000 | 1.000 | 107 | 28 | 10/13 | 06 1/1; 07 1/0 | 28.92 (4.3x) |
| TTA K=3, mean probabilities | 1 TTA | 88/120 | +0.0% (-3.0% to +3.8%) | 2 / 2 | 1.000 | 1.000 | 106 | 28 | 10/13 | 06 1/2; 07 1/0 | 28.66 (4.2x) |
| TTA K=3, tracker vote | 1 TTA | 87/120 | -0.8% (-3.9% to +1.8%) | 1 / 2 | 1.000 | 1.000 | 108 | 32 | 10/13 | 06 1/0; 07 0/2 | 28.64 (4.2x) |
| TTA K=5, slot vote | 1 TTA | 89/120 | +0.8% (-2.8% to +4.6%) | 3 / 2 | 1.000 | 1.000 | 109 | 29 | 10/13 | 06 1/1; 07 2/1 | 43.18 (6.4x) |
| TTA K=5, mean probabilities | 1 TTA | 89/120 | +0.8% (-2.9% to +4.7%) | 3 / 2 | 1.000 | 1.000 | 109 | 29 | 10/13 | 06 1/1; 07 2/1 | 42.98 (6.4x) |
| TTA K=5, tracker vote | 1 TTA | 89/120 | +0.8% (-2.0% to +3.6%) | 2 / 1 | 1.000 | 1.000 | 109 | 30 | 10/13 | 06 1/0; 07 1/1 | 42.94 (6.4x) |
| TTA K=8, slot vote | 1 TTA | 93/120 | +4.2% (+0.0% to +8.5%) | 6 / 1 | 0.125 | 1.000 | 111 | 26 | 10/13 | 06 3/0; 07 3/1 | 64.34 (9.5x) |
| TTA K=8, mean probabilities | 1 TTA | 92/120 | +3.3% (+0.0% to +7.5%) | 6 / 2 | 0.289 | 1.000 | 110 | 27 | 10/13 | 06 3/1; 07 3/1 | 63.72 (9.4x) |
| TTA K=8, tracker vote | 1 TTA | 91/120 | +2.5% (-0.9% to +6.1%) | 4 / 1 | 0.375 | 1.000 | 110 | 29 | 10/13 | 06 2/0; 07 2/1 | 63.82 (9.5x) |
| CLAHE | 2 contrast | 79/120 | -7.5% (-13.0% to -2.2%) | 0 / 9 | 0.004 | 0.059 | 100 | 32 | 8/13 | 06 0/8; 07 0/1 | 9.51 (1.4x) |
| gamma | 2 contrast | 86/120 | -1.7% (-3.9% to +0.0%) | 0 / 2 | 0.500 | 1.000 | 108 | 30 | 9/13 | 06 0/2 | 6.34 (0.9x) |
| cct-s-v2-global-model | 3 other model | 53/120 | -29.2% (-37.6% to -18.9%) | 4 / 39 | 0.000 | 0.000 | 69 | 23 | 7/13 | 06 3/32; 07 1/7 | 54.18 (8.0x) |
| cct-s-v1-global-model | 3 other model | 11/120 | -64.2% (-72.7% to -55.3%) | 1 / 78 | 0.000 | 0.000 | 33 | 52 | 0/13 | 06 0/63; 07 1/15 | 99.70 (14.8x) |
| cct-xs-v1-global-model | 3 other model | 7/120 | -67.5% (-75.9% to -59.2%) | 0 / 81 | 0.000 | 0.000 | 31 | 36 | 0/13 | 06 0/66; 07 0/15 | 7.90 (1.2x) |
| argentinian-plates-cnn-model | 3 other model | 0/120 | -73.3% (-81.2% to -65.7%) | 0 / 88 | 0.000 | 0.000 | 0 | 0 | 0/13 | 06 0/70; 07 0/18 | 4.68 (0.7x) |
| argentinian-plates-cnn-synth-model | 3 other model | 0/120 | -73.3% (-80.9% to -65.6%) | 0 / 88 | 0.000 | 0.000 | 0 | 0 | 0/13 | 06 0/70; 07 0/18 | 7.59 (1.1x) |
| european-plates-mobile-vit-v2-model | 3 other model | 0/120 | -73.3% (-81.5% to -65.7%) | 0 / 88 | 0.000 | 0.000 | 6 | 0 | 0/13 | 06 0/70; 07 0/18 | 8.10 (1.2x) |
| global-plates-mobile-vit-v2-model | 3 other model | 2/120 | -71.7% (-80.0% to -63.9%) | 0 / 86 | 0.000 | 0.000 | 4 | 1 | 0/13 | 06 0/68; 07 0/18 | 8.50 (1.3x) |
| cct-s-relu-v1-global-model | 3 other model | 8/120 | -66.7% (-75.7% to -58.0%) | 1 / 81 | 0.000 | 0.000 | 31 | 46 | 0/13 | 06 0/64; 07 1/17 | 173.25 (25.7x) |
| cct-xs-relu-v1-global-model | 3 other model | 8/120 | -66.7% (-76.0% to -57.9%) | 0 / 80 | 0.000 | 0.000 | 26 | 38 | 0/13 | 06 0/65; 07 0/15 | 15.06 (2.2x) |
| ensemble: shipped + cct-s-v2 | 3 ensemble | 82/120 | -5.0% (-11.1% to +0.6%) | 3 / 9 | 0.146 | 1.000 | 101 | 27 | 9/13 | 06 2/7; 07 1/2 | 61.10 (9.1x) |
| ensemble: shipped + cct-s-v2 + global mobile-vit-v2 | 3 ensemble | 73/120 | -12.5% (-19.2% to -5.7%) | 2 / 17 | 0.001 | 0.011 | 96 | 16 | 9/13 | 06 2/12; 07 0/5 | 69.62 (10.3x) |
| two-line halves | 4 two-line | 88/120 | +0.0% (+0.0% to +0.0%) | 0 / 0 | 1.000 | 1.000 | 108 | 31 | 10/13 | none | 8.43 (1.2x) |
| upscale cubic | 5 upscale | 87/120 | -0.8% (-4.5% to +3.0%) | 2 / 3 | 1.000 | 1.000 | 105 | 29 | 10/13 | 06 2/2; 07 0/1 | 6.48 (1.0x) |
| upscale Lanczos | 5 upscale | 88/120 | +0.0% (-3.4% to +3.8%) | 2 / 2 | 1.000 | 1.000 | 106 | 26 | 10/13 | 06 2/1; 07 0/1 | 6.78 (1.0x) |

Each variant read alone (not candidates; they show what the votes are made of):

| Variant | sandbox-blind-v1 exact | Fixed / broken | Passes and wrong | ownfeed-v1 exact | Fixed / broken | CPU ms per crop |
|---|---|---|---|---|---|---|
| pad -5% | 84/120 | 4 / 8 | 29 | 5094/5528 | 62 / 276 | 6.37 |
| pad +10% | 81/120 | 1 / 8 | 31 | 4348/5528 | 50 / 1010 | 5.89 |
| shift +2 px | 77/120 | 3 / 14 | 33 | 5051/5528 | 58 / 315 | 7.01 |
| shift -2 px | 84/120 | 5 / 9 | 27 | 5142/5528 | 85 / 251 | 7.17 |
| scale 1.1 | 74/120 | 6 / 20 | 33 | 4851/5528 | 60 / 517 | 7.55 |
| rotate +3 deg | 89/120 | 7 / 6 | 28 | 4955/5528 | 56 / 409 | 6.57 |
| rotate -3 deg | 86/120 | 3 / 5 | 28 | 4781/5528 | 36 / 563 | 6.65 |
| scale 0.9 | 74/120 | 4 / 18 | 28 | 4042/5528 | 29 / 1295 | 6.79 |

**Choosing the best is part of the result.** The best candidate here, TTA K=8, slot vote, is +5 net (fixed minus broken) on all 120 crops. Chosen on a random half of the 55 groups and scored on the other half (both ways, 1000 splits), the chosen candidate's net is +3.14 on average (95% of splits +0 to +5); above zero in 88% of splits and below zero in 2%. Most often chosen: TTA K=8, slot vote (1575 of 2000 halves); TTA K=3, slot vote (153 of 2000 halves); TTA K=5, slot vote (140 of 2000 halves).

## Other sets: non-inferiority

Gate 1 of `bench/ocr_gates.md`, applied to each candidate as if it were a model candidate: on the real sets, broken <= fixed and no more crops passing wrong; on `reject-v1` (real non-plate text), no more crops passing the gate; on `ownfeed-v1` (synthetic plates on stock footage), the exact change's lower bound above -1 point and the passes-and-wrong change's upper bound below +0.5 point. Gate 0 also asks for CPU time at most 1.25x.

| Candidate | ownfeed-v1 exact | Change, groups 95% | ownfeed-v1 passes and wrong, change (95%) | ownfeed-v1 two-line fixed / broken | sandbox-v1 fixed / broken | reject-v1 passing | CPU x shipped | Reading |
|---|---|---|---|---|---|---|---|---|
| shipped model, as stored | 5308/5528 |  | 205/5528 |  | exact 25/28 | 0/23 | 1.0x | baseline |
| TTA K=3, slot vote | 5275/5528 | -0.60% (-1.4% to +0.0%) | -0.09% (-0.6% to +0.5%) | 7 / 43 | 0 / 0 | 0/23 | 4.4x | fails: ownfeed-v1 exact |
| TTA K=3, mean probabilities | 5280/5528 | -0.51% (-1.3% to +0.1%) | -0.14% (-0.7% to +0.4%) | 10 / 43 | 0 / 0 | 0/23 | 4.4x | fails: ownfeed-v1 exact |
| TTA K=3, tracker vote | 5328/5528 | +0.36% (+0.1% to +0.7%) | -0.14% (-0.4% to +0.1%) | 17 / 3 | 0 / 0 | 0/23 | 4.4x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong |
| TTA K=5, slot vote | 5310/5528 | +0.04% (-0.6% to +0.6%) | -1.07% (-1.8% to -0.4%) | 19 / 30 | 0 / 0 | 0/23 | 6.8x | non-inferior |
| TTA K=5, mean probabilities | 5314/5528 | +0.11% (-0.5% to +0.7%) | -1.09% (-1.8% to -0.5%) | 19 / 28 | 0 / 0 | 0/23 | 6.8x | non-inferior |
| TTA K=5, tracker vote | 5354/5528 | +0.83% (+0.3% to +1.4%) | -0.56% (-1.1% to -0.1%) | 24 / 1 | 0 / 0 | 0/23 | 6.8x | non-inferior |
| TTA K=8, slot vote | 5259/5528 | -0.89% (-2.2% to +0.3%) | -0.69% (-1.6% to +0.1%) | 19 / 89 | 0 / 0 | 0/23 | 10.4x | fails: ownfeed-v1 exact |
| TTA K=8, mean probabilities | 5267/5528 | -0.74% (-2.1% to +0.3%) | -0.67% (-1.4% to +0.0%) | 19 / 79 | 0 / 0 | 0/23 | 10.3x | fails: ownfeed-v1 exact |
| TTA K=8, tracker vote | 5360/5528 | +0.94% (+0.3% to +1.7%) | -0.67% (-1.3% to -0.1%) | 30 / 8 | 0 / 0 | 0/23 | 10.3x | non-inferior |
| CLAHE | 5139/5528 | -3.06% (-4.5% to -1.9%) | +0.52% (-0.5% to +1.5%) | 4 / 149 | 0 / 3 | 0/23 | 1.2x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong, sandbox-v1 breaks, sandbox-v1 passes-and-wrong, ownfeed-v1 exact, ownfeed-v1 passes-and-wrong |
| gamma | 5266/5528 | -0.76% (-1.7% to +0.1%) | -0.36% (-0.9% to +0.2%) | 17 / 56 | 0 / 1 | 0/23 | 1.2x | fails: sandbox-blind-v1 breaks, sandbox-v1 breaks, sandbox-v1 passes-and-wrong, ownfeed-v1 exact |
| cct-s-v2-global-model | 4955/5528 | -6.39% (-10.4% to -3.0%) | -0.40% (-2.5% to +1.9%) | 67 / 323 | 2 / 8 | 0/23 | 8.1x | fails: sandbox-blind-v1 breaks, sandbox-v1 breaks, sandbox-v1 passes-and-wrong, ownfeed-v1 exact, ownfeed-v1 passes-and-wrong |
| cct-s-v1-global-model | not run: no plate here fits its slots (0 by construction) |  |  |  | 0 / 24 | 0/23 | 14.8x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong, sandbox-v1 breaks, sandbox-v1 passes-and-wrong |
| cct-xs-v1-global-model | not run: no plate here fits its slots (0 by construction) |  |  |  | 0 / 25 | 0/23 | 1.2x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong, sandbox-v1 breaks, sandbox-v1 passes-and-wrong |
| argentinian-plates-cnn-model | not run: no plate here fits its slots (0 by construction) |  |  |  | n/a | 0/23 | 0.7x | fails: sandbox-blind-v1 breaks |
| argentinian-plates-cnn-synth-model | not run: no plate here fits its slots (0 by construction) |  |  |  | n/a | 0/23 | 1.1x | fails: sandbox-blind-v1 breaks |
| european-plates-mobile-vit-v2-model | not run: no plate here fits its slots (0 by construction) |  |  |  | 0 / 25 | 0/23 | 1.2x | fails: sandbox-blind-v1 breaks, sandbox-v1 breaks |
| global-plates-mobile-vit-v2-model | 0/5528 | -96.02% (-97.6% to -94.2%) | -2.91% (-5.2% to -0.5%) | 0 / 3191 | 0 / 25 | 0/23 | 0.9x | fails: sandbox-blind-v1 breaks, sandbox-v1 breaks, ownfeed-v1 exact |
| cct-s-relu-v1-global-model | not run: no plate here fits its slots (0 by construction) |  |  |  | 0 / 24 | 0/23 | 25.7x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong, sandbox-v1 breaks, sandbox-v1 passes-and-wrong |
| cct-xs-relu-v1-global-model | not run: no plate here fits its slots (0 by construction) |  |  |  | 0 / 25 | 0/23 | 2.2x | fails: sandbox-blind-v1 breaks, sandbox-blind-v1 passes-and-wrong, sandbox-v1 breaks, sandbox-v1 passes-and-wrong |
| ensemble: shipped + cct-s-v2 | 5281/5528 | -0.49% (-2.5% to +1.2%) | -1.25% (-2.2% to -0.4%) | 39 / 86 | 1 / 0 | 0/23 | 9.2x | fails: sandbox-blind-v1 breaks, ownfeed-v1 exact |
| ensemble: shipped + cct-s-v2 + global mobile-vit-v2 | 4786/5528 | -9.44% (-13.9% to -5.7%) | -2.10% (-3.7% to -0.7%) | 30 / 260 | 1 / 1 | 0/23 | 10.0x | fails: sandbox-blind-v1 breaks, ownfeed-v1 exact |
| two-line halves | 5329/5528 | +0.38% (-0.0% to +1.0%) | -0.27% (-0.8% to +0.0%) | 23 / 2 | 0 / 0 | 0/23 | 2.3x | non-inferior |
| upscale cubic | 5327/5528 | +0.34% (-0.2% to +0.9%) | -0.76% (-1.5% to -0.1%) | 36 / 20 | 0 / 1 | 0/23 | 1.2x | fails: sandbox-blind-v1 breaks, sandbox-v1 breaks, sandbox-v1 passes-and-wrong |
| upscale Lanczos | 5304/5528 | -0.07% (-1.0% to +0.9%) | -0.34% (-1.3% to +0.6%) | 44 / 53 | 0 / 1 | 0/23 | 1.1x | fails: sandbox-v1 breaks, sandbox-v1 passes-and-wrong, ownfeed-v1 exact, ownfeed-v1 passes-and-wrong |

## Why the slot vote breaks two-line plates (post hoc)

Added after the slot vote was seen to break two-line plates on `ownfeed-v1`; a diagnosis, not a candidate. Each TTA candidate's fixes and breaks, split by whether the reads it combines agree on length. A slot vote lines characters up by position, so one variant that drops or adds a character shifts every slot after it; the tracker votes only over the reads of the most common length.

| Candidate | sandbox-blind-v1: mixed lengths, crops / fixed / broken | sandbox-blind-v1: one length, fixed / broken | sandbox-v1: mixed lengths, crops / fixed / broken | sandbox-v1: one length, fixed / broken | ownfeed-v1: mixed lengths, crops / fixed / broken | ownfeed-v1: one length, fixed / broken |
|---|---|---|---|---|---|---|
| TTA K=3, slot vote | 18 / 2 / 1 | 0 / 0 | 1 / 0 / 0 | 0 / 0 | 806 / 5 / 46 | 13 / 5 |
| TTA K=3, mean probabilities | 18 / 2 / 2 | 0 / 0 | 1 / 0 / 0 | 0 / 0 | 806 / 6 / 44 | 15 / 5 |
| TTA K=3, tracker vote | 18 / 1 / 0 | 0 / 2 | 1 / 0 / 0 | 0 / 0 | 806 / 14 / 5 | 11 / 0 |
| TTA K=5, slot vote | 32 / 3 / 2 | 0 / 0 | 8 / 0 / 0 | 0 / 0 | 930 / 21 / 27 | 13 / 5 |
| TTA K=5, mean probabilities | 32 / 3 / 2 | 0 / 0 | 8 / 0 / 0 | 0 / 0 | 930 / 21 / 26 | 13 / 2 |
| TTA K=5, tracker vote | 32 / 2 / 1 | 0 / 0 | 8 / 0 / 0 | 0 / 0 | 930 / 29 / 3 | 20 / 0 |
| TTA K=8, slot vote | 39 / 6 / 1 | 0 / 0 | 10 / 0 / 0 | 0 / 0 | 1261 / 24 / 89 | 18 / 2 |
| TTA K=8, mean probabilities | 39 / 6 / 2 | 0 / 0 | 10 / 0 / 0 | 0 / 0 | 1261 / 24 / 81 | 16 / 0 |
| TTA K=8, tracker vote | 39 / 4 / 1 | 0 / 0 | 10 / 0 / 0 | 0 / 0 | 1261 / 38 / 10 | 24 / 0 |

## Caveats

- `sandbox-blind-v1` is a test set under `bench/ocr_gates.md` (Addendum 1), which forbids tuning on it. Choosing a fix from this table is tuning, so the winner's number here is optimistic (see the cross-selection line), and a fix chosen from it needs fresh blind-read plates (new sightings, not in the set) before any gain is claimed.
- The real set is 120 crops of stored sightings: only plates Sentinel already stored, read by the shipped model, so it leans towards the shipped model. It says nothing about plates missed.
- The true plate is one team member's blind reading, right 222 times in 226 on our own plates (`review_truth.md`); 9 of the 120 are not in `normalise_plate`'s form, so no candidate can match them.
- The crops are the stored evidence crops (JPEG quality 85, already the track's best-confidence read). Variants of one crop share its blur, angle and light, so TTA is a floor on what more frames would give.
- `ownfeed-v1` was labelled by matching the stored read within 2 edits, so it favours the shipped model; its plates are synthetic, painted on Pexels stock footage. `sandbox-v1` and `reject-v1` were labelled by our AI coding assistant, not blind; `sandbox-v1`'s 28 crops are all inside the blind set.
- CPU ms is wall time on a laptop shared with live workers (GPU) and other CPU jobs, making the view included: compare within this run only. It is per crop read once; the worker reads each crop once per frame.
