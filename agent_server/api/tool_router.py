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
    return ok(call_tool(tool_name, payload or {}, current_user))
