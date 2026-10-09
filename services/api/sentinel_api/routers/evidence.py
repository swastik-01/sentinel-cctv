"""Evidence crops: the plate images workers write, served only to a signed-in user who may
see the sighting or alert they belong to, and only for cameras inside that user's scope.

The token comes in the Authorization header only. The control room fetches each crop with it and shows the image
from memory (web/src/components/CropImg.tsx): a token in a URL ends up in proxy logs, browser history and
screenshots. Anything outside the crop store, or outside the user's department/district, is a 404: a crop's
existence is itself information.
"""
from __future__ import annotations

from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security.utils import get_authorization_scheme_param

from ..auth import User, decode_token, load_user
from ..cameras_repo import scope_clause
from ..db import get_conn

router = APIRouter(tags=["evidence"])
CROP_ROOT = Path("data/crops").resolve()


async def token_user(request: Request, conn: asyncpg.Connection) -> User:
    """The signed-in user, from the Authorization header."""
    scheme, raw = get_authorization_scheme_param(request.headers.get("authorization"))
    if scheme.lower() != "bearer" or not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    user = await load_user(conn, decode_token(raw)["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled or unknown")
    return user


def crop_file(crop_path: str | None) -> Path | None:
    """The file behind a stored crop_path ('/crops/<camera>/<name>.jpg'), if it is in that camera's folder of the
    store. Exactly two parts and no separator inside either: on Windows a backslash in the name is a separator, and
    '<camera>/..\\<other camera>\\<file>.jpg' reached another camera's crop while the scope was checked on <camera>."""
    if not crop_path or not crop_path.startswith("/crops/"):
        return None
    parts = crop_path.removeprefix("/crops/").split("/")
    if len(parts) != 2 or any(not p or p in (".", "..") or "\\" in p or ":" in p for p in parts):
        return None
    camera, name = parts
    path = (CROP_ROOT / camera / name).resolve()
    if (path.parent.parent != CROP_ROOT or path.parent.name.upper() != camera.upper()
            or path.suffix.lower() != ".jpg" or not path.is_file()):
        return None
    return path


def send_crop(path: Path) -> FileResponse:
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/crops/{camera}/{name}", include_in_schema=False)
async def crop(camera: str, name: str, request: Request, conn: asyncpg.Connection = Depends(get_conn)):
    user = await token_user(request, conn)
    if not (user.can("sightings.search") or user.can("alerts.read")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing permission: sightings.search or alerts.read")

    path = crop_file(f"/crops/{camera}/{name}")
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such crop")
    where, params = scope_clause(user, alias="c", start_idx=2)
    if not await conn.fetchval(f"SELECT 1 FROM cameras c WHERE c.camera_code = $1 AND {where}",
                               camera.upper(), *params):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such crop")
    return send_crop(path)
