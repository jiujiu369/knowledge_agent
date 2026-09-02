from __future__ import annotations


def test_web_smoke_uses_precreated_admin_credentials(monkeypatch):
    """Web smoke 必须使用环境变量提供的预创建管理员，不调用公共注册。"""
    import web.smoke_test as smoke

    monkeypatch.setenv("KNOWLEDGE_AGENT_SMOKE_ADMIN_USERNAME", "precreated-admin")
    monkeypatch.setenv("KNOWLEDGE_AGENT_SMOKE_ADMIN_PASSWORD", "ConfiguredOnly123!")

    register_calls: list[tuple[str, str]] = []
    login_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(smoke, "_register", lambda username, role: register_calls.append((username, role)))
    monkeypatch.setattr(
        smoke,
        "_login",
        lambda username, password=smoke.PASSWORD: login_calls.append((username, password)) or "token",
    )
    monkeypatch.setattr(smoke, "auth_headers", lambda token: {"Authorization": f"Bearer {token}"})

    token, headers = smoke._prepare_admin("legacy-admin")

    assert register_calls == []
    assert login_calls == [("precreated-admin", "ConfiguredOnly123!")]
    assert token == "token"
    assert headers == {"Authorization": "Bearer token"}
