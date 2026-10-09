"""Every registry write path (API, CSV import, catalogue sync) goes through validate_fields: a camera code is a
plain token (a worker makes a folder from it) and a stream address has a stream scheme (FFmpeg opens it)."""
import pytest

from sentinel_api.cameras_repo import validate_fields


@pytest.mark.parametrize("code", ["CAM01", "AMD-POL-001", "GNR-GSRTC-001", "GNR_MUNI_101", "cam07"])
def test_real_codes_pass_and_are_upper_cased(code):
    row = {"camera_code": code}
    validate_fields(row)
    assert row["camera_code"] == code.upper()


@pytest.mark.parametrize("code", [r"..\..\..\Users\x", "../etc", "a", "", "CAM 01", "x" * 65, "CAM01/sub"])
def test_a_code_that_could_leave_the_crop_folder_is_refused(code):
    with pytest.raises(ValueError):
        validate_fields({"camera_code": code})


def test_stream_addresses_must_be_stream_schemes():
    ok = {"camera_code": "CAM01", "rtsp_url": "rtsp://localhost:8554/CAM01",
          "hls_url": "http://host/live/stream/cam01/index.m3u8", "whep_url": "https://host:8889/CAM01/whep"}
    validate_fields(ok)
    for bad in ("file:///C:/Users/x/.env", "concat:a|b", "gopher://x", r"C:\clip.mp4"):
        with pytest.raises(ValueError):
            validate_fields({"camera_code": "CAM01", "rtsp_url": bad})
    validate_fields({"camera_code": "CAM01", "rtsp_url": None, "onvif_url": ""})   # empty is allowed
