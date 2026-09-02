from __future__ import annotations

import json
import sqlite3

from harness_test.fixture.app_client import auth_headers


def _conversation(api_client, headers):
    """创建测试会话。

    :param api_client: 隔离 API 客户端。
    :param headers: 登录认证头。
    :return: 返回新建会话。
    """
    response = api_client.post("/api/chat/conversations", json={}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_repeated_request_id_saves_chat_only_once(api_client, monkeypatch):
    """验证重复请求标识只保存一次聊天。

    :param api_client: 隔离 API 客户端。
    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证幂等性。
    """
    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "幂等回答", "needs_ticket": False, "title": "幂等"},
    )
    headers = auth_headers(api_client, "alice")
    conversation = _conversation(api_client, headers)
    payload = {"message": "同一次提交", "conversation_id": conversation["id"], "request_id": "req-one"}

    first = api_client.post("/api/chat", json=payload, headers=headers)
    second = api_client.post("/api/chat", json=payload, headers=headers)
    history = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages", headers=headers
    ).json()["data"]["items"]

    assert first.status_code == second.status_code == 200
    assert len(history) == 1
    assert history[0]["request_id"] == "req-one"
    assert first.json()["data"]["chat_history_id"] == second.json()["data"]["chat_history_id"]


def test_same_question_with_different_request_ids_is_saved_twice(api_client, monkeypatch):
    """验证相同文本的不同请求可分别保存。

    :param api_client: 隔离 API 客户端。
    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证保存结果。
    """
    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "允许重复问题", "needs_ticket": False, "title": "重复"},
    )
    headers = auth_headers(api_client, "alice")
    conversation = _conversation(api_client, headers)

    for request_id in ("req-a", "req-b"):
        response = api_client.post(
            "/api/chat",
            json={"message": "完全相同的问题", "conversation_id": conversation["id"], "request_id": request_id},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    items = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages", headers=headers
    ).json()["data"]["items"]
    assert [item["request_id"] for item in items] == ["req-a", "req-b"]


def test_stream_done_contains_persisted_identifiers_and_answer(api_client, monkeypatch):
    """验证完成事件返回持久化标识和回答。

    :param api_client: 隔离 API 客户端。
    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证完成事件。
    """
    import agent_server.graph_flow.graph_nodes as graph_nodes
    from web.frontend_api import parse_sse_events

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "完整回答", "needs_ticket": False, "title": "完成"},
    )
    headers = auth_headers(api_client, "alice")
    conversation = _conversation(api_client, headers)

    with api_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "请回答", "conversation_id": conversation["id"], "request_id": "req-stream"},
        headers=headers,
    ) as response:
        events = list(parse_sse_events(response.iter_lines()))

    done = next(event["data"] for event in events if event["event"] == "done")
    assert done["request_id"] == "req-stream"
    assert done["conversation_id"] == conversation["id"]
    assert isinstance(done["chat_history_id"], int)
    assert done["answer"] == "完整回答"


def test_stream_failure_is_persisted_as_assistant_error(api_client, monkeypatch):
    """验证后端失败会保存对应助手错误。

    :param api_client: 隔离 API 客户端。
    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证失败持久化。
    """
    import agent_server.api.chat_router as chat_router
    from web.frontend_api import parse_sse_events

    def broken_events(*args, **kwargs):
        """模拟生成过程失败。

        :param args: 被替换函数的位置参数。
        :param kwargs: 被替换函数的关键字参数。
        :return: 无正常返回；函数抛出测试异常。
        """
        raise RuntimeError("backend exploded")
        yield

    monkeypatch.setattr(chat_router, "run_agent_events", broken_events)
    headers = auth_headers(api_client, "alice")
    conversation = _conversation(api_client, headers)
    with api_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "失败也要保留", "conversation_id": conversation["id"], "request_id": "req-fail"},
        headers=headers,
    ) as response:
        events = list(parse_sse_events(response.iter_lines()))

    done = next(event["data"] for event in events if event["event"] == "done")
    assert done["request_id"] == "req-fail"
    assert done["error"] is True
    assert done["answer"].startswith("请求失败：")
    history = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages", headers=headers
    ).json()["data"]["items"]
    assert history[0]["question"] == "失败也要保留"
    assert history[0]["answer"] == done["answer"]
    assert history[0]["is_error"] == 1


def test_delete_last_conversation_returns_exactly_one_replacement(api_client):
    """验证删除最后会话只补建一个会话。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证补建结果。
    """
    headers = auth_headers(api_client, "alice")
    conversation = _conversation(api_client, headers)

    deleted = api_client.delete(f"/api/chat/conversations/{conversation['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    data = deleted.json()["data"]
    assert data["deleted"]["id"] == conversation["id"]
    assert data["active_conversation"]["id"] != conversation["id"]
    assert data["created_replacement"] is True
    assert len(api_client.get("/api/chat/conversations", headers=headers).json()["data"]["items"]) == 1


def test_repeated_conversation_create_request_does_not_create_duplicate(api_client):
    """验证重复会话创建请求不会重复创建。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证幂等性。
    """
    headers = auth_headers(api_client, "alice")
    payload = {"request_id": "conversation-create-one"}
    first = api_client.post("/api/chat/conversations", json=payload, headers=headers)
    second = api_client.post("/api/chat/conversations", json=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len(api_client.get("/api/chat/conversations", headers=headers).json()["data"]["items"]) == 1


def test_ticket_migration_adds_consultation_type_without_data_loss(api_client):
    """验证普通工单具有兼容默认类型。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证默认类型。
    """
    import agent_server.core.db as db

    headers = auth_headers(api_client, "alice")
    user = api_client.get("/api/auth/me", headers=headers).json()["data"]
    ticket = db.create_ticket("旧工单", "旧内容", creator_id=user["id"])
    loaded = db.get_ticket(ticket["id"], user)
    assert loaded["ticket_type"] == "consultation"
    assert loaded["title"] == "旧工单"


def test_legacy_ticket_table_is_migrated_without_rebuild(tmp_path, monkeypatch):
    """验证旧工单表增量增加类型且不丢数据。

    :param tmp_path: pytest 隔离临时目录。
    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证旧库迁移。
    """
    db_file = tmp_path / "legacy-ticket.db"
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
            CREATE TABLE ticket (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                creator_id INTEGER NOT NULL,
                answer TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO user (id, username, password_hash, role, created_at)
            VALUES (1, 'legacy', 'hash', 'employee', '2026-01-01T00:00:00');
            INSERT INTO ticket (id, title, content, status, creator_id, created_at, updated_at)
            VALUES (9, '保留标题', '保留内容', 'pending', 1, '2026-01-02T00:00:00', '2026-01-02T00:00:00');
            """
        )
    monkeypatch.setenv("APP_DB_PATH", str(db_file))
    import agent_server.core.db as db

    db._POOL = None
    tickets = db.list_tickets({"id": 1})
    assert len(tickets) == 1
    assert tickets[0]["id"] == 9
    assert tickets[0]["ticket_type"] == "consultation"


def test_valid_leave_application_creates_structured_pending_ticket(api_client):
    """验证合法表单创建结构化待审批请假单。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证请假字段。
    """
    headers = auth_headers(api_client, "alice")
    payload = {
        "leave_type": "年假",
        "start_at": "2026-09-03T09:00:00",
        "end_at": "2026-09-04T18:00:00",
        "leave_days": 2,
        "reason": "家庭事务",
        "request_id": "leave-one",
    }
    response = api_client.post("/api/tickets/leave", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    ticket = response.json()["data"]
    assert ticket["ticket_type"] == "leave"
    assert ticket["status"] == "pending"
    assert ticket["leave_type"] == "年假"
    assert ticket["start_at"] == payload["start_at"]
    assert ticket["end_at"] == payload["end_at"]
    assert ticket["leave_days"] == 2
    assert ticket["leave_reason"] == "家庭事务"


def test_leave_application_rejects_invalid_values(api_client):
    """验证请假接口拒绝非法时间、天数、原因和类型。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证后端校验。
    """
    headers = auth_headers(api_client, "alice")
    base = {
        "leave_type": "病假",
        "start_at": "2026-09-04T09:00:00",
        "end_at": "2026-09-04T18:00:00",
        "leave_days": 1,
        "reason": "就医",
        "request_id": "leave-invalid",
    }
    invalid_payloads = [
        {**base, "end_at": "2026-09-03T18:00:00"},
        {**base, "leave_days": 0},
        {**base, "reason": "   "},
        {**base, "leave_type": "伪造类型"},
    ]
    for payload in invalid_payloads:
        response = api_client.post("/api/tickets/leave", json=payload, headers=headers)
        assert response.status_code == 422, response.text


def test_repeated_leave_request_id_does_not_create_duplicate(api_client):
    """验证重复请假提交不会创建两张工单。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证幂等性。
    """
    headers = auth_headers(api_client, "alice")
    payload = {
        "leave_type": "调休",
        "start_at": "2026-09-05T09:00:00",
        "end_at": "2026-09-05T18:00:00",
        "leave_days": 1,
        "reason": "调休一天",
        "request_id": "leave-repeat",
    }
    first = api_client.post("/api/tickets/leave", json=payload, headers=headers)
    second = api_client.post("/api/tickets/leave", json=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len(api_client.get("/api/tickets", headers=headers).json()["data"]["items"]) == 1


def test_employee_cannot_view_another_users_leave(api_client):
    """验证普通用户无法查看他人请假申请。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证数据隔离。
    """
    alice_headers = auth_headers(api_client, "alice")
    bob_headers = auth_headers(api_client, "bob")
    created = api_client.post(
        "/api/tickets/leave",
        json={
            "leave_type": "事假",
            "start_at": "2026-09-05T09:00:00",
            "end_at": "2026-09-05T18:00:00",
            "leave_days": 1,
            "reason": "个人事务",
            "request_id": "alice-leave",
        },
        headers=alice_headers,
    ).json()["data"]
    assert api_client.get(f"/api/tickets/{created['id']}", headers=bob_headers).status_code == 404
    assert api_client.get("/api/tickets", headers=bob_headers).json()["data"]["items"] == []


def test_admin_bulk_approves_only_pending_consultations(api_client):
    """验证批量审核只修改待审批普通咨询工单。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证批量边界。
    """
    import agent_server.core.db as db

    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    user = api_client.get("/api/auth/me", headers=employee_headers).json()["data"]
    pending_a = db.create_ticket("咨询 A", "A", user["id"], ticket_type="consultation")
    pending_b = db.create_ticket("咨询 B", "B", user["id"], ticket_type="consultation")
    approved = db.create_ticket("已批准", "C", user["id"], status="approved", ticket_type="consultation")
    rejected = db.create_ticket("已驳回", "D", user["id"], status="rejected", ticket_type="consultation")
    closed = db.create_ticket("已关闭", "E", user["id"], status="closed", ticket_type="consultation")
    leave = db.create_ticket("请假", "F", user["id"], ticket_type="leave")

    response = api_client.post("/api/tickets/bulk-approve-consultations", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data == {
        "matched_count": 2,
        "updated_count": 2,
        "updated_ticket_ids": [pending_a["id"], pending_b["id"]],
    }
    assert db.get_ticket(approved["id"], user)["status"] == "approved"
    assert db.get_ticket(rejected["id"], user)["status"] == "rejected"
    assert db.get_ticket(closed["id"], user)["status"] == "closed"
    assert db.get_ticket(leave["id"], user)["status"] == "pending"

    repeated = api_client.post("/api/tickets/bulk-approve-consultations", headers=admin_headers)
    assert repeated.json()["data"] == {
        "matched_count": 0,
        "updated_count": 0,
        "updated_ticket_ids": [],
    }


def test_non_admin_cannot_bulk_approve_consultations(api_client):
    """验证非管理员无法执行批量审核。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证权限。
    """
    headers = auth_headers(api_client, "alice")
    response = api_client.post("/api/tickets/bulk-approve-consultations", headers=headers)
    assert response.status_code == 403


def test_admin_bulk_marks_only_open_non_leave_tickets_processed_and_refreshes_views(api_client):
    """验证一键已处理的后端边界，以及列表和统计查询能立即看到更新。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证批量处理结果。
    """
    import agent_server.core.db as db

    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    user = api_client.get("/api/auth/me", headers=employee_headers).json()["data"]
    open_consultation = db.create_ticket(
        "待处理咨询", "A", user["id"], status="open", ticket_type="consultation"
    )
    open_leave = db.create_ticket(
        "待处理请假", "B", user["id"], status="open", ticket_type="leave"
    )
    approved = db.create_ticket(
        "已批准", "C", user["id"], status="approved", ticket_type="consultation"
    )
    closed = db.create_ticket(
        "已关闭", "D", user["id"], status="closed", ticket_type="consultation"
    )
    rejected = db.create_ticket(
        "已驳回", "E", user["id"], status="rejected", ticket_type="consultation"
    )

    response = api_client.post("/api/tickets/bulk-process-open", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "matched_count": 1,
        "updated_count": 1,
        "updated_ticket_ids": [open_consultation["id"]],
    }
    items = api_client.get("/api/tickets", headers=admin_headers).json()["data"]["items"]
    statuses = {item["id"]: item["status"] for item in items}
    assert statuses[open_consultation["id"]] == "processed"
    assert statuses[open_leave["id"]] == "open"
    assert statuses[approved["id"]] == "approved"
    assert statuses[closed["id"]] == "closed"
    assert statuses[rejected["id"]] == "rejected"

    statistics = api_client.post(
        "/api/tools/export_ticket_stat", json={}, headers=admin_headers
    ).json()["data"]
    assert statistics["by_status"]["processed"] == 1
    assert statistics["by_status"]["open"] == 1


def test_non_admin_cannot_bulk_process_open_tickets(api_client):
    """验证普通用户不能执行一键已处理。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证权限。
    """
    headers = auth_headers(api_client, "alice")
    response = api_client.post("/api/tickets/bulk-process-open", headers=headers)
    assert response.status_code == 403


def test_leave_can_still_be_reviewed_individually_by_admin(api_client):
    """验证管理员仍可逐条审核请假申请。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证逐条审核。
    """
    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    leave = api_client.post(
        "/api/tickets/leave",
        json={
            "leave_type": "婚假",
            "start_at": "2026-10-01T09:00:00",
            "end_at": "2026-10-03T18:00:00",
            "leave_days": 3,
            "reason": "结婚",
            "request_id": "leave-review",
        },
        headers=employee_headers,
    ).json()["data"]
    assert api_client.patch(
        f"/api/tickets/{leave['id']}", json={"status": "approved"}, headers=employee_headers
    ).status_code == 403
    reviewed = api_client.patch(
        f"/api/tickets/{leave['id']}", json={"status": "approved"}, headers=admin_headers
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["status"] == "approved"


def test_leave_review_only_accepts_approved_or_rejected_once(api_client):
    """验证请假单只能从待审批逐条批准或驳回一次。

    :param api_client: 隔离 API 客户端。
    :return: 无返回值；函数通过断言验证审核状态边界。
    """
    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    leave = api_client.post(
        "/api/tickets/leave",
        json={
            "leave_type": "其他",
            "start_at": "2026-10-05T09:00:00",
            "end_at": "2026-10-05T18:00:00",
            "leave_days": 1,
            "reason": "其他原因",
            "request_id": "leave-review-limits",
        },
        headers=employee_headers,
    ).json()["data"]
    assert api_client.patch(
        f"/api/tickets/{leave['id']}", json={"status": "closed"}, headers=admin_headers
    ).status_code == 400
    assert api_client.patch(
        f"/api/tickets/{leave['id']}", json={"status": "rejected"}, headers=admin_headers
    ).status_code == 200
    assert api_client.patch(
        f"/api/tickets/{leave['id']}", json={"status": "approved"}, headers=admin_headers
    ).status_code == 400
