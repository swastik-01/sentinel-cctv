"""Request guards in front of every route: input the database or the JSON encoder cannot take is refused with a
4xx before it reaches a handler, instead of surfacing as a 500 (found by scripts/edge_checks.py).

- A NUL character, in the path, the query or a JSON body: PostgreSQL text cannot hold one.
- A JSON body over MAX_JSON_BYTES: nothing the API takes as JSON comes near it (files arrive as multipart).
- A validation refusal answers with where and why, never the submitted value: echoing it back fails on NaN
  (not valid JSON) and would repeat a password or a key to whoever sent it.
"""
from __future__ import annotations

import json
import math
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

MAX_JSON_BYTES = 8 * 2**20
NUL = "NUL characters are not accepted"


class RequestGuard:
    """Pure ASGI, so streaming responses and the WebSocket pass through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if "\x00" in scope.get("path", "") or b"%00" in scope.get("raw_path", b"") \
                or b"%00" in scope.get("query_string", b""):
            return await _refuse(send, 422, NUL)
        # FastAPI reads a body as JSON when its type says JSON (application/json, application/*+json) and also when
        # there is no type at all; files arrive as multipart and pass untouched.
        content_type = dict(scope.get("headers") or []).get(b"content-type", b"").lower()
        if content_type and b"json" not in content_type:
            return await self.app(scope, receive, send)
        body, more = b"", True
        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            if len(body) > MAX_JSON_BYTES:
                return await _refuse(send, 413, f"a JSON body is at most {MAX_JSON_BYTES // 2**20} MB")
        if b"\x00" in body or b"\\u0000" in body.lower():
            return await _refuse(send, 422, NUL)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


async def _refuse(send, status: int, detail: str) -> None:
    payload = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
    await send({"type": "http.response.body", "body": payload})


def _plain(v: Any) -> Any:
    """A validation context value as JSON can carry it: non-finite floats and objects become text."""
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return str(v)


async def validation_refusal(_: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "invalid"), "type": e.get("type", "value_error"),
               **({"ctx": {k: _plain(v) for k, v in e["ctx"].items()}} if e.get("ctx") else {})}
              for e in exc.errors()]
    return JSONResponse({"detail": detail}, status_code=422)
