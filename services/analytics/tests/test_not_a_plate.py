"""The digit-repair rule (bench/plate_gate_gates.md, Stage A): a read that fits a plate layout only after two or more
digits were turned into letters is dropped before the tracker. Synthetic plates only: GJ99 is not an RTO, and the BH
and phone digits are made up."""
from sentinel_analytics.config import Settings
from sentinel_analytics.worker import check_read
from sentinel_common import letters_from_digits, looks_like_indian_plate, normalise_plate

PHONE = "75000 12345"      # a mobile number as a hoarding shows it: TS 00 OI 2345 once 7,5,0,1 become letters


def verdict(text: str, conf: float = 0.9) -> str:
    return check_read(text, conf, min_conf=0.35, max_from_digits=Settings(_env_file=None).max_letters_from_digits)


def test_a_phone_number_passes_the_old_gate_but_is_dropped():
    assert looks_like_indian_plate(normalise_plate(PHONE))
    assert letters_from_digits(PHONE) == 4
    assert verdict(PHONE) == "digits"


def test_an_exact_gj_plate_is_kept():
    assert letters_from_digits("GJ99AB1234") == 0
    assert verdict("GJ99AB1234") == "ok"


def test_one_state_letter_read_as_a_digit_is_kept():
    assert normalise_plate("6J99AB1234") == "GJ99AB1234"
    assert letters_from_digits("6J99AB1234") == 1
    assert verdict("6J99AB1234") == "ok"


def test_bh_plates_are_kept():
    assert letters_from_digits("25BH4821KX") == 0 and verdict("25BH4821KX") == "ok"
    for misread, plate in (("258H4821KX", "25BH4821KX"), ("25BH4821K2", "25BH4821KZ")):   # B read as 8; Z as 2
        assert normalise_plate(misread) == plate
        assert letters_from_digits(misread) == 1
        assert verdict(misread) == "ok"


def test_both_state_letters_from_digits_are_dropped():
    assert normalise_plate("6499AB1234") == "GA99AB1234"
    assert letters_from_digits("6499AB1234") == 2
    assert verdict("6499AB1234") == "digits"


def test_known_cost_two_series_letters_read_as_digits_are_dropped():
    # A real plate lost: both series letters misread as digits. On our own feeds this cost 4 of 5,307 exact reads.
    assert normalise_plate("GJ99851234") == "GJ99BS1234"
    assert letters_from_digits("GJ99851234") == 2
    assert verdict("GJ99851234") == "digits"


def test_only_digits_made_letters_count():
    assert letters_from_digits("GJ99AB1Z34") == 0      # a letter made a digit (Z -> 2 in the number)
    assert normalise_plate("CJ99AB1234") == "GJ99AB1234"
    assert letters_from_digits("CJ99AB1234") == 0      # the look-alike state fix swaps a letter for a letter
    assert letters_from_digits("") == 0 and letters_from_digits("HELLO") == 0


def test_the_existing_gate_comes_first():
    assert verdict(PHONE, conf=0.2) == "gate"          # too weak: never counted as a rule drop
    assert verdict("") == "gate"
    assert verdict("GJ99AB") == "gate"


def test_the_setting_turns_the_rule_off():
    assert Settings(_env_file=None).max_letters_from_digits == 1
    assert check_read(PHONE, 0.9, min_conf=0.35, max_from_digits=99) == "ok"
