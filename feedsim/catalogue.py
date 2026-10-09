"""Camera catalogue API — mirrors the hackathon sandbox contract.

Lists every simulated camera with location, codec, live status and its three
stream endpoints (RTSP for inference, WHEP for browser preview, HLS for
dashboards). Status is read live from the MediaMTX control API.

Admin endpoints simulate outages so health monitoring can be demonstrated.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

CAMERAS = Path(os.environ.get("CAMERAS_FILE", "cameras.yaml"))
STATE = Path(os.environ.get("STATE_DIR", "/state"))
MTX_API = os.environ.get("MEDIAMTX_API", "http://mediamtx:9997").rstrip("/")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
RTSP_PORT = os.environ.get("RTSP_PORT", "8554")
WHEP_PORT = os.environ.get("WHEP_PORT", "8889")
HLS_PORT = os.environ.get("HLS_PORT", "8888")

app = FastAPI(title="Sentinel Feed Catalogue", version="0.1.0")
# The control room reads this list and calls the outage endpoint from the browser (Map and Health pages): without
# CORS the browser blocks both, and the simulator buttons never appear.
app.add_middleware(CORSMiddleware, allow_methods=["GET", "POST"], allow_headers=["*"],
                   allow_origins=[o.strip() for o in os.environ.get(
                       "SIM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()])
_cams: list[dict] = yaml.safe_load(CAMERAS.read_text())["cameras"]
_by_code = {c["code"]: c for c in _cams}


def urls(cam: dict) -> dict:
    """Per-camera endpoints. `rtsp` is always the original stream (for inference).
    Browser endpoints point at the H.264 preview sub-stream for H.265 cameras."""
    code = cam["code"]
    preview = f"{code}_sub" if cam.get("codec") == "h265" else code
    return {
        "rtsp": f"rtsp://{PUBLIC_HOST}:{RTSP_PORT}/{code}",
        "whep": f"http://{PUBLIC_HOST}:{WHEP_PORT}/{preview}/whep",
        "hls": f"http://{PUBLIC_HOST}:{HLS_PORT}/{preview}/index.m3u8",
        "preview_rtsp": f"rtsp://{PUBLIC_HOST}:{RTSP_PORT}/{preview}",
        "preview_codec": "H.264",
    }


async def mtx_paths() -> dict[str, dict]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{MTX_API}/v3/paths/list", params={"itemsPerPage": 500})
            r.raise_for_status()
            return {p["name"]: p for p in r.json().get("items", [])}
    except httpx.HTTPError:
        return {}


def read_outages() -> dict[str, float]:
    try:
        return json.loads((STATE / "outages.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_outages(d: dict[str, float]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "outages.json").write_text(json.dumps(d))


def describe(cam: dict, paths: dict, outages: dict) -> dict:
    p = paths.get(cam["code"])
    ready = bool(p and p.get("ready"))
    status = "offline"
    if ready:
        status = "online"
    elif outages.get(cam["code"], 0) > time.time():
        status = "outage"
    return {
        "code": cam["code"],
        "name": cam["name"],
        "department": cam["department"],
        "district": cam["district"],
        "lat": cam["lat"],
        "lon": cam["lon"],
        "codec": cam["codec"].upper().replace("H26", "H.26"),
        "resolution": cam["resolution"],
        "fps": cam.get("fps"),
        "mode": cam.get("mode"),
        "camera_class": cam.get("camera_class", "fixed"),
        "vendor": cam.get("vendor"),
        "retention_days": cam.get("retention_days"),
        "storage": cam.get("storage", "unknown"),
        "anpr_viable": bool(cam.get("anpr_viable")),
        "analytics_enabled": bool(cam.get("analytics", cam.get("anpr_viable"))),
        "status": status,
        "readers": len(p.get("readers", [])) if p else 0,
        "bytes_received": p.get("bytesReceived") if p else 0,
        "ready_since": p.get("readyTime") if p else None,
        "preview": "on_demand_transcode" if cam.get("codec") == "h265" else "direct",
        "urls": urls(cam),
    }


@app.get("/")
async def root():
    return {"service": "sentinel-feed-catalogue", "cameras": len(_cams),
            "endpoints": ["/cameras", "/cameras/{code}", "/health", "/admin/outage/{code}"]}


@app.get("/health")
async def health():
    paths = await mtx_paths()
    online = sum(1 for c in _cams if paths.get(c["code"], {}).get("ready"))
    return {"ok": True, "mediamtx_reachable": bool(paths) or online == 0,
            "cameras": len(_cams), "online": online}


@app.get("/cameras")
async def list_cameras():
    paths, outages = await mtx_paths(), read_outages()
    return {"count": len(_cams), "items": [describe(c, paths, outages) for c in _cams]}


@app.get("/cameras/{code}")
async def get_camera(code: str):
    cam = _by_code.get(code)
    if not cam:
        raise HTTPException(404, f"unknown camera {code}")
    return describe(cam, await mtx_paths(), read_outages())


@app.post("/admin/outage/{code}")
async def simulate_outage(code: str, seconds: int = 60):
    """Take a camera down for N seconds. Demonstrates health monitoring end to end."""
    if code not in _by_code:
        raise HTTPException(404, f"unknown camera {code}")
    outages = read_outages()
    outages[code] = time.time() + max(1, min(seconds, 3600))
    write_outages(outages)
    return {"code": code, "down_for_seconds": seconds}


@app.delete("/admin/outage/{code}")
async def clear_outage(code: str):
    outages = read_outages()
    outages.pop(code, None)
    write_outages(outages)
    return {"code": code, "restored": True}
