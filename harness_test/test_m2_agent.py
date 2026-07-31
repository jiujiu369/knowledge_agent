from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setenv("AGNES_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AGNES_MODEL", "agnes-2.0-flash")

    import agent_server.core.db as db

    db.reset_db_for_tests()

    import agent_server.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_agnes_config_is_lazy_and_has_expected_defaults(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.setenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    monkeypatch.setenv("AGNES_MODEL", "agnes-2.0-flash")
    monkeypatch.delenv("ARK_BASE_URL", raising=False)
    monkeypatch.delenv("ARK_MODEL", raising=False)

    from agent_server.core.config import get_llm_settings

    settings = get_llm_settings(validate_key=False)
    assert settings.base_url == "https://apihub.agnes-ai.com/v1"
    assert settings.model == "agnes-2.0-flash"

    monkeypatch.setenv("AGNES_API_KEY", "")
    monkeypatch.setenv("ARK_API_KEY", "")
    try:
        get_llm_settings(validate_key=True)
    except RuntimeError as exc:
        assert "AGNES_API_KEY" in str(exc) or "ARK_API_KEY" in str(exc)
    else:
        raise AssertionError("missing AGNES_API_KEY must fail at request time")


def test_register_login_chat_ticket_and_rbac(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "已检索制度并创建咨询工单", "needs_ticket": True, "title": "差旅咨询"},
    )

    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "Passw0rd!", "role": "employee"},
    )
    assert register.status_code == 200

    login = client.post("/api/auth/login", json={"username": "alice", "password": "Passw0rd!"})
    assert login.status_code == 200
    token = login.json()["data"]["token"]

    auth_headers = {"Authorization": f"Bearer {token}"}
    chat = client.post("/api/chat", json={"message": "差旅报销上限多少"}, headers=auth_headers)
    assert chat.status_code == 200
    assert chat.json()["data"]["ticket_id"] is None
    assert chat.json()["data"]["ticket_suggestion"]["recommended"] is True
    assert chat.json()["data"]["guardrail"]["risk_score"] >= 0

    tickets = client.get("/api/tickets", headers=auth_headers)
    assert tickets.status_code == 200
    assert tickets.json()["data"]["items"] == []

    created = client.post(
        "/api/tickets",
        json=chat.json()["data"]["ticket_suggestion"],
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["status"] == "pending"

    unauth = client.get("/api/tickets")
    assert unauth.status_code == 401

    forbidden = client.post("/api/tools/export_ticket_stat", json={}, headers=auth_headers)
    assert forbidden.status_code == 403

    client.post(
        "/api/auth/register",
        json={"username": "root", "password": "Passw0rd!", "role": "admin"},
    )
    admin_login = client.post("/api/auth/login", json={"username": "root", "password": "Passw0rd!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['token']}"}
    export = client.post("/api/tools/export_ticket_stat", json={}, headers=admin_headers)
    assert export.status_code == 200


def test_sse_stream_returns_tool_events(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    import agent_server.graph_flow.graph_nodes as graph_nodes

    monkeypatch.setattr(
        graph_nodes,
        "decide_with_llm",
        lambda question, context: {"answer": "流式回答", "needs_ticket": True, "title": "流式咨询"},
    )
    client.post("/api/auth/register", json={"username": "bob", "password": "Passw0rd!", "role": "employee"})
    login = client.post("/api/auth/login", json={"username": "bob", "password": "Passw0rd!"})
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    with client.stream("POST", "/api/chat/stream", json={"message": "技术故障怎么处理"}, headers=headers) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: tool" in body
    assert "event: done" in body
