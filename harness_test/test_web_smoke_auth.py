from __future__ import annotations


def test_web_smoke_uses_precreated_admin_credentials(monkeypatch):
    """验证 Web 冒烟测试使用预创建管理员且不调用公共注册。

    :param monkeypatch: pytest 提供的环境变量和属性替换夹具。
    :return: 无返回值；冒烟测试仍尝试公共注册时断言失败。
    """
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
