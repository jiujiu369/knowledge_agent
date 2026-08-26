from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    """客户端。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录，类型为 ``Path``。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 返回客户端得到的处理结果；具体类型由实际执行分支决定。
    """
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setenv("AGNES_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AGNES_MODEL", "agnes-2.0-flash")

    import agent_server.core.db as db

    db.reset_db_for_tests()

    import agent_server.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_admin_creates_user_with_default_password_and_user_changes_password(tmp_path, monkeypatch):
    """验证管理员`creates`用户`with``default`密码`and`用户`changes`密码。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    client.post("/api/auth/register", json={"username": "root", "password": "Passw0rd!", "role": "admin"})
    admin_login = client.post("/api/auth/login", json={"username": "root", "password": "Passw0rd!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['token']}"}

    created = client.post(
        "/api/auth/admin/users",
        json={"username": "alice", "role": "employee"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"] == {"id": 2, "username": "alice", "role": "employee", "default_password": "123456"}

    login = client.post("/api/auth/login", json={"username": "alice", "password": "123456"})
    assert login.status_code == 200, login.text
    user_headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    changed = client.post(
        "/api/auth/change-password",
        json={"old_password": "123456", "new_password": "Newpass123"},
        headers=user_headers,
    )
    assert changed.status_code == 200, changed.text

    old_login = client.post("/api/auth/login", json={"username": "alice", "password": "123456"})
    assert old_login.status_code == 401
    new_login = client.post("/api/auth/login", json={"username": "alice", "password": "Newpass123"})
    assert new_login.status_code == 200

    reset = client.post("/api/auth/admin/users/2/reset-password", headers=admin_headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["data"] == {"id": 2, "default_password": "123456"}

    reset_login = client.post("/api/auth/login", json={"username": "alice", "password": "123456"})
    assert reset_login.status_code == 200, reset_login.text

    deleted = client.delete("/api/auth/admin/users/2", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"] == {"id": 2, "deleted": True}

    deleted_login = client.post("/api/auth/login", json={"username": "alice", "password": "123456"})
    assert deleted_login.status_code == 401
    users = client.get("/api/auth/admin/users", headers=admin_headers)
    assert users.status_code == 200, users.text
    assert [item["username"] for item in users.json()["data"]["items"]] == ["root"]


def test_employee_cannot_create_users(tmp_path, monkeypatch):
    """验证`employee``cannot`创建`users`。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    client.post("/api/auth/register", json={"username": "bob", "password": "Passw0rd!", "role": "employee"})
    login = client.post("/api/auth/login", json={"username": "bob", "password": "Passw0rd!"})
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    response = client.post(
        "/api/auth/admin/users",
        json={"username": "alice", "role": "employee"},
        headers=headers,
    )

    assert response.status_code == 403


def test_admin_cannot_delete_or_reset_self(tmp_path, monkeypatch):
    """验证管理员`cannot`删除`or`重置`self`。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    client.post("/api/auth/register", json={"username": "root", "password": "Passw0rd!", "role": "admin"})
    admin_login = client.post("/api/auth/login", json={"username": "root", "password": "Passw0rd!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['token']}"}

    reset = client.post("/api/auth/admin/users/1/reset-password", headers=admin_headers)
    deleted = client.delete("/api/auth/admin/users/1", headers=admin_headers)

    assert reset.status_code == 400
    assert deleted.status_code == 400
