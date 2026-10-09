"""Plate review verdicts: the reviewer's reading against the stored read. Synthetic GJ99 plates only."""
import pytest

from sentinel_api.review import correction, edits, reading, verdict

STORED = "GJ99AB1234"


def test_same_plate_is_exact():
    assert verdict("GJ99AB1234", STORED) == "exact"


def test_spacing_case_and_punctuation_do_not_count():
    assert verdict("gj 99 ab 1234", STORED) == "exact"
    assert verdict(" GJ-99-AB-1234 ", STORED) == "exact"
    assert verdict("gj99.ab.1234", STORED) == "exact"


@pytest.mark.parametrize("seen", ["GJ99AB1235",    # one character different
                                  "GJ99A1234",     # one missing
                                  "GJ99ABC1234"])  # one extra
def test_one_character_off(seen):
    assert verdict(seen, STORED) == "one_off"


@pytest.mark.parametrize("seen", ["GJ99AB1256", "GJ99CD1234", "GJ99XY9876", "GJ9"])
def test_two_or_more_off_is_wrong(seen):
    assert verdict(seen, STORED) == "wrong"


def test_question_mark_is_unreadable_and_dash_is_not_a_plate():
    assert verdict("?", STORED) == "unreadable"
    assert verdict(" ? ", STORED) == "unreadable"
    assert verdict("-", STORED) == "not_a_plate"
    assert verdict(" - ", STORED) == "not_a_plate"


def test_reading_is_stored_normalised():
    assert reading(" gj 99 ab 1234 ") == "GJ99AB1234"
    assert reading("?") == "?" and reading("-") == "-"
    assert reading("...") == ""


def test_reading_is_what_was_typed_not_repaired():
    # a digit typed where a series letter goes is the reviewer's reading, not an OCR slip to repair
    assert reading("GJ99A21234") == "GJ99A21234"
    assert verdict("GJ99A21234", "GJ99AZ1234") == "one_off"


def test_a_reading_without_letters_is_not_a_plate():
    assert verdict("75000 12345", "GJ99AB1234") == "not_a_plate"      # a made-up phone number


def test_edit_distance():
    assert edits("GJ99AB1234", "GJ99AB1234") == 0
    assert edits("GJ99AB1234", "GJ99AB1244") == 1
    assert edits("GJ99AB1234", "GJ99B1234") == 1
    assert edits("", "GJ99") == 4


def test_a_change_is_graded_like_a_first_reading():
    assert correction("GJ99AB1784", "wrong", "gj 99 ab 1234", STORED) == ("GJ99AB1234", "exact")
    assert correction("GJ99AB1234", "exact", "?", STORED) == ("?", "unreadable")
    assert correction("?", "unreadable", "GJ99AB1235", STORED) == ("GJ99AB1235", "one_off")


def test_the_first_reading_again_takes_a_change_back():
    assert correction("GJ99AB1235", "one_off", "GJ-99-AB-1235", STORED) is None


def test_a_confirmed_verify_review_changes_only_with_its_verdict():
    assert correction(None, "exact", "GJ99AB1234", STORED) is None      # confirmed, and the reading agrees
    assert correction(None, "exact", "-", STORED) == ("-", "not_a_plate")
