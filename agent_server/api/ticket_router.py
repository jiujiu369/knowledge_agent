from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_server.api.utils import ok
from agent_server.core import db
from agent_server.core.auth import get_current_user
from agent_server.core.rbac import role_tier
from agent_server.tools.business_tools import query_ticket_list
from agent_server.tools.schemas import CreateConsultTicketInput, QueryTicketListInput


router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class TicketStatusUpdate(BaseModel):
    status: str


ALLOWED_TICKET_STATUSES = {"pending", "approved", "rejected", "closed"}


@router.get("")
def list_tickets(current_user: Annotated[dict, Depends(get_current_user)]):
    """查询列表`tickets`。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回查询列表`tickets`得到的处理结果；具体类型由实际执行分支决定。
    """
    mine_only = role_tier(current_user["role"]) != "admin"
    return ok(query_ticket_list(QueryTicketListInput(mine_only=mine_only), current_user))


@router.post("")
def create_ticket(payload: CreateConsultTicketInput, current_user: Annotated[dict, Depends(get_current_user)]):
    """创建工单。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``CreateConsultTicketInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回创建工单得到的处理结果；具体类型由实际执行分支决定。
    """
    ticket = db.create_ticket(
        title=payload.title,
        content=payload.content,
        creator_id=current_user["id"],
        answer=payload.answer,
        metadata=json.dumps({"source": "user"}, ensure_ascii=False),
        status="pending",
    )
    return ok(ticket)


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """获取工单。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回获取工单得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    ticket = db.get_ticket(ticket_id, current_user, include_all=role_tier(current_user["role"]) == "admin")
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ok(ticket)


@router.patch("/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketStatusUpdate, current_user: Annotated[dict, Depends(get_current_user)]):
    """更新工单。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param payload: 函数处理所需的“`payload`”数据，类型为 ``TicketStatusUpdate``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回更新工单得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if role_tier(current_user["role"]) != "admin":
        raise HTTPException(status_code=403, detail="admin approval required")
    if payload.status not in ALLOWED_TICKET_STATUSES:
        raise HTTPException(status_code=400, detail="unsupported ticket status")
    ticket = db.update_ticket_status(
        ticket_id,
        payload.status,
        current_user,
        include_all=True,
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ok(ticket)
