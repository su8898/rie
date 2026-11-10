"""Auth dependencies — session-cookie identity + lane-based RBAC (ADMIN is superuser).

The cookie only identifies the user; role and active status are re-read from `app_user` on
every request, so a deactivation or role change takes effect immediately (not at cookie expiry)
and a forged/stale cookie naming an unknown user is rejected."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppUser


def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    u = request.session.get("user")
    if not u or not u.get("username"):
        raise HTTPException(status_code=401, detail="login required")
    row = db.scalar(select(AppUser).where(AppUser.username == u["username"]))
    if row is None or not row.active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="session no longer valid — login required")
    if row.role != u.get("role"):                       # role changed since login -> apply now
        u = {"username": row.username, "role": row.role}
        request.session["user"] = u
    return u


def require_role(*roles: str) -> Callable[..., dict]:
    def dep(user: dict = Depends(current_user)) -> dict:
        if roles and user["role"] != "ADMIN" and user["role"] not in roles:
            raise HTTPException(status_code=403, detail="forbidden for role " + user["role"])
        return user
    return dep
