"""A worker on another machine than the relay reaches it through RELAY_HOST (worker.via_relay_host); both workers
open a loopback relay by 127.0.0.1, never by the name localhost (worker.loopback_ipv4)."""
from sentinel_analytics.worker import loopback_ipv4, via_relay_host


def test_unset_keeps_the_shipped_behaviour():
    assert via_relay_host("rtsp://localhost:8554/CAM06", "") == "rtsp://localhost:8554/CAM06"


def test_localhost_relay_addresses_point_at_the_relay_machine():
    assert via_relay_host("rtsp://localhost:8554/CAM06", "192.168.1.20") == "rtsp://192.168.1.20:8554/CAM06"
    assert via_relay_host("rtsp://127.0.0.1:8554/AMD-POL-001", "10.0.0.5") == "rtsp://10.0.0.5:8554/AMD-POL-001"


def test_credentials_are_kept_and_other_hosts_left_alone():
    assert via_relay_host("rtsp://u:p@localhost:8554/x", "10.0.0.5") == "rtsp://u:p@10.0.0.5:8554/x"
    assert via_relay_host("rtsp://203.0.113.9:554/live", "10.0.0.5") == "rtsp://203.0.113.9:554/live"
    assert via_relay_host("", "10.0.0.5") == ""


def test_workers_open_localhost_as_ipv4_loopback():
    assert loopback_ipv4("rtsp://localhost:8554/CAM06") == "rtsp://127.0.0.1:8554/CAM06"
    assert loopback_ipv4("rtsp://u:p@localhost:8554/x") == "rtsp://u:p@127.0.0.1:8554/x"
    assert loopback_ipv4("rtsp://localhost/x") == "rtsp://127.0.0.1/x"


def test_other_hosts_reach_the_workers_unchanged():
    assert loopback_ipv4("rtsp://192.168.1.20:8554/CAM06") == "rtsp://192.168.1.20:8554/CAM06"
    assert loopback_ipv4("rtsp://localhost.example.org:8554/x") == "rtsp://localhost.example.org:8554/x"
    assert loopback_ipv4("") == ""
