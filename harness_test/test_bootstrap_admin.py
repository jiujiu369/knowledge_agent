from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_bootstrap_admin_creates_login_capable_admin_with_server_auth(tmp_path: Path, monkeypatch) -> None:
    """验证初始化函数通过服务端认证逻辑创建可登录管理员。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的环境变量替换夹具。
    :return: 无返回值；管理员无法登录或角色错误时断言失败。
    """
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    import agent_server.core.db as db

    db.reset_db_for_tests()
    bootstrap = importlib.import_module("scripts.bootstrap_admin")
    user = bootstrap.bootstrap_admin("local_admin", "StrongPass123!")

    from agent_server.core.auth import login_user

    logged_in = login_user("local_admin", "StrongPass123!")
    assert user["role"] == "admin"
    assert logged_in["role"] == "admin"


def test_interactive_bootstrap_uses_getpass_confirmation_and_never_prints_password(capsys) -> None:
    """验证交互流程仅通过无回显读取密码且输出不包含密码。

    :param capsys: pytest 提供的标准输出与错误输出捕获夹具。
    :return: 无返回值；密码读取、角色或输出泄密不符合要求时断言失败。
    """
    bootstrap = importlib.import_module("scripts.bootstrap_admin")
    secret = "NoEchoPass123!"
    prompts: list[str] = []
    calls: list[tuple[str, str]] = []

    def read_password(prompt: str) -> str:
        """记录密码提示并返回测试密码。

        :param prompt: 无回显密码提示文本。
        :return: 返回固定测试密码。
        """
        prompts.append(prompt)
        return secret

    def create_admin(username: str, password: str) -> dict[str, str]:
        """记录初始化请求并返回最小用户结果。

        :param username: 待创建的管理员用户名。
        :param password: 无回显读取的管理员密码。
        :return: 返回用于交互成功输出的用户信息。
        """
        calls.append((username, password))
        return {"username": username, "role": "admin"}

    result = bootstrap.run_interactive(
        username_reader=lambda _prompt: "ops_admin",
        password_reader=read_password,
        create_admin=create_admin,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert len(prompts) == 2
    assert calls == [("ops_admin", secret)]
    assert secret not in captured.out
    assert secret not in captured.err


def test_interactive_bootstrap_rejects_password_mismatch_without_calling_server(capsys) -> None:
    """验证两次密码不一致时不会调用服务端创建逻辑。

    :param capsys: pytest 提供的标准输出与错误输出捕获夹具。
    :return: 无返回值；不一致密码仍创建账号或发生泄密时断言失败。
    """
    bootstrap = importlib.import_module("scripts.bootstrap_admin")
    secrets = iter(("FirstPass123!", "SecondPass123!"))
    called = False

    def create_admin(_username: str, _password: str) -> dict[str, str]:
        """标记不应发生的服务端创建调用。

        :param _username: 待创建的管理员用户名。
        :param _password: 待创建的管理员密码。
        :return: 返回占位用户结果。
        """
        nonlocal called
        called = True
        return {"username": "unexpected", "role": "admin"}

    result = bootstrap.run_interactive(
        username_reader=lambda _prompt: "ops_admin",
        password_reader=lambda _prompt: next(secrets),
        create_admin=create_admin,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert called is False
    assert "FirstPass123!" not in captured.out + captured.err
    assert "SecondPass123!" not in captured.out + captured.err


def test_main_rejects_command_line_credentials_without_echoing_them(monkeypatch, capsys) -> None:
    """验证命令行参数被拒绝且不会在错误输出中回显凭据。

    :param monkeypatch: pytest 提供的进程参数替换夹具。
    :param capsys: pytest 提供的标准输出与错误输出捕获夹具。
    :return: 无返回值；脚本接受参数或回显潜在密码时断言失败。
    """
    bootstrap = importlib.import_module("scripts.bootstrap_admin")
    secret = "HistoryLeak123!"
    monkeypatch.setattr(sys, "argv", ["bootstrap_admin.py", "--password", secret])

    result = bootstrap.main()

    captured = capsys.readouterr()
    assert result == 2
    assert secret not in captured.out + captured.err


def test_interactive_bootstrap_accepts_matching_unicode_password(capsys) -> None:
    """验证无回显确认支持包含非 ASCII 字符的强密码。

    :param capsys: pytest 提供的标准输出与错误输出捕获夹具。
    :return: 无返回值；Unicode 密码比较报错或泄密时断言失败。
    """
    bootstrap = importlib.import_module("scripts.bootstrap_admin")
    secret = "安全Pass123!"
    received: list[str] = []

    def create_admin(username: str, password: str) -> dict[str, str]:
        """记录 Unicode 密码并返回最小管理员结果。

        :param username: 待创建的管理员用户名。
        :param password: 无回显读取的 Unicode 密码。
        :return: 返回用于交互成功输出的管理员信息。
        """
        received.append(password)
        return {"username": username, "role": "admin"}

    result = bootstrap.run_interactive(
        username_reader=lambda _prompt: "ops_admin",
        password_reader=lambda _prompt: secret,
        create_admin=create_admin,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert received == [secret]
    assert secret not in captured.out + captured.err
