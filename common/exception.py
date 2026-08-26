from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    RAG_ERROR = "rag_error"


class AppException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        """初始化当前对象并保存后续操作所需的状态。

        :param code: 函数处理所需的“`code`”数据，类型为 ``ErrorCode``。
        :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
        :param status_code: 函数处理所需的“获取状态`code`”数据，类型为 ``int``。
        :param details: 函数处理所需的“`details`”数据，类型为 ``dict[str, Any] | None``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        """初始化当前对象并保存后续操作所需的状态。

        :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        super().__init__(ErrorCode.NOT_FOUND, message, status_code=404)


class PermissionDeniedError(AppException):
    def __init__(self, message: str = "Permission denied") -> None:
        """初始化当前对象并保存后续操作所需的状态。

        :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        super().__init__(ErrorCode.PERMISSION_DENIED, message, status_code=403)


def register_exception_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册业务异常和未处理异常的统一响应处理器。

    :param app: 需要注册处理逻辑的 FastAPI 应用实例，类型为 ``FastAPI``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        """`app`异常`handler`。

        :param _: 当前处理流程未使用的请求对象，类型为 ``Request``。
        :param exc: 当前捕获并准备转换为响应的异常对象，类型为 ``AppException``。
        :return: 返回`app`异常`handler`得到的结果，返回类型为 ``JSONResponse``。
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        """`unhandled`异常`handler`。

        :param _: 当前处理流程未使用的请求对象，类型为 ``Request``。
        :param exc: 当前捕获并准备转换为响应的异常对象，类型为 ``Exception``。
        :return: 返回`unhandled`异常`handler`得到的结果，返回类型为 ``JSONResponse``。
        """
        return JSONResponse(
            status_code=500,
            content={"code": ErrorCode.INTERNAL_ERROR, "message": str(exc), "details": {}},
        )
