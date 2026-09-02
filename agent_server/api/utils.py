from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from agent_server.tools.schemas import validate_user_text
from common.constants import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS


_REQUESTS: dict[str, deque[float]] = defaultdict(deque)
LOGGER = logging.getLogger(__name__)
GENERIC_ERROR_MESSAGE = "操作失败，请稍后重试；详细原因已记录到服务日志。"


def rate_limit_disabled() -> bool:
    """`rate``limit``disabled`。

    :return: 返回`rate``limit``disabled`得到的结果，返回类型为 ``bool``。
    """
    return os.getenv("KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT", "").strip().lower() in {"1", "true", "yes", "on"}


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """构造成功响应。

    :param data: 函数处理所需的“数据”数据，类型为 ``Any``。
    :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
    :return: 返回构造成功响应得到的结果，返回类型为 ``dict[str, Any]``。
    """
    return {"code": "ok", "message": message, "data": data}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = Field(default=None, gt=0)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("message")
    @classmethod
    def message_valid(cls, value: str) -> str:
        """校验聊天消息。

        :param value: 待校验的消息文本。
        :return: 返回清理后的消息文本。
        """
        return validate_user_text(value)


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="新对话", max_length=80)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("title")
    @classmethod
    def title_valid(cls, value: str) -> str:
        """清理会话标题，空标题回退为默认名称。

        :param value: 待校验的会话标题。
        :return: 返回清理后的会话标题。
        """
        return " ".join(value.split()) or "新对话"

async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """`rate``limit``middleware`。

    :param request: 包含认证、请求体及上下文信息的 HTTP 请求对象，类型为 ``Request``。
    :param call_next: 函数处理所需的“调用`next`”数据，类型为 ``Callable[[Request], Awaitable[Response]]``。
    :return: 返回`rate``limit``middleware`得到的结果，返回类型为 ``Response``。
    """
    if rate_limit_disabled():
        return await call_next(request)
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _REQUESTS[client]
    while window and now - window[0] > RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(status_code=429, content={"code": "rate_limited", "message": "too many requests", "data": None})
    window.append(now)
    return await call_next(request)


async def uniform_exception_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """统一处理异常`middleware`。

    :param request: 包含认证、请求体及上下文信息的 HTTP 请求对象，类型为 ``Request``。
    :param call_next: 函数处理所需的“调用`next`”数据，类型为 ``Callable[[Request], Awaitable[Response]]``。
    :return: 返回统一处理异常`middleware`得到的结果，返回类型为 ``Response``。
    """
    try:
        response = await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": "error", "message": str(exc.detail), "data": None})
    except Exception:
        LOGGER.exception("处理请求时发生未识别异常")
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": GENERIC_ERROR_MESSAGE, "data": None},
        )

    if request.url.path in {"/health", "/openapi.json"} or request.url.path.startswith("/docs"):
        return response
    if response.headers.get("content-type", "").startswith("application/json"):
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except json.JSONDecodeError:
            payload = body.decode("utf-8", errors="replace")
        if isinstance(payload, dict) and {"code", "message", "data"}.issubset(payload.keys()):
            content = payload
        elif response.status_code >= 400:
            message = payload.get("detail") if isinstance(payload, dict) else payload
            content = {"code": "error", "message": str(message), "data": None}
        else:
            content = ok(payload)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return JSONResponse(status_code=response.status_code, content=content, headers=headers)
    return response
