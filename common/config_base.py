from __future__ import annotations

import os
from dataclasses import dataclass


def get_env(name: str, default: str = "") -> str:
    """获取环境变量。

    :param name: 目标配置项、日志器或资源的名称，类型为 ``str``。
    :param default: 环境变量不存在或无法转换时采用的默认值，类型为 ``str``。
    :return: 返回获取环境变量得到的结果，返回类型为 ``str``。
    """
    return os.getenv(name, default)


def get_env_int(name: str, default: int) -> int:
    """获取环境变量`int`。

    :param name: 目标配置项、日志器或资源的名称，类型为 ``str``。
    :param default: 环境变量不存在或无法转换时采用的默认值，类型为 ``int``。
    :return: 返回获取环境变量`int`得到的结果，返回类型为 ``int``。
    """
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def get_env_float(name: str, default: float) -> float:
    """获取环境变量`float`。

    :param name: 目标配置项、日志器或资源的名称，类型为 ``str``。
    :param default: 环境变量不存在或无法转换时采用的默认值，类型为 ``float``。
    :return: 返回获取环境变量`float`得到的结果，返回类型为 ``float``。
    """
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def get_env_bool(name: str, default: bool = False) -> bool:
    """获取环境变量`bool`。

    :param name: 目标配置项、日志器或资源的名称，类型为 ``str``。
    :param default: 环境变量不存在或无法转换时采用的默认值，类型为 ``bool``。
    :return: 返回获取环境变量`bool`得到的结果，返回类型为 ``bool``。
    """
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
    """获取基础设置。

    :return: 返回获取基础设置得到的结果，返回类型为 ``BaseSettings``。
    """
    return BaseSettings()
