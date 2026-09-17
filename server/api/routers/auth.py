"""Auth router: bootstrap, login, logout, me, and admin user management.

Implements the P5a accounts increment on top of server/api/accounts.py
(users/sessions/user_settings tables + password hashing). The middleware
dependency below enforces Bearer-token auth on every /api route except
/api/health, /api/auth/login, and /api/auth/bootstrap.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.api.accounts import (
    count_users,
    create_session,
    create_user,
    delete_session,
    get_db_path,
    get_session_user,
    get_setting,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    list_users,
    migrate,
    set_setting,
    verify_password,
    writable_conn,
)

router = APIRouter(prefix="/api")

# Routes exempt from auth (matched as path prefixes on the request scope).
PUBLIC_PATHS = ("/api/health", "/api/auth/login", "/api/auth/bootstrap")


def _public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS)


def require_user(request: Request):
    """FastAPI dependency: resolve the session token to an active user."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        _deny(request)
    with writable_conn() as conn:
        user = get_session_user(conn, token)
        if user is None:
            _deny(request)
        return dict(user)


def _deny(request: Request) -> None:
    with writable_conn() as conn:
        bootstrapped = count_users(conn) > 0
    raise HTTPException(
        status_code=401,
        detail={"needs_bootstrap": not bootstrapped, "message": "authentication required"},
    )


def admin_only(user=Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user


class LoginBody(BaseModel):
    username: str
    password: str


class UserCreateBody(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "user"


class UserPatchBody(BaseModel):
    is_active: bool | None = None
    role: str | None = None
    new_password: str | None = None


class SettingsBody(BaseModel):
    key: str | None = None
    value: object


def _public_user(row) -> dict:
    email = row["email"] if "email" in row.keys() else None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "email": email,
    }


@router.post("/auth/bootstrap", status_code=201)
def bootstrap() -> dict:
    with writable_conn() as conn:
        if count_users(conn) > 0:
            raise HTTPException(status_code=400, detail="already bootstrapped")
    username = os.environ.get("SERMONPILOT_ADMIN_USER", "").strip()
    password = os.environ.get("SERMONPILOT_ADMIN_PASSWORD", "")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="SERMONPILOT_ADMIN_USER and SERMONPILOT_ADMIN_PASSWORD must be set",
        )
    with writable_conn() as conn:
        row = create_user(conn, username, username, password, role="admin")
    return _public_user(row)


@router.post("/auth/login")
def login(body: LoginBody):
    with writable_conn() as conn:
        row = get_user_by_username(conn, body.username)
        if row is None or not row["is_active"] or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = create_session(conn, row["id"])
    return {"token": token, "user": _public_user(row)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if token:
        with writable_conn() as conn:
            delete_session(conn, token)


@router.get("/auth/me")
def me(user=Depends(require_user)):
    return _public_user(_row(user))


def _row(user: dict):
    with writable_conn() as conn:
        return get_user_by_id(conn, user["id"])


def _conn():  # legacy shim kept for reference; unused
    raise NotImplementedError


@router.get("/admin/users", dependencies=[Depends(admin_only)])
def admin_list_users():
    with writable_conn() as conn:
        return {"users": [_public_user(r) for r in list_users(conn)]}


@router.post("/admin/users", status_code=201, dependencies=[Depends(admin_only)])
def admin_create_user(body: UserCreateBody):
    with writable_conn() as conn:
        if get_user_by_username(conn, body.username) is not None:
            raise HTTPException(status_code=409, detail="username exists")
        if body.role not in ("admin", "user"):
            raise HTTPException(status_code=422, detail="role must be admin or user")
        row = create_user(conn, body.username, body.display_name, body.password, role=body.role)
    return _public_user(row)


@router.patch("/admin/users/{user_id}", dependencies=[Depends(admin_only)])
def admin_patch_user(user_id: str, body: UserPatchBody):
    with writable_conn() as conn:
        row = get_user_by_id(conn, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no such user")
        if body.is_active is not None:
            conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(body.is_active), user_id))
        if body.role is not None:
            if body.role not in ("admin", "user"):
                raise HTTPException(status_code=422, detail="role must be admin or user")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
        if body.new_password:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), user_id))
        row = get_user_by_id(conn, user_id)
    return _public_user(row)


@router.get("/me/settings/{key}")
def get_user_setting(key: str, user=Depends(require_user)):
    with writable_conn() as conn:
        return {"key": key, "value": get_setting(conn, user["id"], key)}


@router.put("/me/settings/{key}")
def put_user_setting(key: str, body: SettingsBody, user=Depends(require_user)):
    with writable_conn() as conn:
        set_setting(conn, user["id"], key, body.value)
    return {"key": key, "value": body.value}
