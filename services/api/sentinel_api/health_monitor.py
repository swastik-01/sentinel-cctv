"""Background camera health monitor and relay reconciler.

Every HEALTH_INTERVAL_S seconds:
  1. Reconcile: every camera onboarded by URL must have its relay path configured in
     MediaMTX (whose path config is in-memory). Missing relays are re-registered, so a
     media-server restart heals itself within one interval.
  2. Probe each registered camera with a stream URL:
     - always-on streams through our MediaMTX: the control API says whether the path is
       ready and whether bytes are still arriving (cheap, exact, no extra RTSP sessions)
     - on-demand relays: nobody may be watching, so probe the upstream source's host:port
     - anything else: a TCP connect to the RTSP host:port
Results land in camera_health_checks, cameras.health is updated, and a camera.health
event is published on any state change.
"""
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

import httpx

from . import bus
from .config import get_settings
from .db import pool
from .mediamtx import MediaMTX

log = logging.getLogger("sentinel.health")


async def _mediamtx_paths(client: httpx.AsyncClient) -> dict[str, dict]:
    try:
        r = await client.get(f"{get_settings().mediamtx_api}/v3/paths/list",
                             params={"itemsPerPage": 5000}, timeout=3)
        r.raise_for_status()
        return {p["name"]: p for p in r.json().get("items", [])}
    except httpx.HTTPError as e:
        log.warning("mediamtx api unreachable: %s", e)
        return {}


async def _tcp_probe(host: str, port: int, timeout: float = 2.5) -> tuple[bool, int | None, str | None]:
    t0 = time.perf_counter()
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        w.close()
        return True, int((time.perf_counter() - t0) * 1000), None
    except (OSError, asyncio.TimeoutError) as e:
        return False, None, type(e).__name__


def probe_cache():
    """A probe for one round of the monitor that connects to each upstream host and port once and repeats the answer:
    fifty cameras behind one recorder or gateway get one connection, not fifty (someone else's server should not see a
    burst that looks like a port scan)."""
    probed: dict[tuple[str, int], tuple[bool, int | None, str | None]] = {}

    async def probe(host: str, port: int) -> tuple[bool, int | None, str | None]:
        if (host, port) not in probed:
            probed[(host, port)] = await _tcp_probe(host, port)
        return probed[(host, port)]
    return probe


def _default_port(url: str) -> int:
    u = urlparse(url)
    return u.port or {"rtsp": 554, "rtsps": 322, "rtmp": 1935, "http": 80, "https": 443}.get(u.scheme, 554)


def _is_local_mediamtx(url: str) -> bool:
    s = get_settings()
    u = urlparse(url)
    return (u.port or 554) == s.mediamtx_rtsp_port and u.hostname in (
        s.mediamtx_host, "localhost", "127.0.0.1", "mediamtx")


async def reconcile_relays(conn) -> int:
    rows = await conn.fetch(
        """SELECT c.camera_code, s.source_url, s.on_demand
           FROM camera_sources s JOIN cameras c ON c.id = s.camera_id""")
    if not rows:
        return 0
    mtx = MediaMTX()
    try:
        configured = await mtx.config_path_names()
    except httpx.HTTPError:
        return 0
    healed = 0
    for r in rows:
        if r["camera_code"] not in configured:
            try:
                await mtx.put_relay(r["camera_code"], r["source_url"], r["on_demand"])
                healed += 1
            except httpx.HTTPError as e:
                log.warning("relay re-register failed for %s: %s", r["camera_code"], e)
    if healed:
        log.info("re-registered %d relay path(s) in MediaMTX", healed)
    return healed


async def run_once(prev_bytes: dict[str, int]) -> None:
    async with pool().acquire() as conn:
        await reconcile_relays(conn)
        cams = await conn.fetch(
            """SELECT c.id, c.camera_code, c.rtsp_url, c.health::text, s.source_url, s.on_demand
               FROM cameras c LEFT JOIN camera_sources s ON s.camera_id = c.id
               WHERE c.rtsp_url IS NOT NULL""")
        if not cams:
            return
        probe_once = probe_cache()
        async with httpx.AsyncClient() as client:
            paths = await _mediamtx_paths(client)
            for cam in cams:
                url = cam["rtsp_url"]
                path = urlparse(url).path.strip("/")
                if cam["on_demand"] and cam["source_url"]:
                    # an idle on-demand relay is healthy if its upstream is reachable
                    live = paths.get(path, {}).get("ready")
                    if live:
                        reachable, latency, err = True, None, None
                    else:
                        su = urlparse(cam["source_url"])
                        host = su.hostname or ""
                        if host in ("localhost", "127.0.0.1"):   # source is the media server itself
                            host = get_settings().mediamtx_host
                        reachable, latency, err = await probe_once(host, _default_port(cam["source_url"]))
                    state = "online" if reachable else "offline"
                elif _is_local_mediamtx(url):
                    p = paths.get(path)
                    reachable = bool(p and p.get("ready"))
                    latency = None
                    err = None if reachable else "path not ready"
                    got = int(p.get("bytesReceived", 0)) if p else 0
                    stalled = reachable and prev_bytes.get(path) == got
                    prev_bytes[path] = got
                    state = "degraded" if stalled else ("online" if reachable else "offline")
                else:
                    reachable, latency, err = await probe_once(urlparse(url).hostname or "", _default_port(url))
                    state = "online" if reachable and (latency or 0) < 1500 else (
                        "degraded" if reachable else "offline")

                await conn.execute(
                    """INSERT INTO camera_health_checks (camera_id, reachable, latency_ms, state, error)
                       VALUES ($1, $2, $3, $4::health_state, $5)""",
                    cam["id"], reachable, latency, state, err)
                await conn.execute(
                    """UPDATE cameras SET health = $2::health_state,
                       last_seen_at = CASE WHEN $3 THEN now() ELSE last_seen_at END WHERE id = $1""",
                    cam["id"], state, reachable)
                if state != cam["health"]:
                    log.info("%s: %s -> %s", cam["camera_code"], cam["health"], state)
                    await bus.publish("camera.health", {"camera_code": cam["camera_code"],
                                                        "from": cam["health"], "to": state,
                                                        "error": err})
        await conn.execute("DELETE FROM camera_health_checks WHERE checked_at < now() - interval '30 days'")


async def loop() -> None:
    prev: dict[str, int] = {}
    interval = get_settings().health_interval_s
    await asyncio.sleep(3)
    while True:
        try:
            await run_once(prev)
        except Exception:  # noqa: BLE001
            log.exception("health monitor iteration failed")
        await asyncio.sleep(interval)
