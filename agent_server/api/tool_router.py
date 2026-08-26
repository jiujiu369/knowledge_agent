from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from agent_server.api.utils import ok
from agent_server.core.auth import get_current_user
from agent_server.tools.business_tools import call_tool


router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.post("/{tool_name}")
def invoke_tool(
    tool_name: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    payload: dict[str, Any] | None = None,
):
    """调用工具。

    :param tool_name: 函数处理所需的“工具`name`”数据，类型为 ``str``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :param payload: 函数处理所需的“`payload`”数据，类型为 ``dict[str, Any] | None``。
    :return: 返回调用工具得到的处理结果；具体类型由实际执行分支决定。
    """
    return ok(call_tool(tool_name, payload or {}, current_user))
