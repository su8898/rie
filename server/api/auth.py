"""Login / logout / me — signed-cookie session."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppUser
from ..security import verify_password
from .deps import current_user

router = APIRouter(prefix="/auth")


class Login(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: Login, request: Request, db: Session = Depends(get_db)) -> dict:
    u = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    request.session["user"] = {"username": u.username, "role": u.role}
    return {"username": u.username, "role": u.role}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user
