from __future__ import annotations

from harness_test.fixture.app_client import auth_headers


def _mock_retrieve(monkeypatch, items=None):
    from common.models import RetrievalResult

    results = items or [
        RetrievalResult(
            doc_id="doc-1",
            content="差旅报销标准：市内交通按制度报销。",
            score=0.91,
            source_path="mock://policy",
            metadata={"retrieval": "mock"},
        )
    ]

    monkeypatch.setattr("agent_server.tools.business_tools.retrieve", lambda query, top_k=5: results[:top_k])
    return results


def test_auth_register_login_and_me(api_client):
    headers = auth_headers(api_client, "alice")

    me = api_client.get("/api/auth/me", headers=headers)

    assert me.status_code == 200, me.text
    data = me.json()["data"]
    assert data["username"] == "alice"
    assert data["tier"] == "employee"
    assert "doc_retrieve" in data["tools"]


def test_rbac_employee_and_admin_tool_visibility(api_client):
    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")

    denied = api_client.post("/api/tools/export_ticket_stat", json={}, headers=employee_headers)
    allowed = api_client.post("/api/tools/export_ticket_stat", json={}, headers=admin_headers)

    assert denied.status_code == 403
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["total"] == 0


def test_rag_tool_returns_mocked_retrieval_results(api_client, monkeypatch):
    expected = _mock_retrieve(monkeypatch)
    headers = auth_headers(api_client, "alice")

    response = api_client.post("/api/tools/doc_retrieve", json={"query": "差旅报销", "top_k": 1}, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == [item.model_dump() for item in expected]


def test_tools_create_and_query_ticket(api_client):
    headers = auth_headers(api_client, "alice")

    created = api_client.post(
        "/api/tools/create_consult_ticket",
        json={"title": "报销咨询", "content": "交通费怎么报销", "answer": "按制度提交。"},
        headers=headers,
    )
    listed = api_client.post("/api/tools/query_ticket_list", json={"mine_only": True}, headers=headers)

    assert created.status_code == 200, created.text
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["items"][0]["title"] == "报销咨询"


def test_graph_chat_suggests_ticket_and_saves_history(api_client, monkeypatch):
    _mock_retrieve(monkeypatch)
    headers = auth_headers(api_client, "alice")

    chat = api_client.post("/api/chat", json={"message": "差旅交通费怎么报销"}, headers=headers)
    history = api_client.get("/api/chat/history", headers=headers)

    assert chat.status_code == 200, chat.text
    assert chat.json()["data"]["answer"]
    assert chat.json()["data"]["ticket_id"] is None
    assert chat.json()["data"]["ticket_suggestion"]["recommended"] is True
    assert history.status_code == 200, history.text
    assert history.json()["data"]["items"][0]["question"] == "差旅交通费怎么报销"


def test_api_stream_chat_returns_tool_and_done_events(api_client, monkeypatch):
    _mock_retrieve(monkeypatch)
    headers = auth_headers(api_client, "alice")

    with api_client.stream("POST", "/api/chat/stream", json={"message": "差旅制度"}, headers=headers) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: tool" in body
    assert "event: done" in body
