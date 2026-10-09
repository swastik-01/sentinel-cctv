"""JWT auth and permission checks.

Roles carry a permission list (see 02_seed.sql). "*" grants everything.
Users may be scoped to a department and/or district; routers apply that scope
to camera queries so a department nodal officer only ever sees their own fleet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from .config import get_settings
from .db import get_conn

_hasher = PasswordHasher()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


@dataclass
class User:
    id: UUID
    username: str
    full_name: str
    role: str
    permissions: list[str] = field(default_factory=list)
    department_id: int | None = None
    district_id: int | None = None

    def can(self, perm: str) -> bool:
        return "*" in self.permissions or perm in self.permissions

    @property
    def statewide(self) -> bool:
        """No department and no district: a user scoped to a district alone is not statewide either."""
        return self.department_id is None and self.district_id is None


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id), "username": user.username, "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


async def load_user(conn: asyncpg.Connection, user_id: str) -> User | None:
    row = await conn.fetchrow(
        """SELECT u.id, u.username, u.full_name, u.department_id, u.district_id, u.active,
                  r.code AS role, r.permissions
           FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = $1""", UUID(user_id))
    if row is None or not row["active"]:
        return None
    return User(id=row["id"], username=row["username"], full_name=row["full_name"],
                role=row["role"], permissions=list(row["permissions"] or []),
                department_id=row["department_id"], district_id=row["district_id"])


def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")


async def current_user(token: str | None = Depends(oauth2),
                       conn: asyncpg.Connection = Depends(get_conn)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    user = await load_user(conn, decode_token(token)["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled or unknown")
    return user


def require(*perms: str):
    """Dependency: current user must hold every listed permission."""
    async def _dep(user: User = Depends(current_user)) -> User:
        missing = [p for p in perms if not user.can(p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing permission: {', '.join(missing)}")
        return user
    return _dep


async def require_ingest_key(request: Request) -> None:
    """Internal auth for analytics workers posting sightings/events."""
    key = request.headers.get("x-ingest-key") or ""
    if not key or not secrets.compare_digest(key.encode(), get_settings().ingest_key.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad ingest key")


# Grants added after first deployment. The seed runs only on an empty database, so these are
# applied idempotently at every start-up. operator: the control-room Overview reads fleet and
# object-count reports, which are aggregates with no personal data. Plate review grades the
# system's reads against real registrations: a supervisory and audit task, not an operator's.
ROLE_GRANTS = {"operator": ["reports.read"],
               "supervisor": ["reviews.read", "reviews.write"],
               "auditor": ["reviews.read", "reviews.write"]}


async def ensure_role_grants(conn: asyncpg.Connection) -> None:
    for role, perms in ROLE_GRANTS.items():
        for perm in perms:
            await conn.execute(
                """UPDATE roles SET permissions = permissions || to_jsonb($2::text)
                   WHERE code = $1 AND NOT permissions ? $2""", role, perm)


async def bootstrap_admin(conn: asyncpg.Connection) -> None:
    s = get_settings()
    n = await conn.fetchval("SELECT count(*) FROM users")
    if n:
        return
    role_id = await conn.fetchval("SELECT id FROM roles WHERE code = 'admin'")
    await conn.execute(
        "INSERT INTO users (username, full_name, password_hash, role_id) VALUES ($1, $2, $3, $4)",
        s.admin_username, "Platform Administrator", hash_password(s.admin_password), role_id)
    # Demo accounts for the other roles, so RBAC can be shown live.
    for uname, name, role, dept in (
        ("supervisor", "Control Room Supervisor", "supervisor", None),
        ("operator", "Control Room Operator", "operator", None),
        ("gsrtc_nodal", "GSRTC Nodal Officer", "dept_nodal", "GSRTC"),
        ("auditor", "Compliance Auditor", "auditor", None),
    ):
        rid = await conn.fetchval("SELECT id FROM roles WHERE code = $1", role)
        did = await conn.fetchval("SELECT id FROM departments WHERE code = $1", dept) if dept else None
        await conn.execute(
            """INSERT INTO users (username, full_name, password_hash, role_id, department_id)
               VALUES ($1, $2, $3, $4, $5)""",
            uname, name, hash_password(s.admin_password), rid, did)
