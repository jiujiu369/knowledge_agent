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
        """用户名`valid`。

        :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
        :return: 返回用户名`valid`得到的结果，返回类型为 ``str``。
        """
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
        """用户名`valid`。

        :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
        :return: 返回用户名`valid`得到的结果，返回类型为 ``str``。
        """
        return validate_user_text(value)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


def require_admin(current_user: dict) -> None:
    """`require`管理员。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if role_tier(current_user["role"]) != "admin":
        raise HTTPException(status_code=403, detail="admin only")


@router.post("/register")
def register(payload: RegisterRequest):
    """注册。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``RegisterRequest``。
    :return: 返回注册得到的处理结果；具体类型由实际执行分支决定。
    """
    user = register_user(payload.username, payload.password, payload.role)
    return ok({"id": user["id"], "username": user["username"], "role": user["role"]})


@router.post("/login")
def login(payload: LoginRequest):
    """执行登录。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``LoginRequest``。
    :return: 返回执行登录得到的处理结果；具体类型由实际执行分支决定。
    """
    user = login_user(payload.username, payload.password)
    return ok({"token": user["token"], "role": user["role"], "tier": role_tier(user["role"])})


@router.get("/me")
def me(current_user: Annotated[dict, Depends(get_current_user)]):
    """`me`。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回`me`得到的处理结果；具体类型由实际执行分支决定。
    """
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
    """查询列表管理员`users`。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回查询列表管理员`users`得到的处理结果；具体类型由实际执行分支决定。
    """
    require_admin(current_user)
    return ok({"items": db.list_users()})


@router.post("/admin/users")
def create_admin_user(payload: AdminCreateUserRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """创建管理员用户。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``AdminCreateUserRequest``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回创建管理员用户得到的处理结果；具体类型由实际执行分支决定。
    """
    require_admin(current_user)
    user = admin_create_user(payload.username, payload.role, password="123456")
    return ok({"id": user["id"], "username": user["username"], "role": user["role"], "default_password": "123456"})


@router.post("/admin/users/{user_id}/reset-password")
def reset_admin_user_password(user_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """重置管理员用户密码。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回重置管理员用户密码得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    require_admin(current_user)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot reset current user")
    admin_reset_password(user_id, password="123456")
    return ok({"id": user_id, "default_password": "123456"})


@router.delete("/admin/users/{user_id}")
def delete_admin_user(user_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """删除管理员用户。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回删除管理员用户得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    require_admin(current_user)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot delete current user")
    admin_delete_user(user_id)
    return ok({"id": user_id, "deleted": True})


@router.post("/change-password")
def change_current_password(payload: ChangePasswordRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """修改当前密码。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``ChangePasswordRequest``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回修改当前密码得到的处理结果；具体类型由实际执行分支决定。
    """
    change_password(current_user, payload.old_password, payload.new_password)
    return ok({"changed": True})
