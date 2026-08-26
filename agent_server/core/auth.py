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
    """计算哈希密码。

    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :return: 返回计算哈希密码得到的结果，返回类型为 ``str``。
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    """验证密码。

    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :param encoded: 函数处理所需的“`encoded`”数据，类型为 ``str``。
    :return: 返回验证密码得到的结果，返回类型为 ``bool``。
    """
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
    """注册用户。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回注册用户得到的结果，返回类型为 ``dict[str, Any]``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="invalid role")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="username already exists")
    return db.create_user(username=username, password_hash=hash_password(password), role=role)


def admin_create_user(username: str, role: str = "employee", password: str = "123456") -> dict[str, Any]:
    """管理员创建用户。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :return: 返回管理员创建用户得到的结果，返回类型为 ``dict[str, Any]``。
    """
    return register_user(username=username, password=password, role=role)


def change_password(user: dict[str, Any], old_password: str, new_password: str) -> None:
    """修改密码。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param old_password: 函数处理所需的“`old`密码”数据，类型为 ``str``。
    :param new_password: 函数处理所需的“`new`密码”数据，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    stored = db.get_user_by_username(user["username"])
    if not stored or not verify_password(old_password, stored["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid old password")
    db.update_user_password(user["id"], hash_password(new_password))


def admin_reset_password(user_id: int, password: str = "123456") -> None:
    """管理员重置密码。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not db.update_user_password(user_id, hash_password(password)):
        raise HTTPException(status_code=404, detail="user not found")


def admin_delete_user(user_id: int) -> None:
    """管理员删除用户。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not db.delete_user(user_id):
        raise HTTPException(status_code=404, detail="user not found")


def login_user(username: str, password: str) -> dict[str, Any]:
    """执行登录用户。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :return: 返回执行登录用户得到的结果，返回类型为 ``dict[str, Any]``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    user = db.get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = secrets.token_urlsafe(32)
    db.set_user_token(user["id"], token)
    user["token"] = token
    return user


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """获取当前用户。

    :param authorization: 函数处理所需的“`authorization`”数据，类型为 ``Annotated[str | None, Header()]``。
    :return: 返回获取当前用户得到的结果，返回类型为 ``dict[str, Any]``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    return user
