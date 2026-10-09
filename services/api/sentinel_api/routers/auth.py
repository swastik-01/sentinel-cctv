from __future__ import annotations

from collections import deque
from time import monotonic

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from ..audit import audit
from ..auth import User, create_token, current_user, load_user, verify_password
from ..db import get_conn
from ..schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


_attempts: dict[str, deque] = {}
LOGIN_PER_MINUTE = 30       # generous: smoke.py and the recorders sign in a few times a minute, a guesser far more


def throttled(ip: str, now: float | None = None) -> bool:
    """More than LOGIN_PER_MINUTE sign-in attempts from one address in a minute are refused before the password
    is checked: each check costs about 0.1 s of argon2, and an unthrottled guesser would also fill the audit log."""
    now = monotonic() if now is None else now
    q = _attempts.setdefault(ip, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= LOGIN_PER_MINUTE:
        return True
    q.append(now)
    return False


async def _login(conn: asyncpg.Connection, request: Request, username: str, password: str) -> TokenOut:
    if throttled(request.client.host if request.client else "?"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many sign-in attempts; wait a minute")
    row = await conn.fetchrow("SELECT id, password_hash, active FROM users WHERE username = $1",
                              username)
    # argon2 takes ~0.1 s: in a thread, so the event loop keeps serving ingest and the control room meanwhile
    ok = row is not None and row["active"] and await run_in_threadpool(verify_password, password, row["password_hash"])
    if not ok:
        await audit(conn, request, None, "auth.login_failed", "user", username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    user = await load_user(conn, str(row["id"]))
    assert user is not None
    await conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", user.id)
    await audit(conn, request, user, "auth.login", "user", user.id)
    return TokenOut(access_token=create_token(user), user=UserOut(**user.__dict__))


@router.post("/login", response_model=TokenOut)
async def login_json(body: LoginIn, request: Request, conn: asyncpg.Connection = Depends(get_conn)):
    return await _login(conn, request, body.username, body.password)


@router.post("/token", response_model=TokenOut, include_in_schema=True)
async def login_form(request: Request, form: OAuth2PasswordRequestForm = Depends(),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """OAuth2 password flow, so the Swagger UI 'Authorize' button works."""
    return await _login(conn, request, form.username, form.password)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return UserOut(**user.__dict__)
