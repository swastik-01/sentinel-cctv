# Blind-checked sandbox plates: why the misses missed

Generated 2026-09-26 16:51 IST by `bench/blind_errors.py` (read-only; nothing re-read or tuned). Set: `sandbox-blind-v1`, 120 stored sandbox plates a team member read blind on the Plate review page (`ocr_baseline_blind.md`): 90 exact, 30 misses (17 one off, 13 wrong). A miss is the review page's verdict: the stored read differs from the reviewer's reading. Counts and rates only: no plate text.

**How to read this.** The reviewer's reading is the answer in the headline numbers. The split into *Sentinel* and *reviewer* misses below comes from `data/ocr-eval/blind-errors/adjudication.csv`, written by our AI coding assistant from each miss's crop with both readings in view, and from the same vehicle's other passes where the sandbox loop replayed it. It is not blind and not a person, and the same kind of label overstated `sandbox-v1`, so it ranks causes; it does not correct the headline number. Only a second blind reviewer can.

## 1. Whose reading does the crop support?

| Side | Misses | Causes |
|---|---|---|
| Sentinel's stored read is wrong | 13 | dropped-char 5; letter-lookalike 3; digit-misread 3; vote-chose-short 1; edge-misread 1 |
| both readings wrong | 1 | digit-misread 1 |
| the reviewer's reading is wrong | 13 | typo 5; lookalike-typed 4; reviewer-misread 4 |
| cannot tell from the crop | 3 | unreadable 3 |

Causes: *dropped-char*: a character dropped: ten-character plate stored as nine; *vote-chose-short*: the vote took the length of truncated reads; the best single read was right; *edge-misread*: last characters misread where the plate box stopped short of the plate's end; *digit-misread*: a digit read as another digit; *letter-lookalike*: a letter read as a similar letter; *typo*: reading has an extra, missing or doubled character, or an impossible state code; *lookalike-typed*: reviewer typed a look-alike where the format fixes a letter or a digit; *reviewer-misread*: crop (and the same vehicle's exact pass, where there is one) shows the stored characters; *unreadable*: crop too small or blurred to say who is right.

Visible conditions on the Sentinel-side misses (one miss can have two): yellow plate 3; blur 3; box short of the plate's right end 2; thin typeface 2; clear crop 1; motion blur 1; low contrast 1; monochrome picture 1; skewed plate 1; occluder across a character 1; tiny two-line crop 1; unusual typeface 1.

Evidence against the reviewer's reading that needs no judgement: the reading is not a valid registration as typed on 12 misses; it equals the stored read once both go through `normalise_plate` on 2; the same stored plate on the same camera was judged exact by the same reviewer on another pass of the loop on 6. At least one of these holds on 14 misses: 12 of the 13 put on the reviewer side, 1 of the 14 on the Sentinel side, 1 of the 3 unclear.

The quoted figure stays 90/120: this split estimates no corrected figure, and only a second blind reviewer can change the answer key (a correction to the key, not a gain in the product).

**A blind check on the split.** Because the split above was made with both readings in view, the same assistant read the 30 misses again blind: shuffled among 15 random hits on contact sheets that show no reading, verdict or id, typed before the key was opened (`bench/blind_errors.py --sheets`). Which reading its own matches, after `normalise_plate`:

| Split above | Crops | Stored read only | Reviewer's reading only | Both (equal once normalised) | Neither | Marked unsure |
|---|---|---|---|---|---|---|
| Sentinel's stored read is wrong | 13 | 0 | 11 | 0 | 2 | 7 |
| both readings wrong | 1 | 0 | 0 | 0 | 1 | 1 |
| the reviewer's reading is wrong | 13 | 11 | 0 | 2 | 0 | 4 |
| cannot tell from the crop | 3 | 1 | 0 | 0 | 2 | 2 |
| hits (the control) | 15 | 0 | 0 | 14 | 1 | 1 |

On the hits, the reviewer's reading, the stored read and the blind reading agree on 14 of 15. The blind reading sides with the stored read on 13 of the 13 reviewer-side misses, and differs from the stored read on 14 of the 14 Sentinel-side ones, so the split holds up when read blind. It is still one AI reader, so it too corrects nothing: only a person's blind reading can change the quoted figure.

## 2. What the misses share

Medians, and the AUC: the chance that a miss has the lower value when a miss and a hit are drawn at random (0.5 means no difference; above 0.5, misses tend to be lower). The 95% interval is a bootstrap over groups (a vehicle the loop replayed, or crops seconds apart, is one group; 2000 draws). *Sentinel-side* compares the Sentinel-side misses with the hits and leaves the reviewer-side and unclear misses out.

| Measure | Hits | All misses | AUC (95%) | Sentinel-side misses | AUC (95%) |
|---|---|---|---|---|---|
| crop width, px | 112 | 108 | 0.56 (0.44–0.68) | 108 | 0.54 (0.37–0.72) |
| crop height, px | 39 | 38 | 0.57 (0.45–0.68) | 38 | 0.54 (0.36–0.67) |
| plate box width per character, px | 11.5 | 10.5 | 0.61 (0.47–0.73) | 10.4 | 0.59 (0.42–0.75) |
| sharpness at the model's 128x64 input (Laplacian variance) | 1902 | 1762 | 0.60 (0.49–0.70) | 1626 | 0.61 (0.48–0.75) |
| sharpness at native size (Laplacian variance) | 7406 | 7600 | 0.53 (0.42–0.64) | 6401 | 0.61 (0.46–0.77) |
| plate brightness (mean grey, 0-255) | 145 | 146 | 0.49 (0.38–0.58) | 150 | 0.46 (0.29–0.63) |
| plate contrast (grey p95 - p5) | 230 | 236 | 0.43 (0.32–0.58) | 232 | 0.46 (0.27–0.65) |
| Sentinel's stored confidence | 0.958 | 0.849 | 0.72 (0.63–0.81) | 0.724 | 0.84 (0.73–0.93) |
| confidence of the single-crop re-read | 0.946 | 0.829 | 0.70 (0.60–0.80) | 0.623 | 0.83 (0.70–0.94) |
| plate detector confidence | 0.62 | 0.59 | 0.55 (0.44–0.67) | 0.58 | 0.59 (0.41–0.76) |
| reads in the track (worker log) | 3 | 2 | 0.60 (0.49–0.70) | 2 | 0.56 (0.43–0.69) |

Crop sizes include the worker's pad (15% of the box height on each side). Reads per track come from the worker's log line for the sighting (120 of 120 found). When three or more reads agree unanimously, `tracker.py` raises the stored confidence to at least 0.6 + 0.1 per read, so 0.900 exactly marks a unanimous three-read vote whose best single read was below 0.9.

**Camera**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| CAM06 | 92 | 71/92 (77%) | 10 | 10 | 1 |
| CAM07 | 27 | 19/27 (70%) | 4 | 3 | 1 |
| CAM12 | 1 | 0/1 (0%) | 0 | 0 | 1 |

**Analysis window**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| 25 Sep evening run | 75 | 54/75 (72%) | 10 | 9 | 2 |
| 26 Sep morning run | 45 | 36/45 (80%) | 4 | 4 | 1 |

**Picture**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| colour | 93 | 71/93 (76%) | 10 | 10 | 2 |
| monochrome | 27 | 19/27 (70%) | 4 | 3 | 1 |

**Plate colour**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| green | 2 | 2/2 (100%) | 0 | 0 | 0 |
| not visible (monochrome picture) | 27 | 19/27 (70%) | 4 | 3 | 1 |
| white | 73 | 54/73 (74%) | 7 | 10 | 2 |
| yellow | 18 | 15/18 (83%) | 3 | 0 | 0 |

**Layout**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| one-line | 107 | 79/107 (74%) | 13 | 13 | 2 |
| two-line | 13 | 11/13 (85%) | 1 | 0 | 1 |

**Vehicle bound to the plate**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| bus | 10 | 8/10 (80%) | 2 | 0 | 0 |
| car | 63 | 46/63 (73%) | 7 | 9 | 1 |
| motorcycle | 2 | 1/2 (50%) | 1 | 0 | 0 |
| not bound to a vehicle | 28 | 20/28 (71%) | 3 | 3 | 2 |
| truck | 17 | 15/17 (88%) | 1 | 1 | 0 |

**Sentinel's stored confidence**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| < 0.6 | 6 | 1/6 (17%) | 3 | 1 | 1 |
| 0.6-0.8 | 21 | 13/21 (62%) | 6 | 1 | 1 |
| 0.8-0.9 | 12 | 7/12 (58%) | 2 | 3 | 0 |
| >= 0.9 | 81 | 69/81 (85%) | 3 | 8 | 1 |

**Reads in the track**

| | Plates | Exact | Sentinel-side misses | Reviewer-side | Unclear |
|---|---|---|---|---|---|
| 1 | 34 | 24/34 (71%) | 3 | 6 | 1 |
| 2 | 25 | 15/25 (60%) | 6 | 2 | 2 |
| 3 | 61 | 51/61 (84%) | 5 | 5 | 0 |

The 25 Sep evening run's windows span 20:07–23:48 IST, the 26 Sep morning run's 06:51–07:58 IST, both on our clock (`sandbox_daynight.md`). The sandbox replays fixed recorded clips, each camera's from one time of day and looping, so both runs replayed the same footage: the split is by run, not by day and night. CAM07 sent a monochrome picture in every crop, in both runs, so plate colour cannot be seen there.

## 3. Which characters went wrong

Edits from the reviewer's reading, put through `normalise_plate` (so a look-alike typed where the format fixes a letter or a digit does not count), to the read. Position is the part of the plate the reading's character sits in.

**stored, all misses** (30 plates; edits per plate: 0 2, 1 16, 2 9, 3 or more 3)

| Edit | Position | Count |
|---|---|---|
| character extra | reading not a standard plate | 8 |
| character dropped | number | 6 |
| character dropped | reading not a standard plate | 2 |
| character dropped | series | 2 |
| digit for digit | number | 11 |
| letter/digit look-alike | series | 6 |
| digit for digit | district | 4 |
| letter for similar letter | series | 3 |
| letter for other letter | series | 3 |
| letter for similar letter | state | 1 |
| letter for other letter | state | 1 |

Substitutions, reading > read: A>4 2, 3>2 2, 2>1 1, O>Q 1, 8>9 1, 7>1 1, Z>2 1, O>D 1, Z>A 1, 4>5 1, 2>0 1, 1>4 1, D>Q 1, 1>7 1, 4>3 1, 9>3 1, H>M 1, K>X 1, C>G 1, H>J 1, 8>0 1, 2>7 1, G>6 1, L>1 1, B>8 1, 9>8 1, 3>4 1.
Lengths, reading > read: 3>10 1, 9>10 1, 10>9 6, 11>10 2, 12>10 1.

**stored, Sentinel-side misses** (14 plates; edits per plate: 1 7, 2 6, 3 or more 1)

| Edit | Position | Count |
|---|---|---|
| character dropped | number | 6 |
| letter/digit look-alike | series | 6 |
| digit for digit | number | 4 |
| digit for digit | district | 3 |
| letter for other letter | series | 2 |
| letter for similar letter | series | 1 |

Substitutions, reading > read: A>4 2, 2>1 1, 8>9 1, 7>1 1, Z>2 1, D>Q 1, 1>7 1, 4>3 1, 9>3 1, H>M 1, K>X 1, 2>7 1, G>6 1, L>1 1, B>8 1.
Lengths, reading > read: 10>9 6.

**single-crop re-read, where it is not exact** (32 plates; edits per plate: 0 2, 1 18, 2 10, 3 or more 2)

| Edit | Position | Count |
|---|---|---|
| character extra | reading not a standard plate | 8 |
| character dropped | number | 4 |
| character dropped | reading not a standard plate | 2 |
| character dropped | series | 2 |
| digit for digit | number | 12 |
| digit for digit | district | 6 |
| letter for other letter | series | 5 |
| letter/digit look-alike | series | 4 |
| letter for similar letter | series | 3 |
| letter/digit other | reading not a standard plate | 1 |
| letter for similar letter | state | 1 |
| letter for other letter | state | 1 |

Substitutions, reading > read: 8>0 2, 3>2 2, 2>1 1, O>Q 1, J>3 1, 8>9 1, 7>1 1, Z>2 1, O>D 1, Z>A 1, 4>5 1, Y>T 1, 3>1 1, 2>0 1, W>X 1, D>Q 1, 1>7 1, 4>3 1, 9>3 1, H>M 1, K>X 1, C>G 1, H>J 1, 1>4 1, 3>7 1, 2>7 1, L>1 1, B>8 1, A>4 1, 9>8 1, 3>4 1.
Lengths, reading > read: 3>10 1, 9>10 1, 10>9 4, 11>10 2, 12>10 1.

On the Sentinel side, 6 of the 6 letter/digit look-alike edits sit on a plate stored one character short: they are `normalise_plate` turning the second series letter into a digit after the drop (section 4), not the model mistaking a letter for a digit. Position-by-position repair already absorbs the classic look-alikes (O/0, D/0, Q/0, B/8, Z/2, S/5) wherever the format fixes the kind of character; what is left is digit for digit, letter for letter, and dropped characters. In the series, where any letter may stand, the round letters D, O and Q are still confused with each other: 1 on the Sentinel-side stored reads, 3 on the single-crop re-reads.

## 4. Dropped characters

Of the 14 Sentinel-side misses, 6 are a ten-character plate stored as nine. `normalise_plate` then turns the second series letter into the number's first digit (the reading's letter A becomes a 4, Z a 2, L a 1, B an 8), so the result is a valid one-letter-series plate and passes `looks_like_indian_plate`: the gate cannot see the loss. Re-reading the stored crop alone, over all 14 Sentinel-side misses: right on 1, the same wrong read on 12, a different wrong read on 1. So the misreads are the model's, not the vote's. On one (cause *vote-chose-short*) the best single read was right and the track's vote still stored the short read: `tracker.vote` keeps only reads of the modal length, so two short reads outvote one full one.

Where the character went, for ten-character plates read as nine (a repeated character counts at its later position):

| Reads | Plates | Last character | Second-last | Earlier | Drop plus a misread |
|---|---|---|---|---|---|
| stored, Sentinel-side misses | 6 | 3 | 2 | 0 | 1 |
| single crop, sandbox-blind-v1 | 4 | 2 | 2 | 0 | 0 |
| single crop, ownfeed-v1 | 64 | 2 | 8 | 40 | 14 |

Of the clean drops (one character gone, nothing else wrong), 5 of 5 stored and 4 of 4 single-crop drops on the sandbox are in the plate's last two positions, against 10 of 50 on our own feeds (synthetic plates painted on stock footage). The plate box does not explain it: its width over height has a median of 3.62 on the 5 one-line stored drops against 3.56 on the 79 one-line hits, so the detector did not stop short on these plates as a rule. The right end of real plates, as the shipped model reads them, is where characters are lost. There are too few drops here to say why.

The raw read of a dropped digit has a shape no Indian plate has: two series letters followed by three digits (`AA99AA999`). How often the shipped model's single read has that shape, and how often such a read is right (from `bench/ocr_ab.py`'s per-crop runs):

| Set | Reads | Dropped-digit shape | ...exact | ...passes today's gate |
|---|---|---|---|---|
| sandbox-blind-v1 | 120 | 4 | 1 | 4 |
| ownfeed-v1 | 5528 | 15 | 0 | 11 |

Across both, such reads are right on 1 of 19 (a genuine nine-character plate whose first number digit was also misread as a letter). On the Sentinel-side misses, the single-crop re-read has this shape on 3.

## 5. The fixes with the largest expected gain

Ranked by how many of the 30 misses each could remove. None is measured here, and none may be tuned on this set (it is test-only); each says how it would be measured.

1. **Settle the answer key** (measurement, not product; up to 13 of the 30 misses, 14 if the unclear one the blind reading gives to the stored read goes the same way). The split puts 13 misses on the reviewer, the blind second reading sides with the stored read on 13 of them, and 12 carry a signal that needs no judgement (section 1). Only a person may move the quoted 90/120: have a second team member read the 30 misses blind on the Plate review page (it records agreement when a sighting has two blind reviews) and freeze the adjudicated answers as `sandbox-blind-v2` beside v1 (never edit v1). On the review page, normalise the typed reading as the stored read is normalised before comparing, and warn when it is not a valid registration: that would have flagged 10 of the 13 at typing time without showing the reviewer Sentinel's read.
2. **Read Indian plates better** (model; up to 14 of the 30). The model makes 13 of the 14 Sentinel-side misreads again on the stored crop alone (12 identically), and the short reads the vote chose on the last one were the model's too, so the model, not the vote, is the main cause: 6 dropped characters (5 of the 5 clean drops in the last two positions, section 4), and 7 confusions of a digit for a digit or a letter for a letter (section 3), on yellow commercial plates with a thin typeface, blurred crops and the monochrome camera (section 1). The shipped model is a global one that lists no Indian region. The Indian-format fine-tune (synthetic plates from `bench/plategen.py`, never these crops) is the fix, adopted only through `bench/ocr_gates.md`, whose Gate 1 scores it on this set's crops against the baseline.
3. **Keep short reads out, and send low-confidence reads to the crop** (product; a few wrong sightings removed, and 11 of the 14 Sentinel-side misses flagged). Reject a raw read of shape `AA99AA999` in `worker.check_read` (as the not-a-plate rule rejects phone numbers), and choose the vote's length by summed confidence rather than by count. The stored crop's re-read has that shape on 3 of the 6 short stored reads (the others were read in a valid shape, which no rule can catch), and on 1 more the vote chose short reads over a right full-length one. On the per-crop runs the rule drops 18 wrong reads and 1 right one. A track whose every read was short is then not stored, so most of these become no sighting rather than an exact one. Until a better model ships, mark alerts and search results stored below 0.9, the review page's top band, as 'check the crop': 11 of the 14 Sentinel-side misses are below it, against 21 of the 90 hits (39 of 120 sightings flagged). The capture grade's low-confidence mark is at 0.6, which catches 3 of them. Confirm both on our own feeds with `scripts/anpr_eval.py` before shipping.

Not recommended from this set: a wider crop. The box is no shorter on the drops (section 4), and stored crops cannot test it.

## Caveats

- 120 plates in 55 groups, 3 cameras, one reviewer. Treat the rates per category as descriptive, and the AUC intervals as the guide to what is signal.
- The Sentinel/reviewer split is our AI assistant's reading of the crops, made with both readings in view. Its blind re-read (section 1) is a check, not a second reviewer: it is the same AI. A second blind person is what settles it.
- The blind re-read saw each crop at 150 px high beside a contrast-stretched copy. Where the loop had replayed a vehicle, its other passes on the sheets were in view too, as they were for the adjudication; the reviewer saw the review page's own view, one sighting at a time.
- Only stored sightings are here, so plates Sentinel never stored are not analysed.
- Hits are sightings where the reviewer and Sentinel agree; a plate both read the same wrong way would count as a hit.
- The stored crop is the track's best-confidence read, saved as JPEG 85; the stored read is a vote over the track's reads, whose raw text is not kept, so the raw shape of the stored read cannot be checked.
