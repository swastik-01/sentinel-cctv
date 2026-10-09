"""Confidence marking (bench/pipeline_gates.md, G3): a stored read below 0.9, or a watchlist alert raised on a
one-character match, is marked "check the crop" wherever an operator sees it. Nothing is suppressed and no alert
rule changes: a mark costs the operator one look at the evidence crop.

The threshold is the Plate review page's band, fixed on 26 Sep: on the 120 blind-checked sandbox plates, reads at
or above 0.9 were 69 of 81 exact and the rest 21 of 39 (bench/results/capture_quality.md). `ocr_conf` is a REAL
column, so 0.9 comes back as 0.8999999761...: the comparison rounds to 3 decimals, as the review page's SQL
compares against real '0.9'.
"""
from __future__ import annotations

THRESHOLD = 0.9


def low_confidence(ocr_conf: float | None) -> bool:
    """True when a stored read's confidence is below the band (rounded as the REAL column stores it)."""
    return ocr_conf is not None and round(ocr_conf, 3) < THRESHOLD


def needs_review(ocr_conf: float | None, exact_match: bool = True) -> bool:
    """A sighting below the band, or an alert raised on a one-character match, needs the crop looked at."""
    return low_confidence(ocr_conf) or not exact_match


def reason(ocr_conf: float | None, exact_match: bool = True) -> str | None:
    """Why it is marked, for the operator; None when it is not."""
    parts = []
    if low_confidence(ocr_conf):
        parts.append(f"read confidence below {THRESHOLD:g}")
    if not exact_match:
        parts.append("one character off the watchlist plate")
    return "; ".join(parts) or None
