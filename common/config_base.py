from __future__ import annotations

import os
from dataclasses import dataclass


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def get_env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class BaseSettings:
    env: str = get_env("APP_ENV", "dev")
    debug: bool = get_env_bool("APP_DEBUG", True)
    log_level: str = get_env("LOG_LEVEL", "INFO")


def get_base_settings() -> BaseSettings:
    return BaseSettings()
