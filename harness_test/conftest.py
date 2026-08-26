from __future__ import annotations

import importlib

import pytest

from harness_test.fixture.app_client import isolated_client


@pytest.fixture(autouse=True)
def isolated_harness_env(tmp_path, monkeypatch):
    """`isolated``harness`环境变量。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
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
    """API客户端。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 返回API客户端得到的处理结果；具体类型由实际执行分支决定。
    """
    return isolated_client(tmp_path, monkeypatch)
