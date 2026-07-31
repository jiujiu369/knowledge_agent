from __future__ import annotations

import json
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


def rate_limit_disabled() -> bool:
    return os.getenv("KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT", "").strip().lower() in {"1", "true", "yes", "on"}


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": "ok", "message": message, "data": data}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def message_valid(cls, value: str) -> str:
        return validate_user_text(value)


async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
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
    try:
        response = await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": "error", "message": str(exc.detail), "data": None})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"code": "internal_error", "message": str(exc), "data": None})

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
