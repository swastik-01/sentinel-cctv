"""Per-camera plate-reading grade: a tier and recommendations from the grades of its captures.

A camera is tiered by what it captures (capture_quality.py), so a department knows which views can carry
ANPR and what would make the others better: the camera suitability report of docs/commercial-anpr.md
(recommendation 8). Pure functions over one row of the camera-quality report; the SQL is in
routers/quality.py.

Tiers:
  A  reads plates:  at least 60% of captures good and a median plate at least 100 px across (Axis:
                    100-150 px), from at least MIN_CAPTURES captures
  C  counts only:   under 20% good, or median characters under 10 px (Adaptive Recognition's minimum),
                    or no plate read at all
  B  marginal:      everything between

Captures a reviewer marked as not a plate (a hoarding, a sign) are left out before any of this: the grade
measures the image, not what is in it, so a sharp hoarding would otherwise make a camera look good.
"""
from __future__ import annotations

A_GOOD, A_WIDTH = 0.6, 100
C_GOOD, C_CHAR = 0.2, 10
MIN_CAPTURES = 20           # fewer captures than this cannot rate a camera A
DOMINANT = 0.25             # a problem on a quarter of the captures or more gets its recommendation
# NHAI's ATMS specification asks >= 90% (docs/commercial-anpr.md): below that on crops graded good, the
# camera did its part and the reader did not.
READS_OK = 0.9
MIN_REVIEWED = 10           # blind reviews needed before the reader is blamed
MIN_TWO_LINE_REVIEWED = 5

# Camera advice, with its source: docs/commercial-anpr.md unless marked.
CAMERA_ADVICE = {
    # Axis: 100-150 px across the plate; Plate Recognizer: about 100 px. The share is what triggers it: the
    # median alone can sit inside 100-150 px while a third of the plates are too small.
    "size": "Zoom in or move closer: plates need about 100-150 px across (now median {w} px; {s}% of captures under size)",
    # Axis: 0.8-4.5 ms at 130 km/h by angle; a 1/50 s exposure smears a car at 60 km/h over five characters
    "blurred": "Faster shutter (1/1000 s or less), higher bitrate, check focus",
    # 850 nm gives the best light output and sensor sensitivity; pulsed IR in step with the shutter
    "dark": "Add 850 nm infrared or light the lane; night plates are too dark",
    # Axis: switch WDR off for plates; pulsed IR suppresses headlights and sun
    "glare": "Lower exposure or turn WDR off for the plate area",
    # Axis: at least 75 px for full-contrast characters, WDR off; pulsed IR keeps the plate bright against
    # its surroundings. Given only when dark or glare advice is not already there: those cover the light.
    "low_contrast": "Plates come out flat: turn WDR off and light the plate with pulsed infrared",
    # Axis: keep the total angle under 30 degrees
    "oblique": "Re-aim to face the traffic within about 30 degrees",
}


def graded(row: dict) -> bool:
    """Is the tier a finding about the camera? Not when nothing in the window could be graded: no worker looked
    at it, or its plate reads carry no crop. The report still gives those C (the default) and says why."""
    if row.get("captures"):
        return True
    reads = (row.get("sightings") or 0) - (row.get("not_plates") or 0)
    return reads <= 0 and bool(row.get("frames_analysed") or row.get("not_plates"))


def tier(row: dict) -> tuple[str, str]:
    """(tier, why) for one camera row: captures, good, median_plate_w, median_char_h."""
    n = row.get("captures") or 0
    if not n:
        if (row.get("sightings") or 0) > (row.get("not_plates") or 0):
            return "C", "its reads have no crop to grade"
        if row.get("not_plates"):
            return "C", "its captures were reviewed as not plates"
        return "C", "no plate read" if row.get("frames_analysed") else "not analysed in this window"
    good = (row.get("good") or 0) / n
    width, char = row.get("median_plate_w") or 0, row.get("median_char_h") or 0
    if good < C_GOOD:
        return "C", f"{good:.0%} of {n} capture{'s' if n != 1 else ''} good"
    if char < C_CHAR:
        return "C", f"median characters {char:g} px"
    if good >= A_GOOD and width >= A_WIDTH:
        if n < MIN_CAPTURES:
            return "B", f"{good:.0%} good but only {n} captures"
        return "A", f"{good:.0%} good, median plate {width:g} px"
    return "B", f"{good:.0%} good, median plate {width:g} px"


def _rate(ok: int | None, n: int | None, at_least: int) -> float | None:
    return ok / n if n and n >= at_least and ok is not None else None


def recommendations(row: dict, tier_: str) -> list[dict]:
    """What would make this camera read plates better, as [{kind: camera | model | config, text}].
    Camera: a capture problem on at least DOMINANT of the captures. Model: crops good but reads wrong, or
    two-line plates common and read badly. Config: how to use the camera given its tier."""
    recs: list[dict] = []
    n = row.get("captures") or 0
    reasons = row.get("reasons") or {}

    def share(*keys: str) -> float:
        return sum(reasons.get(k, 0) for k in keys) / n if n else 0.0

    if n:
        if share("too_small", "small") >= DOMINANT:
            recs.append({"kind": "camera", "text": CAMERA_ADVICE["size"].format(
                w=round(row.get("median_plate_w") or 0), s=round(100 * share("too_small", "small")))})
        for reason in ("blurred", "dark", "glare", "oblique"):
            if share(reason) >= DOMINANT:
                recs.append({"kind": "camera", "text": CAMERA_ADVICE[reason]})
        if share("low_contrast") >= DOMINANT and share("dark") < DOMINANT and share("glare") < DOMINANT:
            recs.append({"kind": "camera", "text": CAMERA_ADVICE["low_contrast"]})

        good_reads = _rate(row.get("good_exact"), row.get("good_reviewed"), MIN_REVIEWED)
        if good_reads is None and (row.get("good") or 0) / n >= A_GOOD:
            good_reads = _rate(row.get("blind_exact"), row.get("reviewed_blind"), MIN_REVIEWED)
        if good_reads is not None and good_reads < READS_OK:
            recs.append({"kind": "model", "text": "Crops are good but reads are wrong: retrain the reader with reviewed plates"})

        two_line = row.get("two_line") or 0
        if two_line / n >= DOMINANT:
            reads = _rate(row.get("two_line_exact"), row.get("two_line_reviewed"), MIN_TWO_LINE_REVIEWED)
            unsure = (row.get("two_line_low_conf") or 0) / two_line
            if (reads is not None and reads < READS_OK) or (reads is None and unsure >= 0.5):
                recs.append({"kind": "model", "text": "Two-line plates: add two-line handling"})
    elif not graded(row):
        recs.append({"kind": "config", "text": "Its reads carry no crop: keep crops on (SAVE_CROPS) to grade it"
                     if row.get("sightings") else "Not analysed in this window: run a worker on it to grade it"})

    if tier_ == "A":
        recs.append({"kind": "config", "text": "Keep it ANPR-viable and analysed continuously" if row.get("anpr_viable")
                     else "Mark this camera ANPR-viable and analyse it continuously"})
    elif tier_ == "C" and graded(row):
        # the registry's flag is somebody's claim; the captures are the evidence, so say when they disagree
        recs.append({"kind": "config", "text": "Marked ANPR-viable, but its captures do not bear that out: use for counts "
                     "and viewing only until they do" if row.get("anpr_viable")
                     else "Use for counts and viewing only; do not rely on plates"})
    return recs
