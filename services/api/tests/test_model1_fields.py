"""The Model 1 maintenance fields (maintenance state, installation year, AMC or warranty expiry), the CSV row
coercion that feeds them, and the alert tags of Model 2: every bad value is a clear refusal, never a 500."""
from datetime import date

import pytest
from pydantic import ValidationError

from sentinel_api.cameras_repo import validate_fields
from sentinel_api.routers.cameras import _coerce_csv_row
from sentinel_api.schemas import AlertTags, CameraIn, CameraPatch


def csv_row(**over):
    base = {"camera_code": "CAM01", "name": "Gate", "department_code": "POL", "lat": "23.2", "lon": "72.6"}
    return _coerce_csv_row({**base, **over})


# --- CSV coercion -------------------------------------------------------------------------------------------------

def test_a_plain_row_coerces():
    r = csv_row(fps="25", retention_days="30.0", install_year="2019", anpr_viable="Yes", analytics_enabled="")
    assert (r["fps"], r["retention_days"], r["install_year"]) == (25, 30, 2019)
    assert r["anpr_viable"] is True and r["analytics_enabled"] is None
    assert r["lat"] == pytest.approx(23.2)


@pytest.mark.parametrize("field,value", [("fps", "241"), ("fps", "-1"), ("retention_days", "3651"),
                                         ("bearing_deg", "360"), ("lat", "91"), ("lon", "-181")])
def test_out_of_range_numbers_are_refused_with_the_field_named(field, value):
    with pytest.raises(ValueError, match=field):
        csv_row(**{field: value})


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e400", "NaN"])
@pytest.mark.parametrize("field", ["fps", "lat", "install_year"])
def test_non_finite_numbers_are_a_value_error_not_an_overflow(field, value):
    with pytest.raises(ValueError, match=field):
        csv_row(**{field: value})


def test_text_in_a_number_column_is_a_value_error():
    with pytest.raises(ValueError):
        csv_row(fps="twenty")


def test_blank_cells_become_none():
    r = csv_row(fps="", vendor="  ", install_year="", amc_expiry="")
    assert r["fps"] is None and r["vendor"] is None and r["install_year"] is None and r["amc_expiry"] is None


@pytest.mark.parametrize("typed,stored", [("Under maintenance", "under_maintenance"), ("FAULTY", "faulty"),
                                          ("in_service", "in_service"), (" decommissioned ", "decommissioned")])
def test_maintenance_is_read_as_a_person_types_it(typed, stored):
    assert csv_row(maintenance=typed)["maintenance"] == stored


# --- validate_fields (every write path) ---------------------------------------------------------------------------

def test_maintenance_must_be_a_known_state():
    validate_fields({"camera_code": "CAM01", "maintenance": "faulty"})
    with pytest.raises(ValueError, match="maintenance"):
        validate_fields({"camera_code": "CAM01", "maintenance": "broken"})


def test_amc_expiry_is_parsed_from_iso_text():
    row = {"camera_code": "CAM01", "amc_expiry": "2027-03-31"}
    validate_fields(row)
    assert row["amc_expiry"] == date(2027, 3, 31)
    for bad in ("31/03/2027", "2027-02-30", "soon"):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            validate_fields({"camera_code": "CAM01", "amc_expiry": bad})


@pytest.mark.parametrize("year", [1989, 2101, -5])
def test_install_year_is_bounded(year):
    with pytest.raises(ValueError, match="install_year"):
        validate_fields({"camera_code": "CAM01", "install_year": year})


# --- the API bodies ----------------------------------------------------------------------------------------------

def test_camera_in_takes_the_maintenance_fields():
    c = CameraIn(camera_code="CAM01", name="Gate", department_code="POL", maintenance="under_maintenance",
                 install_year=2018, amc_expiry="2026-12-31", maintenance_note="lens replaced")
    assert c.amc_expiry == date(2026, 12, 31)


@pytest.mark.parametrize("over", [{"maintenance": "broken"}, {"install_year": 1900}, {"amc_expiry": "31-12-2026"},
                                  {"maintenance_note": "x" * 501}, {"fps": 999}, {"retention_days": -1},
                                  {"lat": float("nan")}, {"lon": float("inf")}, {"bearing_deg": 360},
                                  {"name": ""}, {"name": "x" * 201}])
def test_a_bad_patch_is_a_validation_error(over):
    with pytest.raises(ValidationError):
        CameraPatch(**over)


def test_a_patch_can_send_explicit_nulls_to_clear():
    p = CameraPatch(install_year=None, amc_expiry=None)
    assert p.model_dump(exclude_unset=True) == {"install_year": None, "amc_expiry": None}


# --- alert tags --------------------------------------------------------------------------------------------------

def test_tags_are_trimmed_and_deduplicated_ignoring_case():
    assert AlertTags(tags=["  Intercepted ", "intercepted", "case  #4471", ""]).tags == ["Intercepted", "case #4471"]


def test_gujarati_and_hindi_tags_are_accepted():
    assert AlertTags(tags=["અટકાવેલ", "रोका गया"]).tags == ["અટકાવેલ", "रोका गया"]


@pytest.mark.parametrize("tag", ["<script>alert(1)</script>", "a" * 33, "drop;table", "x\x00y", "quote\"s", "a{b}"])
def test_a_bad_tag_is_refused(tag):
    with pytest.raises(ValidationError):
        AlertTags(tags=[tag])


def test_at_most_ten_tags():
    AlertTags(tags=[f"t{i}" for i in range(10)])
    with pytest.raises(ValidationError):
        AlertTags(tags=[f"t{i}" for i in range(11)])


def test_an_empty_list_clears_the_tags():
    assert AlertTags(tags=[]).tags == []


# --- search text in LIKE patterns ---------------------------------------------------------------------------------

def test_like_wildcards_in_search_text_match_literally():
    from sentinel_api.db import like_escape
    assert like_escape("50%_off") == r"50\%\_off"
    assert like_escape(r"C:\cam") == r"C:\\cam"
    assert like_escape("GNR-POL") == "GNR-POL"
