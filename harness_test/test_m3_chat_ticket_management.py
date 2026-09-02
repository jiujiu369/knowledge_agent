from __future__ import annotations

import importlib
import sqlite3
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
    if role == "admin":
        from agent_server.core.auth import register_user

        register_user(username, "Passw0rd!", role)
    else:
        register = client.post(
            "/api/auth/register", json={"username": username, "password": "Passw0rd!", "role": role}
        )
        assert register.status_code == 200, register.text
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


def test_two_conversations_keep_messages_strictly_isolated(tmp_path, monkeypatch):
    """同一用户的两个会话只返回各自消息。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言两个会话消息隔离。
    """
    client = _client(tmp_path, monkeypatch)
    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": f"回答：{question}", "needs_ticket": False, "title": question},
    )
    headers = _register_and_login(client, "alice")
    first = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]
    second = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]

    assert client.post(
        "/api/chat", json={"message": "第一会话问题", "conversation_id": first["id"]}, headers=headers
    ).status_code == 200
    assert client.post(
        "/api/chat", json={"message": "第二会话问题", "conversation_id": second["id"]}, headers=headers
    ).status_code == 200

    first_messages = client.get(f"/api/chat/conversations/{first['id']}/messages", headers=headers).json()["data"]["items"]
    second_messages = client.get(f"/api/chat/conversations/{second['id']}/messages", headers=headers).json()["data"]["items"]
    assert [item["question"] for item in first_messages] == ["第一会话问题"]
    assert [item["question"] for item in second_messages] == ["第二会话问题"]


def test_llm_recent_history_only_uses_current_conversation(tmp_path, monkeypatch):
    """LLM 上下文不混入同一用户的其他会话。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言上下文隔离。
    """
    client = _client(tmp_path, monkeypatch)
    import agent_server.graph_flow.graph_nodes as graph_nodes

    contexts: list[tuple[str, str]] = []

    def decide(question, context):
        """记录模型收到的上下文。

        :param question: 当前问题。
        :param context: 当前会话上下文。
        :return: 返回固定测试决策。
        """
        contexts.append((question, context))
        return {"answer": "已回答", "needs_ticket": False, "title": question}

    monkeypatch.setattr(graph_nodes, "decide_with_llm", decide)
    headers = _register_and_login(client, "alice")
    first = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]
    second = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]
    client.post("/api/chat", json={"message": "机密的第一会话内容", "conversation_id": first["id"]}, headers=headers)
    client.post("/api/chat", json={"message": "第二会话问题", "conversation_id": second["id"]}, headers=headers)

    second_context = next(context for question, context in contexts if question == "第二会话问题")
    assert "机密的第一会话内容" not in second_context


def test_user_and_admin_cannot_read_another_users_conversation(tmp_path, monkeypatch):
    """会话所有权限制同样适用于管理员。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言跨用户读取被拒绝。
    """
    client = _client(tmp_path, monkeypatch)
    alice_headers = _register_and_login(client, "alice")
    bob_headers = _register_and_login(client, "bob")
    admin_headers = _register_and_login(client, "root", role="admin")
    conversation = client.post("/api/chat/conversations", json={}, headers=alice_headers).json()["data"]

    assert client.get(f"/api/chat/conversations/{conversation['id']}/messages", headers=bob_headers).status_code == 404
    assert client.get(f"/api/chat/conversations/{conversation['id']}/messages", headers=admin_headers).status_code == 404


def test_old_database_chat_history_is_migrated_without_data_loss(tmp_path, monkeypatch):
    """旧 chat_history 表增量增加会话字段并归入默认历史会话。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言旧记录迁移后仍可读取。
    """
    db_file = tmp_path / "legacy.db"
    with sqlite3.connect(db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                token TEXT UNIQUE,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                ticket_id INTEGER,
                tool_events TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            INSERT INTO user (id, username, password_hash, role, created_at)
            VALUES (1, 'legacy', 'hash', 'employee', '2026-01-01T00:00:00');
            INSERT INTO chat_history (user_id, question, answer, created_at)
            VALUES (1, '旧问题', '旧回答', '2026-01-02T00:00:00');
            """
        )

    monkeypatch.setenv("APP_DB_PATH", str(db_file))
    import agent_server.core.db as db

    db._POOL = None
    migrated = db.list_conversations({"id": 1})
    assert len(migrated) == 1
    assert migrated[0]["title"] == "历史对话"
    messages = db.list_chat_history({"id": 1}, conversation_id=migrated[0]["id"])
    assert [(item["question"], item["answer"]) for item in messages] == [("旧问题", "旧回答")]


def test_conversation_sequence_is_unique_per_user_and_starts_independently(tmp_path, monkeypatch):
    """每个用户独立、连续地获得持久化会话序号。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言用户级序号和默认标题。
    """
    client = _client(tmp_path, monkeypatch)
    alice_headers = _register_and_login(client, "alice")
    bob_headers = _register_and_login(client, "bob")

    alice = [client.post("/api/chat/conversations", json={}, headers=alice_headers).json()["data"] for _ in range(3)]
    bob = [client.post("/api/chat/conversations", json={}, headers=bob_headers).json()["data"] for _ in range(2)]

    assert [(item["sequence_no"], item["title"]) for item in alice] == [
        (1, "新对话"),
        (2, "新对话"),
        (3, "新对话"),
    ]
    assert [(item["sequence_no"], item["title"]) for item in bob] == [
        (1, "新对话"),
        (2, "新对话"),
    ]


def test_deleted_conversation_sequence_is_never_reused(tmp_path, monkeypatch):
    """删除会话后新建会话不会复用旧序号。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言序号单调增加。
    """
    client = _client(tmp_path, monkeypatch)
    headers = _register_and_login(client, "alice")
    first = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]
    second = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]

    deleted = client.delete(f"/api/chat/conversations/{second['id']}", headers=headers)
    third = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]

    assert deleted.status_code == 200, deleted.text
    assert first["sequence_no"] == 1
    assert second["sequence_no"] == 2
    assert third["sequence_no"] == 3


def test_conversation_delete_enforces_owner_and_admin_cannot_bypass(tmp_path, monkeypatch):
    """普通用户和管理员都不能删除其他用户的私人会话。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言删除接口执行所有权校验。
    """
    client = _client(tmp_path, monkeypatch)
    alice_headers = _register_and_login(client, "alice")
    bob_headers = _register_and_login(client, "bob")
    admin_headers = _register_and_login(client, "root", role="admin")
    conversation = client.post("/api/chat/conversations", json={}, headers=alice_headers).json()["data"]

    assert client.delete(f"/api/chat/conversations/{conversation['id']}", headers=bob_headers).status_code == 404
    assert client.delete(f"/api/chat/conversations/{conversation['id']}", headers=admin_headers).status_code == 404
    assert client.delete(f"/api/chat/conversations/{conversation['id']}", headers=alice_headers).status_code == 200


def test_deleting_conversation_removes_history_but_keeps_ticket(tmp_path, monkeypatch):
    """删除会话清除聊天记录，但不删除已经创建的工单。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言聊天与工单生命周期解耦。
    """
    client = _client(tmp_path, monkeypatch)
    import agent_server.core.db as db

    headers = _register_and_login(client, "alice")
    user = client.get("/api/auth/me", headers=headers).json()["data"]
    conversation = client.post("/api/chat/conversations", json={}, headers=headers).json()["data"]
    ticket = db.create_ticket("保留工单", "工单内容", creator_id=user["id"])
    db.create_chat_history(
        user["id"],
        "关联问题",
        "关联回答",
        ticket_id=ticket["id"],
        conversation_id=conversation["id"],
    )

    response = client.delete(f"/api/chat/conversations/{conversation['id']}", headers=headers)

    assert response.status_code == 200, response.text
    assert db.list_chat_history(user, conversation_id=conversation["id"]) == []
    assert db.get_ticket(ticket["id"], user) is not None


def test_existing_new_conversations_receive_stable_sequence_during_migration(tmp_path, monkeypatch):
    """旧数据库中的“新对话”会话获得稳定序号且消息不丢失。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言增量迁移结果。
    """
    db_file = tmp_path / "legacy-conversation.db"
    with sqlite3.connect(db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                token TEXT UNIQUE,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                ticket_id INTEGER,
                tool_events TEXT NOT NULL DEFAULT '[]',
                conversation_id INTEGER,
                created_at TEXT NOT NULL
            );
            INSERT INTO user (id, username, password_hash, role, created_at)
            VALUES (1, 'legacy', 'hash', 'employee', '2026-01-01T00:00:00');
            INSERT INTO conversation (id, user_id, title, created_at, updated_at)
            VALUES
                (10, 1, '新对话', '2026-01-02T00:00:00', '2026-01-02T00:00:00'),
                (11, 1, '新对话', '2026-01-03T00:00:00', '2026-01-03T00:00:00');
            INSERT INTO chat_history (user_id, question, answer, conversation_id, created_at)
            VALUES (1, '迁移问题', '迁移回答', 11, '2026-01-03T00:01:00');
            """
        )

    monkeypatch.setenv("APP_DB_PATH", str(db_file))
    import agent_server.core.db as db

    db._POOL = None
    conversations = sorted(db.list_conversations({"id": 1}), key=lambda item: item["sequence_no"])
    assert [(item["sequence_no"], item["title"]) for item in conversations] == [
        (1, "新对话"),
        (2, "新对话"),
    ]
    assert db.list_chat_history({"id": 1}, conversation_id=11)[0]["question"] == "迁移问题"
    assert db.create_conversation(1)["sequence_no"] == 3


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
