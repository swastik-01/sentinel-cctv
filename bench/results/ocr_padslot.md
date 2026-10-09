# OCR confidence with the first pad slot

Generated 2026-09-26 15:41 IST by `bench/ocr_padslot.py`: each crop read once by the shipped model through the product's reader, CPU only. *Shipped*: the weakest character's probability over the text's slots (ocr.py). *With pad slot*: the lower of that and the probability of the first empty slot. Only reads that pass the worker gate are counted. Counts and rates only.

## ownfeed-v1

5528 crops (AMD-TRAF-001/002 crops, synthetic plates painted on stock footage); 5512 pass the gate.

| Confidence | Band | Reads in band | Exact in band | Exact below band |
|---|---|---|---|---|
| shipped | >= 0.7 | 4631 | 4546/4631 = 98.2% | 761/881 = 86.4% |
| shipped | >= 0.9 | 3206 | 3178/3206 = 99.1% | 2129/2306 = 92.3% |
| with pad slot | >= 0.7 | 4627 | 4546/4627 = 98.2% | 761/885 = 86.0% |
| with pad slot | >= 0.9 | 3202 | 3178/3202 = 99.3% | 2129/2310 = 92.2% |

Reads shorter than the true plate: 51; at >= 0.9 shipped 12, with pad slot 8. Reads that leave the 0.9 band when the pad slot counts: 4, exact among them 0.

## sandbox-blind-v1

120 crops (real sandbox plates read blind by a team member (test only)); 119 pass the gate.

| Confidence | Band | Reads in band | Exact in band | Exact below band |
|---|---|---|---|---|
| shipped | >= 0.7 | 96 | 77/96 = 80.2% | 11/23 = 47.8% |
| shipped | >= 0.9 | 64 | 54/64 = 84.4% | 34/55 = 61.8% |
| with pad slot | >= 0.7 | 95 | 77/95 = 81.1% | 11/24 = 45.8% |
| with pad slot | >= 0.9 | 64 | 54/64 = 84.4% | 34/55 = 61.8% |

Reads shorter than the true plate: 7; at >= 0.9 shipped 0, with pad slot 0. Reads that leave the 0.9 band when the pad slot counts: 0, exact among them 0.
