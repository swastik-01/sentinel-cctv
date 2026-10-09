"""Logs leave the database's scoping, audit and retention, so a worker's log never carries a whole registration;
and only stream schemes reach the decoders. Synthetic plates only."""
from sentinel_common import mask_plate

from sentinel_analytics.worker import allowed_source


def test_a_masked_plate_keeps_the_state_code_and_the_last_two_characters():
    assert mask_plate("GJ99AB1234") == "GJ******34"
    assert mask_plate("22BH1234A") == "22*****4A"
    assert mask_plate("GJ1") == "***"
    assert mask_plate("") == ""


def test_only_stream_schemes_reach_the_decoders():
    assert allowed_source("rtsp://localhost:8554/CAM06")
    assert allowed_source("RTSPS://cam/stream") and allowed_source("http://host/live/x/index.m3u8")
    assert not allowed_source("file:///C:/Users/x/.env")
    assert not allowed_source("concat:a|b") and not allowed_source("") and not allowed_source(None)
