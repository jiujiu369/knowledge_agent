from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def isolated_client(tmp_path: Path, monkeypatch: Any) -> TestClient:
    """`isolated`客户端。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录，类型为 ``Path``。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具，类型为 ``Any``。
    :return: 返回`isolated`客户端得到的结果，返回类型为 ``TestClient``。
    """
    datas_dir = tmp_path / "datas"
    chroma_dir = tmp_path / "chroma"
    db_path = tmp_path / "app.db"
    datas_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATAS_DIR", str(datas_dir))
    monkeypatch.setenv("CHROMA_DIR", str(chroma_dir))
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    monkeypatch.setenv("KNOWLEDGE_AGENT_MOCK_LLM", "1")
    monkeypatch.setenv("AGNES_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AGNES_MODEL", "mock-model")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    import common.constants as constants
    import agent_server.core.db as db
    import agent_server.api.utils as api_utils
    import agent_server.main as main_module

    importlib.reload(constants)
    db.reset_db_for_tests()
    api_utils._REQUESTS.clear()
    importlib.reload(main_module)

    return TestClient(main_module.app)


def auth_headers(client: TestClient, username: str, role: str = "employee", password: str = "Passw0rd!") -> dict[str, str]:
    """认证请求头。

    :param client: 函数处理所需的“客户端”数据，类型为 ``TestClient``。
    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :return: 返回认证请求头得到的结果，返回类型为 ``dict[str, str]``。
    """
    if role == "admin":
        from agent_server.core.auth import register_user

        register_user(username, password, role)
    else:
        register = client.post("/api/auth/register", json={"username": username, "password": password, "role": role})
        assert register.status_code == 200, register.text
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}
