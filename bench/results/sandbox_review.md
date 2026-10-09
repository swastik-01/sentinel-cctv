# Plates stored by Sentinel, checked by people on the Plate review page

Generated 2026-09-26 13:19 IST by `bench/sandbox_eye.py score --from-db` from 144 review(s) in the database (cameras matching `^CAM[0-9]{2}$`).

Method: a reviewer opens a stored sighting's evidence crop (the image of the best read) in the control room. **Blind**: the page shows only the crop; the reviewer types the plate they see (`?` unreadable, `-` not a plate) and the server derives the verdict by comparing that reading with the stored read (exact, one character off, wrong). **Verify**: the page shows the stored read and its confidence, and the reviewer confirms or corrects it. The two are never mixed: only blind numbers are an independent measure. The readings hold real registrations and stay in the database; only totals are published here.

## Blind

144 review(s) of 144 sighting(s) by Platform Administrator (`admin`, 144).

| Verdict | Reviews |
|---|---|
| exact | 90 |
| one off | 17 |
| wrong | 13 |
| not a plate | 24 |
| unreadable | 0 |

**Of the reviews that were vehicle plates a person could read: exact 90/120 = 75.0%; within one character 107/120 = 89.2%.**

| Camera | exact | one off | wrong | not a plate | unreadable |
|---|---|---|---|---|---|
| CAM05 | 0 | 0 | 0 | 24 | 0 |
| CAM06 | 71 | 12 | 9 | 0 | 0 |
| CAM07 | 19 | 4 | 4 | 0 | 0 |
| CAM12 | 0 | 1 | 0 | 0 | 0 |

| OCR confidence | plates | exact | within one |
|---|---|---|---|
| 0.35-0.5 | 1 | 0/1 = 0.0% | 0/1 = 0.0% |
| 0.5-0.7 | 18 | 8/18 = 44.4% | 14/18 = 77.8% |
| 0.7-0.9 | 20 | 13/20 = 65.0% | 14/20 = 70.0% |
| >=0.9 | 81 | 69/81 = 85.2% | 79/81 = 97.5% |

Agreement: 0 sighting(s) checked blind by two or more reviewers; 0 with the same verdict, 0 with the same reading.

## Verify

No verify reviews yet.

Precision only: a review judges a plate Sentinel stored. Plates on screen that were never stored (capture rate) are not counted here.
