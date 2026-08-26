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


def _register_and_login(client: TestClient, username: str, role: str = "employee") -> dict[str, str]:
    """注册`and`执行登录。

    :param client: 函数处理所需的“客户端”数据，类型为 ``TestClient``。
    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回注册`and`执行登录得到的结果，返回类型为 ``dict[str, str]``。
    """
    client.post("/api/auth/register", json={"username": username, "password": "Passw0rd!", "role": role})
    login = client.post("/api/auth/login", json={"username": username, "password": "Passw0rd!"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['data']['token']}"}


def test_chat_history_is_saved_for_current_user(tmp_path, monkeypatch):
    """验证处理对话历史记录判断`saved``for`当前用户。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "这是历史回答", "needs_ticket": True, "title": "历史咨询"},
    )

    alice_headers = _register_and_login(client, "alice")
    bob_headers = _register_and_login(client, "bob")

    chat = client.post("/api/chat", json={"message": "怎么查看年假"}, headers=alice_headers)
    assert chat.status_code == 200, chat.text

    alice_history = client.get("/api/chat/history", headers=alice_headers)
    bob_history = client.get("/api/chat/history", headers=bob_headers)

    assert alice_history.status_code == 200, alice_history.text
    assert bob_history.status_code == 200, bob_history.text
    assert alice_history.json()["data"]["items"][0]["question"] == "怎么查看年假"
    assert alice_history.json()["data"]["items"][0]["answer"] == "这是历史回答"
    assert alice_history.json()["data"]["items"][0]["ticket_id"] is None
    assert chat.json()["data"]["ticket_suggestion"]["recommended"] is True
    assert bob_history.json()["data"]["items"] == []


def test_stream_chat_history_is_saved_after_done_event(tmp_path, monkeypatch):
    """验证流式处理处理对话历史记录判断`saved``after``done`事件。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "流式历史回答", "needs_ticket": False, "title": "流式历史"},
    )
    headers = _register_and_login(client, "alice")

    with client.stream("POST", "/api/chat/stream", json={"message": "报销规则是什么"}, headers=headers) as response:
        assert response.status_code == 200, response.text
        assert "event: done" in "".join(response.iter_text())

    history = client.get("/api/chat/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["data"]["items"][0]["question"] == "报销规则是什么"
    assert history.json()["data"]["items"][0]["answer"] == "流式历史回答"


def test_admin_can_view_and_manage_all_tickets_while_users_only_see_their_own(tmp_path, monkeypatch):
    """验证管理员`can``view``and``manage``all``tickets``while``users``only``see``their``own`。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    client = _client(tmp_path, monkeypatch)

    import agent_server.core.db as db

    alice_headers = _register_and_login(client, "alice")
    bob_headers = _register_and_login(client, "bob")
    admin_headers = _register_and_login(client, "root", role="admin")

    alice = client.get("/api/auth/me", headers=alice_headers).json()["data"]
    bob = client.get("/api/auth/me", headers=bob_headers).json()["data"]
    db.create_ticket("Alice 工单", "Alice 内容", creator_id=alice["id"])
    bob_ticket = db.create_ticket("Bob 工单", "Bob 内容", creator_id=bob["id"])

    alice_list = client.get("/api/tickets", headers=alice_headers)
    bob_list = client.get("/api/tickets", headers=bob_headers)
    admin_list = client.get("/api/tickets", headers=admin_headers)

    assert [item["title"] for item in alice_list.json()["data"]["items"]] == ["Alice 工单"]
    assert [item["title"] for item in bob_list.json()["data"]["items"]] == ["Bob 工单"]
    assert {item["title"] for item in admin_list.json()["data"]["items"]} == {"Alice 工单", "Bob 工单"}

    forbidden = client.patch(f"/api/tickets/{bob_ticket['id']}", json={"status": "closed"}, headers=alice_headers)
    managed = client.patch(f"/api/tickets/{bob_ticket['id']}", json={"status": "closed"}, headers=admin_headers)

    assert forbidden.status_code == 403
    assert managed.status_code == 200, managed.text
    assert managed.json()["data"]["status"] == "closed"
