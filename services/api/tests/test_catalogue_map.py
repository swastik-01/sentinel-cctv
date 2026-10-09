"""Catalogue mapping: departments, coordinates and districts from someone else's field names.

Departments and districts are read from the seed SQL, so the tests follow the real registry.
"""
import re
from pathlib import Path

import pytest

from sentinel_api.catalogue import (department_code, extract_items, find_coordinates, map_item,
                                    match_department, match_district, nearest_district)

ROOT = Path(__file__).resolve().parents[3]
SEED = (ROOT / "infra" / "postgres" / "init" / "02_seed.sql").read_text(encoding="utf-8")
DEPARTMENTS = dict(re.findall(r"\(\s*'([A-Z]+)'\s*,\s*'([^']*)'\s*\)", SEED))
CENTROIDS = {name: (float(lat), float(lon)) for name, lon, lat in re.findall(
    r"\('([^']+)',\s*'[^']*',\s*ST_GeogFromText\('POINT\(([\d.]+) ([\d.]+)\)'\)\)", SEED)}
DISTRICTS = {name.lower(): name for name in CENTROIDS}


def test_seed_parsed():
    assert len(DEPARTMENTS) == 26 and DEPARTMENTS["RNB"] == "Roads & Buildings"
    assert len(CENTROIDS) == 33 and CENTROIDS["Kutch"] == (23.2420, 69.6669)


@pytest.mark.parametrize("value, code", [
    # the four the old hint list got wrong (HEALTH, MUNI, HOME, HOME)
    ("Food & Civil Supplies Department", "FCS"),
    ("Gujarat State Road Transport Corporation", "GSRTC"),
    ("Roads & Buildings", "RNB"),
    ("Tourism", "TOUR"),
    ("HOME", "HOME"), ("gsrtc", "GSRTC"), ("Home Department (Police)", "HOME"),
    ("Police", "HOME"), ("Traffic Police", "HOME"), ("SCRB", "HOME"),
    ("Police Training College", "HOME"),
    ("Ahmedabad Municipal Corporation", "MUNI"), ("AMC", "MUNI"), ("Smart City", "MUNI"),
    ("Urban Development", "MUNI"),
    ("GSRTC Bus Depot", "GSRTC"),
    ("Health & Family Welfare", "HEALTH"), ("Civil Hospital", "HEALTH"),
    ("Food and Civil Supplies", "FCS"),
    ("R&B", "RNB"), ("Roads and Buildings Department", "RNB"),
    ("Tourism Corporation of Gujarat", "TOUR"),
    ("Narmada, Water Resources, Water Supply & Kalpsar Department", "NWR"), ("Irrigation", "NWR"),
    ("Gujarat Maritime Board", "GMB"), ("Ports", "GMB"),
    ("Transport", "RTO"), ("Transport Department", "RTO"), ("RTO", "RTO"),
    ("Panchayat", "PNCHT"), ("Forest Department", "FOREST"), ("Education", "EDU"),
    ("District Court", "LEGAL"), ("District Collector", "REV"), ("Jail", "JAILS"),
    ("GUVNL", "ENERGY"), ("Women & Child Development", "WCD"),
    ("Science and Technology", "SCITECH"),
    ("Gujarat Industrial Development Corporation", "IND"),
    ("Gujarat Pollution Control Board", "FOREST"), ("Civil Defence", "HOME"),
    ("Water Supply", "NWR"), ("AMTS", "MUNI"), ("City Bus", "MUNI"),
])
def test_department_matches(value, code):
    assert match_department(value, DEPARTMENTS, "HOME") == (code, None)
    assert department_code(value, DEPARTMENTS, "HOME") == code


@pytest.mark.parametrize("value", ["Department of Space", "Development", "Welfare", "D-07"])
def test_unknown_department_falls_back_with_a_warning(value):
    code, warning = match_department(value, DEPARTMENTS, "HOME")
    assert code == "HOME" and value in warning


def test_missing_department_is_flagged():
    assert match_department(None, DEPARTMENTS, "HOME") == (
        "HOME", "no department in record; assigned HOME")


def test_codes_only_still_work():
    # the old call shape: a set of codes, no names
    assert department_code("Police", {"HOME", "MUNI"}, "HOME") == "HOME"
    assert department_code("Municipal Corporation", {"HOME", "MUNI"}, "HOME") == "MUNI"


@pytest.mark.parametrize("item, source", [
    ({"lat": 23.0225, "lon": 72.5714}, "lat/lon"),
    ({"latitude": "23.0225", "longitude": "72.5714"}, "lat/lon"),
    ({"lat": "23.0225° N", "lon": "72.5714° E"}, "lat/lon"),
    ({"location": {"type": "Point", "coordinates": [72.5714, 23.0225]}},
     "location.coordinates (GeoJSON Point)"),
    ({"type": "Feature", "geometry": {"type": "Point", "coordinates": [72.5714, 23.0225, 55]}},
     "geometry.coordinates (GeoJSON Point)"),
    ({"gps": [72.5714, 23.0225]}, "gps [lon, lat] list"),
    ({"coordinates": [23.0225, 72.5714]}, "coordinates [lat, lon] list"),
    ({"location": "23.0225,72.5714"}, "location 'lat, lon' text"),
    ({"location": "72.5714, 23.0225"}, "location 'lon, lat' text"),
    ({"location": "POINT(72.5714 23.0225)"}, "location 'lon, lat' text"),
    ({"geo": {"latitude": 23.0225, "longitude": 72.5714}}, "geo.lat/lon"),
    ({"latlng": {"lat": 23.0225, "lng": 72.5714}}, "latlng.lat/lon"),
    ({"location": {"gps": {"lat": 23.0225, "long": 72.5714}}}, "location.gps.lat/lon"),
    ({"properties": {"lat": 23.0225, "lon": 72.5714}}, "properties.lat/lon"),
])
def test_coordinate_shapes(item, source):
    assert find_coordinates(item) == (23.0225, 72.5714, source, [])


def test_reversed_labelled_pair_is_swapped_with_a_warning():
    lat, lon, _, warnings = find_coordinates({"lat": 72.5714, "lon": 23.0225})
    assert (lat, lon) == (23.0225, 72.5714) and "reversed" in warnings[0]
    lat, lon, _, warnings = find_coordinates(
        {"location": {"type": "Point", "coordinates": [23.0225, 72.5714]}})
    assert (lat, lon) == (23.0225, 72.5714) and "reversed" in warnings[0]


@pytest.mark.parametrize("item", [{"lat": 19.0760, "lon": 72.8777},   # Mumbai
                                  {"lat": 0, "lon": 0},
                                  {"x": 512, "y": 288}])
def test_out_of_box_coordinates_are_rejected(item):
    lat, lon, source, warnings = find_coordinates(item)
    assert (lat, lon, source) == (None, None, None) and "outside Gujarat" in warnings[0]


def test_valid_pair_wins_over_a_rejected_one():
    lat, lon, source, _ = find_coordinates({"x": 512, "y": 288, "gps": "23.0225, 72.5714"})
    assert (lat, lon, source) == (23.0225, 72.5714, "gps 'lat, lon' text")


def test_no_coordinates_is_flagged():
    assert find_coordinates({"location": "Sector 21 Circle"})[3] == [
        "no coordinates in record; camera will not be on the map"]


@pytest.mark.parametrize("value, name", [
    ("Kutch", "Kutch"), ("Kachchh", "Kutch"), ("Mahesana", "Mehsana"), ("Mehsana", "Mehsana"),
    ("Ahmadabad", "Ahmedabad"), ("ahmedabad city", "Ahmedabad"), ("Dang", "Dang"),
    ("Dangs", "Dang"), ("The Dangs", "Dang"), ("Panchmahals", "Panchmahal"),
    ("Banas Kantha", "Banaskantha"), ("Sabar Kantha", "Sabarkantha"),
    ("Gir-Somnath", "Gir Somnath"), ("Chhota Udepur", "Chhota Udaipur"), ("Baroda", "Vadodara"),
    ("Devbhoomi Dwarka", "Devbhumi Dwarka"),
    ("Aravali", "Aravalli"), ("Surat District", "Surat"), ("Bhuj", "Kutch"),
])
def test_district_variants(value, name):
    assert match_district(value, DISTRICTS) == name


def test_unknown_district():
    assert match_district("Atlantis", DISTRICTS) is None
    assert match_district("", DISTRICTS) is None


def test_nearest_district():
    assert nearest_district(23.25, 69.67, CENTROIDS)[0] == "Kutch"
    assert nearest_district(21.19, 72.83, CENTROIDS)[0] == "Surat"


def _map(item):
    row, err = map_item(item, known_departments=DEPARTMENTS, known_districts=DISTRICTS,
                        default_department="HOME", district_centroids=CENTROIDS)
    assert err is None
    return row


def _key_fields(row):
    return (row["camera_code"], row["department_code"], row["district"], row["lat"], row["lon"])


SIMULATOR_RECORD = {   # GNR-POL-001 as the feed-simulator catalogue serves it
    "code": "GNR-POL-001", "name": "Sector 21 Circle, Gandhinagar", "department": "HOME",
    "district": "Gandhinagar", "lat": 23.2233, "lon": 72.6503, "codec": "H.264",
    "resolution": "1920x1080", "fps": 25, "anpr_viable": True, "analytics_enabled": True,
    "urls": {"rtsp": "rtsp://localhost:8554/GNR-POL-001",
             "whep": "http://localhost:8889/GNR-POL-001/whep",
             "hls": "http://localhost:8888/GNR-POL-001/index.m3u8"},
}


def test_simulator_record_unchanged():
    row = _map(SIMULATOR_RECORD)
    assert _key_fields(row) == (
        "GNR-POL-001", "HOME", "Gandhinagar", 23.2233, 72.6503)
    assert row["rtsp_url"] == "rtsp://localhost:8554/GNR-POL-001" and row["address"] is None
    assert row["tags"]["catalogue_warnings"] == [] and row["tags"]["coord_source"] == "lat/lon"


def test_geojson_feature_with_names_to_resolve():
    feature = {"type": "Feature",
               "geometry": {"type": "Point", "coordinates": [69.6669, 23.2420]},
               "properties": {"id": "kd-17", "department": "Roads & Buildings",
                              "district": "Kachchh", "rtsp": "rtsp://10.1.1.7/ch1"}}
    assert extract_items({"type": "FeatureCollection", "features": [feature]}) == [feature]
    row = _map(feature)
    assert _key_fields(row) == (
        "KD-17", "RNB", "Kutch", 23.2420, 69.6669)
    assert row["tags"]["catalogue_warnings"] == []


def test_district_inferred_from_location():
    row = _map({"id": "cam-1", "rtsp": "rtsp://x/1", "department": "Tourism",
                "location": "23.25, 69.67"})
    assert row["district"] == "Kutch" and row["department_code"] == "TOUR"
    assert row["address"] is None                       # the coordinate text is not an address
    assert any(w.startswith("district inferred from location: Kutch")
               for w in row["tags"]["catalogue_warnings"])


def test_unrecognised_district_inferred_and_named():
    row = _map({"id": "cam-2", "rtsp": "rtsp://x/2", "department": "Police", "zone": "West Zone",
                "lat": 21.19, "lon": 72.83})
    assert row["district"] == "Surat" and row["tags"]["district_unmatched"] == "West Zone"
    assert "'West Zone' not recognised" in row["tags"]["catalogue_warnings"][0]


def test_nested_objects_and_unknown_department():
    row = _map({"camera_id": "fcs-9", "stream_url": "rtsp://x/9",
                "department": {"id": 4, "name": "Food & Civil Supplies Department"},
                "location": {"name": "PDS Godown, Bhuj", "district": "Kutch",
                             "geo": {"lat": 23.25, "lng": 69.67}}})
    assert (row["department_code"], row["district"], row["address"]) == (
        "FCS", "Kutch", "PDS Godown, Bhuj")
    assert row["tags"]["coord_source"] == "location.geo.lat/lon"

    row = _map({"id": "sp-1", "rtsp": "rtsp://x/1", "department": "Department of Space",
                "lat": 23.02, "lon": 72.57, "district": "Ahmedabad"})
    assert row["department_code"] == "HOME"
    assert row["tags"]["catalogue_warnings"] == [
        "department 'Department of Space' not recognised; assigned HOME"]


def test_location_block_never_supplies_the_camera_id_or_stream():
    # device_id and rtsp_uri rank below id and url among the aliases
    row = _map({"device_id": "dev-x1", "rtsp_uri": "rtsp://x/1",
                "location": {"id": 17, "code": "L1", "url": "http://maps/17", "district": "Anand",
                             "lat": 22.56, "lon": 72.93}})
    assert (row["camera_code"], row["rtsp_url"], row["district"], row["address"]) == (
        "DEV-X1", "rtsp://x/1", "Anand", None)


def test_second_department_field_used_when_first_is_foreign():
    row = _map({"id": "t-1", "rtsp": "rtsp://x/1", "department_code": "D-07",
                "department_name": "Tourism", "lat": 23.02, "lon": 72.57})
    assert row["department_code"] == "TOUR" and row["tags"]["catalogue_warnings"][0].startswith(
        "district inferred")


def test_class_mode_and_storage_come_from_the_catalogue():
    from sentinel_api.catalogue import map_item
    item = {"code": "C-1", "rtsp": "rtsp://h/1", "lat": 23.0, "lon": 72.5, "camera_class": "ANPR",
            "mode": "vms_api", "storage": "cloud", "type": "Feature"}
    row, err = map_item(item, known_departments={"HOME"}, known_districts={}, default_department="HOME")
    assert err is None
    assert (row["camera_class"], row["mode"], row["storage"]) == ("anpr", "vms_api", "cloud")


def test_unknown_enum_values_fall_back_quietly():
    from sentinel_api.catalogue import ENUMS, _enum
    assert _enum({"type": "Feature"}, "camera_class", "fixed") == "fixed"
    assert _enum({"storage": "NVR"}, "storage", "unknown") == "unknown"
    assert "vms_api" in ENUMS["mode"]
