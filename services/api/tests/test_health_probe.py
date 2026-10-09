"""The health monitor probes each upstream host and port once a round, however many cameras sit behind it."""
import asyncio

from sentinel_api import health_monitor


def test_fifty_cameras_behind_one_host_cost_one_connection(monkeypatch):
    calls = []

    async def fake_probe(host, port, timeout=2.5):
        calls.append((host, port))
        return True, 12, None

    monkeypatch.setattr(health_monitor, "_tcp_probe", fake_probe)

    async def round_():
        probe = health_monitor.probe_cache()
        got = [await probe("gateway.example", 8554) for _ in range(50)]
        got.append(await probe("nvr.example", 554))
        return got

    got = asyncio.run(round_())
    assert calls == [("gateway.example", 8554), ("nvr.example", 554)]
    assert all(g == (True, 12, None) for g in got)


def test_each_round_probes_afresh(monkeypatch):
    calls = []

    async def fake_probe(host, port, timeout=2.5):
        calls.append((host, port))
        return False, None, "TimeoutError"

    monkeypatch.setattr(health_monitor, "_tcp_probe", fake_probe)

    async def two_rounds():
        for _ in range(2):
            probe = health_monitor.probe_cache()
            await probe("gateway.example", 8554)
            await probe("gateway.example", 8554)

    asyncio.run(two_rounds())
    assert calls == [("gateway.example", 8554)] * 2
