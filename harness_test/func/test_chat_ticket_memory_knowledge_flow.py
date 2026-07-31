from __future__ import annotations

from pathlib import Path

from harness_test.fixture.app_client import auth_headers


def test_chat_suggests_ticket_without_creating_one(api_client, monkeypatch):
    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "please create a ticket", "needs_ticket": True, "title": "network fault"},
    )

    headers = auth_headers(api_client, "alice")

    chat = api_client.post("/api/chat", json={"message": "my router is broken"}, headers=headers)
    tickets = api_client.get("/api/tickets", headers=headers)
    history = api_client.get("/api/chat/history", headers=headers)

    assert chat.status_code == 200, chat.text
    data = chat.json()["data"]
    assert data["ticket_id"] is None
    assert data["ticket_suggestion"] == {
        "recommended": True,
        "title": "network fault",
        "content": "my router is broken",
        "answer": "please create a ticket",
    }
    assert tickets.json()["data"]["items"] == []
    assert history.json()["data"]["items"][0]["ticket_id"] is None


def test_user_creates_pending_ticket_and_admin_approves(api_client):
    employee_headers = auth_headers(api_client, "alice")
    admin_headers = auth_headers(api_client, "root", role="admin")

    created = api_client.post(
        "/api/tickets",
        json={"title": "router fault", "content": "router is broken", "answer": "please check hardware"},
        headers=employee_headers,
    )

    assert created.status_code == 200, created.text
    ticket = created.json()["data"]
    assert ticket["status"] == "pending"
    assert ticket["metadata"]

    employee_patch = api_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "approved"}, headers=employee_headers)
    admin_patch = api_client.patch(f"/api/tickets/{ticket['id']}", json={"status": "approved"}, headers=admin_headers)

    assert employee_patch.status_code == 403
    assert admin_patch.status_code == 200, admin_patch.text
    assert admin_patch.json()["data"]["status"] == "approved"


def test_chat_uses_recent_history_as_context(api_client, monkeypatch):
    import agent_server.core.db as db
    import agent_server.graph_flow.graph_nodes as graph_nodes

    captured: dict[str, str] = {}

    def fake_decide(question: str, context: str):
        captured["context"] = context
        return {"answer": "memory answer", "needs_ticket": False, "title": "memory"}

    monkeypatch.setattr(graph_nodes, "decide_with_llm", fake_decide)
    headers = auth_headers(api_client, "alice")
    user = api_client.get("/api/auth/me", headers=headers).json()["data"]
    db.create_chat_history(user["id"], "first question", "first answer")

    response = api_client.post("/api/chat", json={"message": "what did I ask before"}, headers=headers)

    assert response.status_code == 200, response.text
    assert "first question" in captured["context"]
    assert "first answer" in captured["context"]


def test_admin_deletes_uploaded_document(api_client, tmp_path, monkeypatch):
    import agent_server.core.db as db
    import agent_server.tools.business_tools as business_tools

    calls: list[str] = []
    monkeypatch.setattr(business_tools, "rebuild_index", lambda: (None, [], None))

    admin_headers = auth_headers(api_client, "root", role="admin")
    source = tmp_path / "datas" / "delete-me.docx"
    source.write_bytes(b"fake docx")
    doc = db.upsert_doc(str(source), "delete-me.docx", chunk_count=3)

    response = api_client.delete(f"/api/knowledge/{doc['id']}", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["deleted"]["id"] == doc["id"]
    assert not source.exists()
    assert db.list_docs() == []
