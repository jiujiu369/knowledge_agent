from __future__ import annotations

import pytest

from harness_test.fixture.app_client import auth_headers


def _conversation(api_client, headers):
    """创建当前测试用户的空白会话。

    :param api_client: 隔离的接口测试客户端。
    :param headers: 当前测试用户的认证请求头。
    :return: 返回新建会话数据。
    """
    response = api_client.post("/api/chat/conversations", json={}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_ticket_list_and_detail_include_server_resolved_creator(api_client):
    """验证工单列表和详情返回后端关联得到的创建人。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证公开字段。
    """
    import agent_server.core.db as db

    alice_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    alice = api_client.get("/api/auth/me", headers=alice_headers).json()["data"]
    ticket = db.create_ticket("请假申请", "回家", alice["id"], ticket_type="leave")

    listed = api_client.get("/api/tickets", headers=admin_headers).json()["data"]["items"][0]
    detail = api_client.get(f"/api/tickets/{ticket['id']}", headers=admin_headers).json()["data"]

    for item in (listed, detail):
        assert item["creator_id"] == alice["id"]
        assert item["creator_username"] == "alice"
        assert "password_hash" not in item


def test_ticket_creator_cannot_be_forged_and_other_ticket_stays_private(api_client):
    """验证前端无法伪造创建人且工单继续保持用户隔离。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证创建人和权限。
    """
    alice_headers = auth_headers(api_client, "alice")
    bob_headers = auth_headers(api_client, "bob")
    created = api_client.post(
        "/api/tickets",
        json={"title": "咨询", "content": "内容", "answer": "", "creator_username": "bob"},
        headers=alice_headers,
    ).json()["data"]

    assert created["creator_username"] == "alice"
    assert api_client.get(f"/api/tickets/{created['id']}", headers=bob_headers).status_code == 404


def test_soft_deleted_ticket_creator_has_explicit_historical_label(api_client):
    """验证软删除账号的历史工单显示可识别创建人。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证历史标签。
    """
    import agent_server.core.db as db

    alice_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")
    alice = api_client.get("/api/auth/me", headers=alice_headers).json()["data"]
    ticket = db.create_ticket("旧请假", "旧内容", alice["id"], ticket_type="leave")
    assert db.delete_user(alice["id"])

    item = api_client.get(f"/api/tickets/{ticket['id']}", headers=admin_headers).json()["data"]
    assert item["creator_username"] == "账号已删除（原用户名：alice）"


def test_conversation_messages_support_complete_cursor_pagination(api_client):
    """验证指定会话的全部记录可通过游标分页读取。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证分页完整性和顺序。
    """
    import agent_server.core.db as db

    headers = auth_headers(api_client, "alice")
    user = api_client.get("/api/auth/me", headers=headers).json()["data"]
    conversation = _conversation(api_client, headers)
    for index in range(5):
        db.create_chat_history(user["id"], f"问题{index}", f"回答{index}", conversation_id=conversation["id"])

    newest = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages?limit=2", headers=headers
    ).json()["data"]
    older = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages?limit=2&before_id={newest['items'][0]['id']}",
        headers=headers,
    ).json()["data"]
    oldest = api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages?limit=2&before_id={older['items'][0]['id']}",
        headers=headers,
    ).json()["data"]

    combined = oldest["items"] + older["items"] + newest["items"]
    assert [item["question"] for item in combined] == [f"问题{i}" for i in range(5)]
    assert newest["has_more"] is True
    assert older["has_more"] is True
    assert oldest["has_more"] is False


def test_delete_own_history_keeps_ticket_and_empty_conversation(api_client):
    """验证删除自己的单轮问答仍保留工单和空会话。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证数据生命周期。
    """
    import agent_server.core.db as db

    headers = auth_headers(api_client, "alice")
    user = api_client.get("/api/auth/me", headers=headers).json()["data"]
    conversation = _conversation(api_client, headers)
    ticket = db.create_ticket("保留", "内容", user["id"])
    history = db.create_chat_history(
        user["id"], "唯一问题", "唯一回答", ticket_id=ticket["id"], conversation_id=conversation["id"]
    )

    deleted = api_client.delete(f"/api/chat/history/{history['id']}", headers=headers)

    assert deleted.status_code == 200, deleted.text
    assert api_client.delete(f"/api/chat/history/{history['id']}", headers=headers).status_code == 404
    assert db.get_ticket(ticket["id"], user) is not None
    remaining = api_client.get("/api/chat/conversations", headers=headers).json()["data"]["items"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == conversation["id"]
    assert remaining[0]["title"] == "新对话"


def test_user_and_admin_cannot_delete_another_users_history(api_client):
    """验证普通用户和管理员均不能删除其他用户私人记录。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证删除权限。
    """
    import agent_server.core.db as db

    alice_headers = auth_headers(api_client, "alice")
    bob_headers = auth_headers(api_client, "bob")
    admin_headers = auth_headers(api_client, "root", role="admin")
    alice = api_client.get("/api/auth/me", headers=alice_headers).json()["data"]
    conversation = _conversation(api_client, alice_headers)
    history = db.create_chat_history(alice["id"], "私密", "回答", conversation_id=conversation["id"])

    assert api_client.delete(f"/api/chat/history/{history['id']}", headers=bob_headers).status_code == 404
    assert api_client.delete(f"/api/chat/history/{history['id']}", headers=admin_headers).status_code == 404
    assert api_client.get(
        f"/api/chat/conversations/{conversation['id']}/messages", headers=alice_headers
    ).json()["data"]["items"]


def test_chat_history_rejects_conversation_owned_by_another_user(api_client):
    """验证数据库层拒绝把聊天记录写入其他用户会话。

    :param api_client: 隔离的接口测试客户端。
    :return: 无返回值；函数通过断言验证同一用户约束。
    """
    import agent_server.core.db as db

    alice_headers = auth_headers(api_client, "alice")
    bob_headers = auth_headers(api_client, "bob")
    alice = api_client.get("/api/auth/me", headers=alice_headers).json()["data"]
    bob_conversation = _conversation(api_client, bob_headers)

    with pytest.raises(ValueError, match="conversation not found"):
        db.create_chat_history(
            alice["id"], "错误归属", "不应保存", conversation_id=bob_conversation["id"]
        )


def test_display_numbers_are_contiguous_without_changing_real_ids():
    """验证界面序号连续且不会修改真实会话编号。

    :return: 无返回值；函数通过断言验证显示映射。
    """
    from web.app import conversation_display_items

    conversations = [
        {"id": 41, "sequence_no": 13, "title": "第三个", "created_at": "2026-01-03"},
        {"id": 7, "sequence_no": 1, "title": "新对话 1", "created_at": "2026-01-01"},
        {"id": 19, "sequence_no": 12, "title": "第二个", "created_at": "2026-01-02"},
    ]

    items = conversation_display_items(conversations)

    assert [(item["id"], item["display_no"], item["display_title"]) for item in items] == [
        (7, 1, "新对话"),
        (19, 2, "第二个"),
        (41, 3, "第三个"),
    ]
