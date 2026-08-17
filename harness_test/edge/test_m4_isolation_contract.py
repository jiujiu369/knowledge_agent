from __future__ import annotations

import importlib


def test_storage_paths_can_be_overridden_for_harness(monkeypatch, tmp_path):
    isolated_datas = tmp_path / "datas"
    isolated_chroma = tmp_path / "chroma"
    monkeypatch.setenv("DATAS_DIR", str(isolated_datas))
    monkeypatch.setenv("CHROMA_DIR", str(isolated_chroma))

    import common.constants as constants

    importlib.reload(constants)

    assert constants.DATAS_DIR == isolated_datas
    assert constants.CHROMA_DIR == isolated_chroma


def test_mock_llm_stream_does_not_require_real_api_key(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_AGENT_MOCK_LLM", "1")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    import agent_server.core.llm_client as llm_client

    importlib.reload(llm_client)

    chunks = list(llm_client.stream_chat_completion([{"role": "user", "content": "测试"}]))

    assert chunks
    assert "mock" in "".join(chunks).lower()


def test_real_llm_client_ignores_environment_proxy(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setenv("AGNES_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AGNES_MODEL", "test-model")
    monkeypatch.delenv("KNOWLEDGE_AGENT_MOCK_LLM", raising=False)

    import agent_server.core.llm_client as llm_client

    monkeypatch.setattr(llm_client, "OpenAI", FakeOpenAI)

    llm_client.get_client()

    http_client = captured["http_client"]
    assert http_client.trust_env is False


def test_rate_limit_can_be_disabled_for_local_stress(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT", "1")

    import agent_server.api.utils as api_utils

    importlib.reload(api_utils)

    assert api_utils.rate_limit_disabled() is True
