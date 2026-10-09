"""Minimal MediaMTX control-API client: relay paths for onboarded cameras."""
from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from .config import get_settings


def mask_url(url: str) -> str:
    """rtsp://user:secret@host/path -> rtsp://user:***@host/path"""
    parts = urlsplit(url)
    if parts.password:
        netloc = f"{parts.username}:***@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
        return urlunsplit(parts._replace(netloc=netloc))
    return url


def relay_urls(code: str, codec: str | None) -> dict[str, str]:
    """Registry endpoints for a relayed camera. Browsers get the H.264 preview profile
    (transcoded on demand) when the source is H.265; inference always gets the original."""
    s = get_settings()
    host = s.mediamtx_host
    preview = f"{code}_sub" if codec and re.search(r"265|hevc", codec, re.I) else code
    return {
        "rtsp_url": f"rtsp://{host}:{s.mediamtx_rtsp_port}/{code}",
        "whep_url": f"http://{host}:{s.mediamtx_whep_port}/{preview}/whep",
        "hls_url": f"http://{host}:{s.mediamtx_hls_port}/{preview}/index.m3u8",
    }


def _codec_info(path: dict) -> dict:
    """Normalise MediaMTX's track description across versions."""
    info: dict = {"codec": None, "width": None, "height": None, "tracks": []}
    for t in path.get("tracks2") or []:
        codec = t.get("codec")
        info["tracks"].append(codec)
        if codec and codec.upper() in ("H264", "H265", "MJPEG", "AV1", "VP8", "VP9") and not info["codec"]:
            props = t.get("codecProps") or {}
            info.update(codec=codec, width=props.get("width"), height=props.get("height"))
    if not info["tracks"]:
        for t in path.get("tracks") or []:
            name = t if isinstance(t, str) else t.get("codec")
            info["tracks"].append(name)
            if name and not info["codec"] and name.upper() in ("H264", "H265", "MJPEG", "AV1", "VP8", "VP9"):
                info["codec"] = name
    if info["codec"]:
        info["codec"] = {"H264": "H.264", "H265": "H.265"}.get(info["codec"].upper(), info["codec"])
    return info


class MediaMTX:
    def __init__(self) -> None:
        self.base = get_settings().mediamtx_api

    async def config_path_names(self) -> set[str]:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/v3/config/paths/list", params={"itemsPerPage": 5000})
            r.raise_for_status()
            return {p["name"] for p in r.json().get("items", [])}

    async def put_relay(self, name: str, source: str, on_demand: bool) -> None:
        body = {"source": source, "sourceOnDemand": on_demand, "rtspTransport": "tcp",
                "sourceOnDemandStartTimeout": "15s", "sourceOnDemandCloseAfter": "30s"}
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(f"{self.base}/v3/config/paths/add/{name}", json=body)
            if r.status_code == 400 and "already exists" in r.text:
                r = await c.patch(f"{self.base}/v3/config/paths/patch/{name}", json=body)
            r.raise_for_status()

    async def delete_path(self, name: str) -> None:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.delete(f"{self.base}/v3/config/paths/delete/{name}")
            if r.status_code not in (200, 404):
                r.raise_for_status()

    async def path(self, name: str) -> dict | None:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/v3/paths/get/{name}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    async def probe(self, name: str, source: str, timeout_s: float = 15.0) -> dict:
        """Relay the source always-on until it is ready, then report what it carries.
        The path stays configured; callers switch it to on-demand afterwards if wanted."""
        t0 = time.perf_counter()
        await self.put_relay(name, source, on_demand=False)
        last: dict | None = None
        while time.perf_counter() - t0 < timeout_s:
            last = await self.path(name)
            if last and last.get("ready"):
                info = _codec_info(last)
                if info["codec"] or time.perf_counter() - t0 > 3:
                    return {"ready": True, "seconds": round(time.perf_counter() - t0, 1), **info}
            await asyncio.sleep(0.5)
        return {"ready": False, "seconds": round(time.perf_counter() - t0, 1),
                "error": "source did not become ready — check URL, credentials, and that the "
                         "media server can reach the camera network",
                **(_codec_info(last) if last else {"codec": None, "width": None, "height": None, "tracks": []})}
