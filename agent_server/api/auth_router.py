from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agent_server.api.utils import ok
from agent_server.core import db
from agent_server.core.auth import (
    admin_create_user,
    admin_delete_user,
    admin_reset_password,
    change_password,
    get_current_user,
    login_user,
    register_user,
)
from agent_server.core.rbac import available_tools, role_tier
from agent_server.tools.schemas import validate_user_text


router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: str = "employee"

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str) -> str:
        return validate_user_text(value)


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: str = "employee"

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str) -> str:
        return validate_user_text(value)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


def require_admin(current_user: dict) -> None:
    if role_tier(current_user["role"]) != "admin":
        raise HTTPException(status_code=403, detail="admin only")


@router.post("/register")
def register(payload: RegisterRequest):
    user = register_user(payload.username, payload.password, payload.role)
    return ok({"id": user["id"], "username": user["username"], "role": user["role"]})


@router.post("/login")
def login(payload: LoginRequest):
    user = login_user(payload.username, payload.password)
    return ok({"token": user["token"], "role": user["role"], "tier": role_tier(user["role"])})


@router.get("/me")
def me(current_user: Annotated[dict, Depends(get_current_user)]):
    return ok(
        {
            "id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "tier": role_tier(current_user["role"]),
            "tools": sorted(available_tools(current_user["role"])),
        }
    )


@router.get("/admin/users")
def list_admin_users(current_user: Annotated[dict, Depends(get_current_user)]):
    require_admin(current_user)
    return ok({"items": db.list_users()})


@router.post("/admin/users")
def create_admin_user(payload: AdminCreateUserRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    require_admin(current_user)
    user = admin_create_user(payload.username, payload.role, password="123456")
    return ok({"id": user["id"], "username": user["username"], "role": user["role"], "default_password": "123456"})


@router.post("/admin/users/{user_id}/reset-password")
def reset_admin_user_password(user_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    require_admin(current_user)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot reset current user")
    admin_reset_password(user_id, password="123456")
    return ok({"id": user_id, "default_password": "123456"})


@router.delete("/admin/users/{user_id}")
def delete_admin_user(user_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    require_admin(current_user)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot delete current user")
    admin_delete_user(user_id)
    return ok({"id": user_id, "deleted": True})


@router.post("/change-password")
def change_current_password(payload: ChangePasswordRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    change_password(current_user, payload.old_password, payload.new_password)
    return ok({"changed": True})
