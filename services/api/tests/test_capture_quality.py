"""Capture grades and camera tiers. Synthetic GJ99 plates drawn with OpenCV; no real registration."""
import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from sentinel_api import capture_quality as cq  # noqa: E402
from sentinel_api.camera_quality import MIN_CAPTURES, graded, recommendations, tier  # noqa: E402


def plate(w=520, h=112, two_line=False, text="GJ99AB1234", bg=210, ink=20):
    """A plate as a camera might see it head-on: light background, dark border and characters."""
    img = np.full((h, w, 3), bg, np.uint8)
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), (ink,) * 3, max(1, h // 40))
    lines = [text[:-4], text[-4:]] if two_line else [text]
    line_h = h / len(lines)
    for i, line in enumerate(lines):
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        scale = min(0.88 * w / tw, 0.62 * line_h / th)
        thick = max(1, round(scale * 2.2))
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        org = (int((w - tw) / 2), int(line_h * i + (line_h + th) / 2))
        cv2.putText(img, line, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (ink,) * 3, thick, cv2.LINE_AA)
    return img


def as_crop(p, surround=110):
    """Pad the plate exactly as worker.py does before it stores the crop: int(0.15 * h) on every side."""
    h, w = p.shape[:2]
    pad = int(h * cq.PAD)
    out = np.full((h + 2 * pad, w + 2 * pad, 3), surround, np.uint8)
    out[pad:pad + h, pad:pad + w] = p
    return out


def grade(p, conf=0.95, bbox=None):
    m = cq.assess(as_crop(p), bbox)
    return m, *cq.classify(m, conf)


# ------------------------------------------------------------------ one capture


def test_the_workers_padding_is_undone():
    """Every plate height a stream gives, not a sample: int() rounding makes some crop heights ambiguous."""
    wrong = [h for h in range(6, 260)
             if cq.plate_box(h + 2 * int(h * cq.PAD), 300 + 2 * int(h * cq.PAD))
             != (int(h * cq.PAD), int(h * cq.PAD), 300, h)]
    assert wrong == []


def test_the_stored_box_wins_and_a_plate_at_the_frame_edge_keeps_its_place():
    # plate 3 px from the top of the frame: the crop could only start at 0, so the plate sits 3 px down
    x, y, w, h = cq.plate_box(3 + 40 + 6, 200 + 12, bbox=[50, 3, 200, 40])
    assert (x, y, w, h) == (6, 3, 200, 40)


def test_a_large_sharp_plate_is_good():
    m, quality, reasons = grade(plate())
    assert (m["plate_w"], m["plate_h"], m["layout"], m["char_h"]) == (520, 112, "one-line", 78)
    assert not m["oblique"]
    assert (quality, reasons) == ("good", [])


def test_the_same_plate_50_px_wide_is_too_small():
    small = cv2.resize(plate(), (50, 11), interpolation=cv2.INTER_AREA)
    m, quality, reasons = grade(small)
    assert m["plate_w"] == 50
    assert quality == "poor" and "too_small" in reasons


def test_a_plate_under_100_px_is_small_not_too_small():
    m, quality, reasons = grade(cv2.resize(plate(), (90, 20), interpolation=cv2.INTER_AREA))
    assert "small" in reasons and "too_small" not in reasons


def test_a_blurred_plate_is_blurred():
    p = plate()
    m, quality, reasons = grade(cv2.GaussianBlur(p, (0, 0), 0.1 * p.shape[0]))
    assert "blurred" in reasons and quality in ("marginal", "poor")


def test_a_dark_plate_is_dark_and_poor():
    m, quality, reasons = grade((plate().astype(np.float32) * 0.08).astype(np.uint8))
    assert "dark" in reasons and "low_contrast" in reasons and quality == "poor"


def test_a_washed_out_plate_is_glare():
    m, quality, reasons = grade(np.clip(plate().astype(np.int16) + 200, 0, 255).astype(np.uint8))
    assert "glare" in reasons and "dark" not in reasons


def test_two_line_layout_is_detected():
    m, quality, reasons = grade(plate(340, 200, two_line=True))
    assert m["layout"] == "two-line" and m["char_h"] == 70
    assert reasons == ["two_line"] and quality == "marginal"


def test_a_squashed_plate_is_oblique():
    m, quality, reasons = grade(cv2.resize(plate(), (520, 50), interpolation=cv2.INTER_AREA))
    assert m["oblique"] and "oblique" in reasons


def test_a_low_confidence_read_makes_a_good_crop_marginal():
    _, quality, reasons = grade(plate(), conf=0.3)
    assert (quality, reasons) == ("marginal", ["low_confidence"])


def test_sharpness_does_not_reward_size():
    """Measured at the reader's input height: the same plate drawn twice as large is not twice as sharp."""
    a, b = cq.assess(as_crop(plate(260, 56)))["sharpness"], cq.assess(as_crop(plate(520, 112)))["sharpness"]
    assert 0.5 < a / b < 2


def test_an_unreadable_file_is_not_graded(tmp_path):
    bad = tmp_path / "x.jpg"
    bad.write_bytes(b"not a jpeg")
    assert cq.grade_file(bad) is None


def test_a_crop_on_disk_is_graded(tmp_path):
    f = tmp_path / "x.jpg"
    cv2.imwrite(str(f), as_crop(plate()), [cv2.IMWRITE_JPEG_QUALITY, 85])
    g = cq.grade_file(f, ocr_conf=0.95)
    assert g["quality"] == "good" and g["plate_w"] == 520


# ------------------------------------------------------------------ one camera


def cam(**kw):
    row = {"captures": 100, "good": 80, "median_plate_w": 140, "median_char_h": 28, "reasons": {},
           "frames_analysed": 5000, "anpr_viable": False}
    return row | kw


def kinds(recs, kind):
    return [r["text"] for r in recs if r["kind"] == kind]


def test_mostly_good_and_wide_is_tier_a():
    row = cam()
    assert tier(row)[0] == "A"
    assert kinds(recommendations(row, "A"), "config") == ["Mark this camera ANPR-viable and analyse it continuously"]
    assert kinds(recommendations(cam(anpr_viable=True), "A"), "config") == ["Keep it ANPR-viable and analysed continuously"]


def test_too_few_captures_cannot_make_tier_a():
    assert tier(cam(captures=MIN_CAPTURES - 1, good=MIN_CAPTURES - 1))[0] == "B"


def test_small_plates_are_tier_c_with_zoom_advice():
    row = cam(good=5, median_plate_w=50, median_char_h=8, reasons={"too_small": 90})
    t, why = tier(row)
    recs = recommendations(row, t)
    assert t == "C"
    assert why == "5% of 100 captures good"
    assert kinds(recs, "camera") == ["Zoom in or move closer: plates need about 100-150 px across "
                                     "(now median 50 px; 90% of captures under size)"]
    assert kinds(recs, "config") == ["Use for counts and viewing only; do not rely on plates"]
    # the registry's flag does not outrank the captures, and the advice says they disagree
    assert kinds(recommendations(row | {"anpr_viable": True}, t), "config") == [
        "Marked ANPR-viable, but its captures do not bear that out: use for counts and viewing only until they do"]


def test_tiny_characters_alone_make_tier_c():
    assert tier(cam(good=50, median_char_h=9))[0] == "C"


def test_in_between_is_tier_b_with_one_recommendation_per_dominant_problem():
    row = cam(good=40, median_plate_w=90, median_char_h=14,
              reasons={"small": 60, "blurred": 30, "dark": 26, "glare": 10, "oblique": 25})
    t, _ = tier(row)
    camera = kinds(recommendations(row, t), "camera")
    assert t == "B"
    assert camera == ["Zoom in or move closer: plates need about 100-150 px across "
                      "(now median 90 px; 60% of captures under size)",
                      "Faster shutter (1/1000 s or less), higher bitrate, check focus",
                      "Add 850 nm infrared or light the lane; night plates are too dark",
                      "Re-aim to face the traffic within about 30 degrees"]     # glare on 10% is not dominant
    assert kinds(recommendations(row, t), "config") == []


def test_flat_plates_get_light_advice_once():
    flat = "Plates come out flat: turn WDR off and light the plate with pulsed infrared"
    dark = "Add 850 nm infrared or light the lane; night plates are too dark"
    assert kinds(recommendations(cam(reasons={"low_contrast": 40}), "B"), "camera") == [flat]
    # a dark plate is a flat one too: the dark advice already covers the light
    assert kinds(recommendations(cam(reasons={"low_contrast": 40, "dark": 40}), "B"), "camera") == [dark]


def test_no_plate_read_is_tier_c():
    row = cam(captures=0, good=0, median_plate_w=None, median_char_h=None)
    assert tier(row) == ("C", "no plate read") and graded(row)
    assert kinds(recommendations(row, "C"), "config") == ["Use for counts and viewing only; do not rely on plates"]


def test_a_camera_nobody_analysed_is_not_called_counts_only():
    idle = cam(captures=0, good=0, median_plate_w=None, median_char_h=None, frames_analysed=0, sightings=0)
    assert tier(idle) == ("C", "not analysed in this window") and not graded(idle)
    assert recommendations(idle, "C") == [{"kind": "config",
                                          "text": "Not analysed in this window: run a worker on it to grade it"}]


def test_captures_reviewed_as_not_plates_do_not_rate_the_camera():
    # the report leaves them out of captures and reasons; what is left is a camera that read no plate
    hoarding = cam(captures=0, good=0, median_plate_w=None, median_char_h=None, frames_analysed=0,
                   sightings=24, not_plates=24)
    assert tier(hoarding) == ("C", "its captures were reviewed as not plates") and graded(hoarding)
    assert recommendations(hoarding, "C") == [{"kind": "config",
                                              "text": "Use for counts and viewing only; do not rely on plates"}]


def test_reads_without_a_crop_are_not_graded():
    bare = cam(captures=0, good=0, median_plate_w=None, median_char_h=None, frames_analysed=0, sightings=3)
    assert tier(bare) == ("C", "its reads have no crop to grade") and not graded(bare)
    assert recommendations(bare, "C") == [{"kind": "config",
                                          "text": "Its reads carry no crop: keep crops on (SAVE_CROPS) to grade it"}]


def test_one_capture_says_it_is_one():
    assert tier(cam(captures=1, good=0, median_plate_w=54, median_char_h=11)) == ("C", "0% of 1 capture good")


def test_good_crops_read_wrong_blame_the_reader():
    retrain = "Crops are good but reads are wrong: retrain the reader with reviewed plates"
    assert retrain in kinds(recommendations(cam(good_reviewed=20, good_exact=12), "A"), "model")
    assert kinds(recommendations(cam(good_reviewed=20, good_exact=19), "A"), "model") == []
    assert kinds(recommendations(cam(good_reviewed=5, good_exact=0), "A"), "model") == []    # too few reviews
    # no graded reviews yet: a mostly-good camera falls back to all its blind reviews
    assert retrain in kinds(recommendations(cam(reviewed_blind=30, blind_exact=15), "A"), "model")


def test_two_line_plates_read_badly_ask_for_two_line_handling():
    two = "Two-line plates: add two-line handling"
    base = cam(good=50, median_plate_w=110, median_char_h=20, two_line=40)
    assert two in kinds(recommendations(base | {"two_line_reviewed": 10, "two_line_exact": 5}, "B"), "model")
    assert two not in kinds(recommendations(base | {"two_line_reviewed": 10, "two_line_exact": 10}, "B"), "model")
    assert two in kinds(recommendations(base | {"two_line_low_conf": 25}, "B"), "model")
    assert two not in kinds(recommendations(base | {"two_line_low_conf": 5}, "B"), "model")
    assert two not in kinds(recommendations(cam(two_line=10, two_line_low_conf=10), "A"), "model")   # not common
