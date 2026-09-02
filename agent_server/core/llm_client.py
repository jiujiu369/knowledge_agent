from __future__ import annotations

import os
from typing import Iterable

import httpx
from openai import OpenAI

from agent_server.core.config import get_llm_settings


MOCK_LLM_RESPONSE = '{"answer":"模拟模型已接管，本次不会调用真实模型。","needs_ticket":true,"title":"模拟咨询"}'


def mock_llm_enabled() -> bool:
    """`mock`大语言模型`enabled`。

    :return: 返回`mock`大语言模型`enabled`得到的结果，返回类型为 ``bool``。
    """
    return os.getenv("KNOWLEDGE_AGENT_MOCK_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def get_client() -> OpenAI:
    """获取客户端。

    :return: 返回获取客户端得到的结果，返回类型为 ``OpenAI``。
    """
    settings = get_llm_settings(validate_key=True)
    http_client = httpx.Client(trust_env=False, timeout=settings.timeout_seconds)
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        http_client=http_client,
    )


def chat_completion(messages: list[dict[str, str]], temperature: float | None = None) -> str:
    """处理对话`completion`。

    :param messages: 函数处理所需的“`messages`”数据，类型为 ``list[dict[str, str]]``。
    :param temperature: 函数处理所需的“`temperature`”数据，类型为 ``float | None``。
    :return: 返回处理对话`completion`得到的结果，返回类型为 ``str``。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if mock_llm_enabled():
        return MOCK_LLM_RESPONSE
    settings = get_llm_settings(validate_key=True)
    response = get_client().chat.completions.create(
        model=settings.model,
        messages=messages,
        temperature=settings.temperature if temperature is None else temperature,
    )
    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise RuntimeError("LLM returned empty content")
    return content


def stream_chat_completion(messages: list[dict[str, str]], temperature: float | None = None) -> Iterable[str]:
    """流式处理处理对话`completion`。

    :param messages: 函数处理所需的“`messages`”数据，类型为 ``list[dict[str, str]]``。
    :param temperature: 函数处理所需的“`temperature`”数据，类型为 ``float | None``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    if mock_llm_enabled():
        yield MOCK_LLM_RESPONSE
        return
    settings = get_llm_settings(validate_key=True)
    stream = get_client().chat.completions.create(
        model=settings.model,
        messages=messages,
        temperature=settings.temperature if temperature is None else temperature,
        stream=True,
    )
    for event in stream:
        if event.choices and event.choices[0].delta.content:
            yield event.choices[0].delta.content
