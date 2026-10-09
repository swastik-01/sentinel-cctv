"""Should the OCR confidence also ask "is the plate really this short?"

Why: seven stored sandbox plates were one character short (pipeline_diag.md). ocr.py's confidence is the weakest
character's probability over the slots that hold text; the model's 10 slots also give a probability for the first
empty (pad) slot, which is ignored. If the model is unsure whether a character sits there, counting that slot would
pull a short read out of the confident band, which is what the review band (pipeline_review.md, rank 4) relies on.

Each crop of the frozen sets is read once through the product's reader (ocr_ab.load_model: ocr.py's preprocessing),
then normalise_plate and the worker gate (confidence >= 0.35, looks_like_indian_plate); the two confidences are
compared at 0.7 and 0.9. Nothing is tuned here: the real set only reports what the idea would do. CPU only, 2 threads.
Counts and rates only.

    PYTHONUTF8=1 uv run --no-sync python bench/ocr_padslot.py [--out bench/results/ocr_padslot.md]
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # a live worker owns the GPU
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import csv  # noqa: E402
import importlib.util  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from sentinel_common import looks_like_indian_plate, normalise_plate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
SETS = {"ownfeed-v1": "AMD-TRAF-001/002 crops, synthetic plates painted on stock footage",
        "sandbox-blind-v1": "real sandbox plates read blind by a team member (test only)"}
MIN_CONF = 0.35
_spec = importlib.util.spec_from_file_location("ocr_ab", ROOT / "bench" / "ocr_ab.py")
ocr_ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ocr_ab)


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "ocr_padslot.md"))
    a = ap.parse_args()
    ocr, _ = ocr_ab.load_model("cct-xs-v2-global-model", None, 2)
    L = ["# OCR confidence with the first pad slot", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/ocr_padslot.py`: each crop read once by the "
         "shipped model through the product's reader, CPU only. *Shipped*: the weakest character's probability over "
         "the text's slots (ocr.py). *With pad slot*: the lower of that and the probability of the first empty slot. "
         "Only reads that pass the worker gate are counted. Counts and rates only.", ""]
    for name, what in SETS.items():
        d = ROOT / "data" / "ocr-eval" / name
        man = list(csv.DictReader(open(d / "manifest.csv", encoding="utf-8")))
        recs = []
        for i in range(0, len(man), 8):
            chunk = [(r, ocr._prep(cv2.imread(str(d / f"{r['id']}.jpg")))) for r in man[i:i + 8]]
            chunk = [(r, im) for r, im in chunk if im is not None]
            for (r, _), p in zip(chunk, ocr.rec.run([im for _, im in chunk], return_confidence=True)):
                text = str(p.plate).replace("_", "").strip()
                probs = np.asarray(p.char_probs, dtype=float).ravel()
                shipped = float(probs[:max(1, len(text))].min())
                norm = normalise_plate(text)
                if shipped < MIN_CONF or not looks_like_indian_plate(norm):
                    continue
                pad = float(probs[len(text)]) if len(text) < probs.size else 1.0
                recs.append({"exact": norm == r["true_plate"], "short": len(norm) < len(r["true_plate"]),
                             "shipped": shipped, "pad": min(shipped, pad)})
        L += [f"## {name}", "", f"{len(man)} crops ({what}); {len(recs)} pass the gate.", "",
              "| Confidence | Band | Reads in band | Exact in band | Exact below band |", "|---|---|---|---|---|"]
        for key, label in (("shipped", "shipped"), ("pad", "with pad slot")):
            for t in (0.7, 0.9):
                hi = [x for x in recs if x[key] >= t]
                lo = [x for x in recs if x[key] < t]
                L.append(f"| {label} | >= {t:g} | {len(hi)} | {pct(sum(x['exact'] for x in hi), len(hi))} | "
                         f"{pct(sum(x['exact'] for x in lo), len(lo))} |")
        short = [x for x in recs if x["short"]]
        moved = [x for x in recs if x["shipped"] >= 0.9 > x["pad"]]
        L += ["", f"Reads shorter than the true plate: {len(short)}; at >= 0.9 shipped {sum(x['shipped'] >= 0.9 for x in short)}, "
              f"with pad slot {sum(x['pad'] >= 0.9 for x in short)}. Reads that leave the 0.9 band when the pad slot "
              f"counts: {len(moved)}, exact among them {sum(x['exact'] for x in moved)}.", ""]
    text = "\n".join(L)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
