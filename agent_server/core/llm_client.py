from __future__ import annotations

import os
from typing import Iterable

from openai import OpenAI

from agent_server.core.config import get_llm_settings


MOCK_LLM_RESPONSE = '{"answer":"mock LLM 已接管，本次不会调用真实模型。","needs_ticket":true,"title":"mock 咨询"}'


def mock_llm_enabled() -> bool:
    return os.getenv("KNOWLEDGE_AGENT_MOCK_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def get_client() -> OpenAI:
    settings = get_llm_settings(validate_key=True)
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.timeout_seconds)


def chat_completion(messages: list[dict[str, str]], temperature: float | None = None) -> str:
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
