from __future__ import annotations

import getpass
import hmac
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_server.core.auth import register_user


AdminCreator = Callable[[str, str], dict[str, Any]]


def bootstrap_admin(
    username: str,
    password: str,
    register: Callable[[str, str, str], dict[str, Any]] = register_user,
) -> dict[str, Any]:
    """通过受信任的服务端认证逻辑创建管理员。

    :param username: 待创建的管理员用户名。
    :param password: 仅存在于当前进程内存中的管理员密码。
    :param register: 实际执行用户创建的服务端函数。
    :return: 返回服务端创建的管理员用户信息。
    :raises ValueError: 当用户名或密码不符合现有账号长度约束时抛出。
    """
    normalized_username = username.strip()
    if not 3 <= len(normalized_username) <= 64:
        raise ValueError("管理员用户名长度必须为 3 到 64 个字符")
    if not 8 <= len(password) <= 128:
        raise ValueError("管理员密码长度必须为 8 到 128 个字符")
    return register(normalized_username, password, "admin")


def run_interactive(
    username_reader: Callable[[str], str] = input,
    password_reader: Callable[[str], str] = getpass.getpass,
    create_admin: AdminCreator = bootstrap_admin,
) -> int:
    """交互读取管理员凭据并执行一次性初始化。

    :param username_reader: 读取非敏感用户名的输入函数。
    :param password_reader: 以无回显方式读取密码的输入函数。
    :param create_admin: 创建管理员的可测试服务函数。
    :return: 创建成功返回 ``0``，输入或服务端校验失败返回 ``1``。
    """
    username = username_reader("管理员用户名: ").strip()
    password = password_reader("管理员密码: ")
    confirmation = password_reader("再次输入管理员密码: ")
    if not hmac.compare_digest(password.encode("utf-8"), confirmation.encode("utf-8")):
        print("管理员密码两次输入不一致", file=sys.stderr)
        return 1

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    previous_umask = os.umask(0o027)
    try:
        user = create_admin(username, password)
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        print(f"管理员创建失败: {detail}", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)

    print(f"管理员已创建: {user['username']} (admin)")
    return 0


def main() -> int:
    """拒绝命令行凭据并在真实终端中启动安全交互流程。

    :return: 交互完成时返回其状态码，参数或终端不安全时返回 ``2``。
    """
    if len(sys.argv) != 1:
        print("此命令不接受参数；用户名和密码必须在交互提示中输入", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print("此命令需要可关闭密码回显的交互式终端", file=sys.stderr)
        return 2
    return run_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
