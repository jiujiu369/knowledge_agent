from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from common.config_base import get_env, get_env_float


load_dotenv()


@dataclass(frozen=True)
class LLMSettings:
    model: str
    base_url: str
    api_key: str
    timeout_seconds: float
    temperature: float
    stream: bool


def get_llm_settings(validate_key: bool = False) -> LLMSettings:
    api_key = os.getenv("AGNES_API_KEY") or os.getenv("ARK_API_KEY", "")
    if validate_key and not api_key:
        raise RuntimeError("Missing AGNES_API_KEY or ARK_API_KEY environment variable")
    return LLMSettings(
        model=os.getenv("AGNES_MODEL") or os.getenv("ARK_MODEL") or "agnes-2.0-flash",
        base_url=os.getenv("AGNES_BASE_URL") or os.getenv("ARK_BASE_URL") or "https://apihub.agnes-ai.com/v1",
        api_key=api_key,
        timeout_seconds=get_env_float("LLM_TIMEOUT_SECONDS", 60.0),
        temperature=get_env_float("AGNES_TEMPERATURE", 0.2),
        stream=True,
    )
