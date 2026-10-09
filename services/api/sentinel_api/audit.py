"""Append-only audit trail. Called from every router that touches footage,
plates, watchlists or alerts. The DB rules make UPDATE/DELETE no-ops."""
from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import Request

from .auth import User


async def audit(conn: asyncpg.Connection, request: Request | None, user: User | None,
                action: str, object_type: str | None = None, object_id: Any = None,
                purpose: str | None = None, **detail: Any) -> None:
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent") if request else None
    await conn.execute(
        """INSERT INTO audit_log (actor_id, actor_name, action, object_type, object_id,
                                  purpose, ip, user_agent, detail)
           VALUES ($1, $2, $3, $4, $5, $6, $7::inet, $8, $9::jsonb)""",
        user.id if user else None, user.username if user else "system", action,
        object_type, str(object_id) if object_id is not None else None,
        purpose, ip, ua, detail)
