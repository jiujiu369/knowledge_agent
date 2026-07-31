from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException

from agent_server.core import db
from common.constants import ROLE_PERMISSIONS


PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def register_user(username: str, password: str, role: str = "employee") -> dict[str, Any]:
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="invalid role")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="username already exists")
    return db.create_user(username=username, password_hash=hash_password(password), role=role)


def admin_create_user(username: str, role: str = "employee", password: str = "123456") -> dict[str, Any]:
    return register_user(username=username, password=password, role=role)


def change_password(user: dict[str, Any], old_password: str, new_password: str) -> None:
    stored = db.get_user_by_username(user["username"])
    if not stored or not verify_password(old_password, stored["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid old password")
    db.update_user_password(user["id"], hash_password(new_password))


def admin_reset_password(user_id: int, password: str = "123456") -> None:
    if not db.update_user_password(user_id, hash_password(password)):
        raise HTTPException(status_code=404, detail="user not found")


def admin_delete_user(user_id: int) -> None:
    if not db.delete_user(user_id):
        raise HTTPException(status_code=404, detail="user not found")


def login_user(username: str, password: str) -> dict[str, Any]:
    user = db.get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = secrets.token_urlsafe(32)
    db.set_user_token(user["id"], token)
    user["token"] = token
    return user


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    return user
