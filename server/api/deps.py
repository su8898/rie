"""Auth dependencies — session-cookie identity + lane-based RBAC (ADMIN is superuser)."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request


def current_user(request: Request) -> dict:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="login required")
    return u


def require_role(*roles: str) -> Callable[[Request], dict]:
    def dep(request: Request) -> dict:
        u = current_user(request)
        if roles and u["role"] != "ADMIN" and u["role"] not in roles:
            raise HTTPException(status_code=403, detail="forbidden for role " + u["role"])
        return u
    return dep
