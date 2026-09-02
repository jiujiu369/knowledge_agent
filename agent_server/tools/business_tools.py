from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from agent_server.core import db
from agent_server.core.rbac import ensure_tool_allowed, role_tier
from agent_server.rag.retriever_pipe import rebuild_index, retrieve
from agent_server.tools.schemas import (
    CreateConsultTicketInput,
    DocRetrieveInput,
    ExportTicketStatInput,
    KnowledgeManageInput,
    MatchSimilarTicketInput,
    QueryTicketListInput,
)


def doc_retrieve(payload: DocRetrieveInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """知识文档检索。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``DocRetrieveInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回知识文档检索得到的结果，返回类型为 ``dict[str, Any]``。
    """
    ensure_tool_allowed(current_user["role"], "doc_retrieve")
    results = retrieve(payload.query, top_k=payload.top_k)
    return {"items": [result.model_dump() for result in results]}


def match_similar_ticket(payload: MatchSimilarTicketInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """匹配`similar`工单。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``MatchSimilarTicketInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回匹配`similar`工单得到的结果，返回类型为 ``dict[str, Any]``。
    """
    ensure_tool_allowed(current_user["role"], "match_similar_ticket")
    include_all = role_tier(current_user["role"]) == "admin"
    tickets = db.list_tickets(current_user, include_all=include_all)
    terms = [term for term in payload.query.lower().split() if term]
    scored: list[tuple[int, dict[str, Any]]] = []
    for ticket in tickets:
        haystack = f"{ticket['title']} {ticket['content']} {ticket.get('answer') or ''}".lower()
        score = sum(1 for term in terms if term in haystack)
        if payload.query in haystack:
            score += 3
        if score > 0:
            scored.append((score, ticket))
    scored.sort(key=lambda item: item[0], reverse=True)
    return {"items": [ticket for _, ticket in scored[: payload.limit]]}


def create_consult_ticket(payload: CreateConsultTicketInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """创建`consult`工单。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``CreateConsultTicketInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回创建`consult`工单得到的结果，返回类型为 ``dict[str, Any]``。
    """
    ensure_tool_allowed(current_user["role"], "create_consult_ticket")
    ticket = db.create_ticket(
        title=payload.title,
        content=payload.content,
        creator_id=current_user["id"],
        answer=payload.answer,
        metadata=json.dumps({"source": "agent"}, ensure_ascii=False),
        ticket_type="consultation",
    )
    return {"ticket": ticket}


def query_ticket_list(payload: QueryTicketListInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """查询工单查询列表。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``QueryTicketListInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回查询工单查询列表得到的结果，返回类型为 ``dict[str, Any]``。
    """
    ensure_tool_allowed(current_user["role"], "query_ticket_list")
    include_all = role_tier(current_user["role"]) == "admin" and not payload.mine_only
    tickets = db.list_tickets(current_user, include_all=include_all)
    if payload.status:
        tickets = [ticket for ticket in tickets if ticket["status"] == payload.status]
    return {"items": tickets}


def export_ticket_stat(payload: ExportTicketStatInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """导出工单统计数据。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``ExportTicketStatInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回导出工单统计数据得到的结果，返回类型为 ``dict[str, Any]``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    ensure_tool_allowed(current_user["role"], "export_ticket_stat")
    if payload.format != "json":
        raise HTTPException(status_code=400, detail="unsupported export format")
    return db.ticket_stats()


def knowledge_manage(payload: KnowledgeManageInput, current_user: dict[str, Any]) -> dict[str, Any]:
    """知识库`manage`。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``KnowledgeManageInput``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回知识库`manage`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    ensure_tool_allowed(current_user["role"], "knowledge_manage")
    if payload.action == "list":
        return {"items": db.list_docs()}
    _, stats, error = rebuild_index()
    for item in stats:
        path = Path(item["source_path"])
        db.upsert_doc(
            source_path=item["source_path"],
            title=path.name,
            checksum=None,
            chunk_count=int(item["chunks"]),
        )
    return {"stats": stats, "warning": error}


TOOL_REGISTRY = {
    "doc_retrieve": (DocRetrieveInput, doc_retrieve),
    "match_similar_ticket": (MatchSimilarTicketInput, match_similar_ticket),
    "create_consult_ticket": (CreateConsultTicketInput, create_consult_ticket),
    "query_ticket_list": (QueryTicketListInput, query_ticket_list),
    "export_ticket_stat": (ExportTicketStatInput, export_ticket_stat),
    "knowledge_manage": (KnowledgeManageInput, knowledge_manage),
}


def call_tool(tool_name: str, payload: dict[str, Any], current_user: dict[str, Any]) -> dict[str, Any]:
    """调用工具。

    :param tool_name: 函数处理所需的“工具`name`”数据，类型为 ``str``。
    :param payload: 函数处理所需的“`payload`”数据，类型为 ``dict[str, Any]``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict[str, Any]``。
    :return: 返回调用工具得到的结果，返回类型为 ``dict[str, Any]``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    ensure_tool_allowed(current_user["role"], tool_name)
    schema, func = TOOL_REGISTRY[tool_name]
    try:
        parsed_payload = schema(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return func(parsed_payload, current_user)
