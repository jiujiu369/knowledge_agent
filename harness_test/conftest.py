from __future__ import annotations

import importlib

import pytest

from harness_test.fixture.app_client import isolated_client


@pytest.fixture(autouse=True)
def isolated_harness_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_DIR", str(tmp_path / "datas"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("QA_LOG_PATH", str(tmp_path / "qa_events.jsonl"))
    monkeypatch.setenv("KNOWLEDGE_AGENT_MOCK_LLM", "1")
    monkeypatch.setenv("KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT", "1")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    import common.constants as constants
    import agent_server.api.utils as api_utils
    import agent_server.core.db as db

    importlib.reload(constants)
    api_utils._REQUESTS.clear()
    db.reset_db_for_tests()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    return isolated_client(tmp_path, monkeypatch)
