from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from . import bus, health_monitor
from .auth import bootstrap_admin, ensure_role_grants
from .config import get_settings
from .db import close_pool, init_pool, pool
from .guards import RequestGuard, validation_refusal
from .routers import (alerts, auth, cameras, evidence, gis, ingest, onboard, quality, reports, reviews, sightings,
                      watchlist, zones)
from .upgrades import apply_upgrades

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinel.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    await init_pool()
    await bus.init_bus()
    async with pool().acquire() as conn:
        await apply_upgrades(conn)
        await bootstrap_admin(conn)
        await ensure_role_grants(conn)
    task = asyncio.create_task(health_monitor.loop()) if s.health_monitor else None
    log.info("Sentinel API up. face_recognition=%s", s.enable_face_recognition)
    # The repo, with .env.example, is readable by anyone: a deployment still on an example value can be signed into,
    # fed fabricated sightings, or have its database opened by whoever read it. Said loudly at every start.
    for name, value, example in (("JWT_SECRET", s.jwt_secret, "dev_only_replace_me"),
                                 ("INGEST_KEY", s.ingest_key, "dev_ingest_key_replace_me"),
                                 ("ADMIN_PASSWORD", str(getattr(s, "admin_password", "")), "admin123"),
                                 ("POSTGRES_PASSWORD", s.database_url, "change_me_in_production")):
        if example and example in value:
            log.error("%s is still the example value from .env.example: run scripts/rotate_secrets.py "
                      "(scripts/set_passwords.py for ADMIN_PASSWORD) before this machine joins a shared network", name)
    try:
        yield
    finally:
        if task:
            task.cancel()
        await bus.close_bus()
        await close_pool()


app = FastAPI(
    title="Sentinel — Unified CCTV Integration Platform",
    version="0.1.0",
    description="Gujarat Police Innovation Challenge 2026. Model 1 registry + GIS, "
                "Model 2 unified viewing + metadata analytics.",
    lifespan=lifespan,
)
# NUL characters and oversized JSON: a 4xx before any route (guards.py). Added first, so CORS wraps it
# and a refusal still reaches the browser with its CORS headers.
app.add_middleware(RequestGuard)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list,
                   allow_origin_regex=get_settings().cors_origin_regex or None, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(RequestValidationError, validation_refusal)

for r in (auth, zones, cameras, onboard, gis, sightings, watchlist, alerts, reports, quality, ingest, evidence, reviews):
    app.include_router(r.router)

# Plate crops written by workers. Served by routers/evidence.py, which checks the token,
# the permission and the camera's scope: never as an open static folder.
import os  # noqa: E402
os.makedirs("data/crops", exist_ok=True)


@app.get("/healthz", tags=["meta"])
async def healthz():
    async with pool().acquire() as conn:
        fleet = await conn.fetchrow("SELECT * FROM v_fleet_summary")
    return {"ok": True, "fleet": dict(fleet)}


def run() -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run("sentinel_api.main:app", host=s.api_host, port=s.api_port, reload=False)
