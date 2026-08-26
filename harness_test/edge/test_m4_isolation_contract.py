from __future__ import annotations

import importlib


def test_storage_paths_can_be_overridden_for_harness(monkeypatch, tmp_path):
    """验证`storage``paths``can``be``overridden``for``harness`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    isolated_datas = tmp_path / "datas"
    isolated_chroma = tmp_path / "chroma"
    monkeypatch.setenv("DATAS_DIR", str(isolated_datas))
    monkeypatch.setenv("CHROMA_DIR", str(isolated_chroma))

    import common.constants as constants

    importlib.reload(constants)

    assert constants.DATAS_DIR == isolated_datas
    assert constants.CHROMA_DIR == isolated_chroma


def test_mock_llm_stream_does_not_require_real_api_key(monkeypatch):
    """验证`mock`大语言模型流式处理`does``not``require``real`API`key`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    monkeypatch.setenv("KNOWLEDGE_AGENT_MOCK_LLM", "1")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    import agent_server.core.llm_client as llm_client

    importlib.reload(llm_client)

    chunks = list(llm_client.stream_chat_completion([{"role": "user", "content": "测试"}]))

    assert chunks
    assert "mock" in "".join(chunks).lower()


def test_real_llm_client_ignores_environment_proxy(monkeypatch):
    """验证`real`大语言模型客户端`ignores``environment``proxy`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            """初始化当前对象并保存后续操作所需的状态。

            :param kwargs: 函数处理所需的“`kwargs`”数据；类型由调用方及当前处理场景决定。
            :return: 无返回值；函数通过副作用、断言或异常完成其职责。
            """
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
    """验证`rate``limit``can``be``disabled``for``local``stress`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    monkeypatch.setenv("KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT", "1")

    import agent_server.api.utils as api_utils

    importlib.reload(api_utils)

    assert api_utils.rate_limit_disabled() is True
