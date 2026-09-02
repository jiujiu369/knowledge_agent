from __future__ import annotations

import json
from uuid import uuid4
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from agent_server.api.utils import ChatRequest, ConversationCreateRequest, ok
from agent_server.core import db
from agent_server.core.auth import get_current_user
from agent_server.core.qa_logger import safe_log_qa_event
from agent_server.graph_flow.graph_builder import run_agent, run_agent_events


router = APIRouter(prefix="/api/chat", tags=["chat"])


def require_conversation(current_user: dict, conversation_id: int | None) -> dict:
    """解析并校验当前用户的会话，管理员也不得绕过所有权。

    :param current_user: 当前登录用户。
    :param conversation_id: 待访问的会话编号。
    :return: 返回校验通过的会话。
    """
    if conversation_id is None:
        return db.get_or_create_default_conversation(current_user["id"])
    conversation = db.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.post("")
def chat(payload: ChatRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """处理对话。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``ChatRequest``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回处理对话得到的处理结果；具体类型由实际执行分支决定。
    """
    conversation = require_conversation(current_user, payload.conversation_id)
    request_id = payload.request_id or uuid4().hex
    result = run_agent(current_user, payload.message, conversation["id"])
    saved = save_chat_history(
        current_user, payload.message, result, conversation["id"], request_id
    )
    return ok(done_payload(result, request_id, int(conversation["id"]), saved))


@router.post("/stream")
def chat_stream(payload: ChatRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """处理对话流式处理。

    :param payload: 函数处理所需的“`payload`”数据，类型为 ``ChatRequest``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回处理对话流式处理得到的处理结果；具体类型由实际执行分支决定。
    """
    def events():
        """`events`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        conversation = require_conversation(current_user, payload.conversation_id)
        request_id = payload.request_id or uuid4().hex
        tool_events: list[dict] = []
        try:
            for item in run_agent_events(current_user, payload.message, conversation["id"]):
                if item["event"] == "tool" and isinstance(item["data"], dict):
                    tool_events.append(item["data"])
                if item["event"] == "done" and isinstance(item["data"], dict):
                    saved = save_chat_history(
                        current_user,
                        payload.message,
                        item["data"],
                        conversation["id"],
                        request_id,
                    )
                    item = {
                        "event": "done",
                        "data": done_payload(
                            item["data"], request_id, int(conversation["id"]), saved
                        ),
                    }
                yield f"event: {item['event']}\n"
                yield "data: " + json.dumps(item["data"], ensure_ascii=False) + "\n\n"
        except Exception:
            failed = {
                "answer": "请求失败：后端处理失败，请稍后重试。",
                "tool_events": tool_events,
                "ticket_id": None,
                "ticket_suggestion": None,
                "error": True,
            }
            saved = save_chat_history(
                current_user,
                payload.message,
                failed,
                conversation["id"],
                request_id,
            )
            data = done_payload(failed, request_id, int(conversation["id"]), saved)
            yield "event: done\n"
            yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/history")
def chat_history(
    current_user: Annotated[dict, Depends(get_current_user)],
    conversation_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
):
    """处理对话历史记录。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :param conversation_id: 可选的会话编号。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回处理对话历史记录得到的处理结果；具体类型由实际执行分支决定。
    """
    conversation = require_conversation(current_user, conversation_id)
    items = db.list_chat_history(
        current_user, limit=limit + 1, conversation_id=conversation["id"], before_id=before_id
    )
    has_more = len(items) > limit
    items = items[:limit]
    for item in items:
        try:
            item["tool_events"] = json.loads(item.get("tool_events") or "[]")
        except json.JSONDecodeError:
            item["tool_events"] = []
    return ok({"items": list(reversed(items)), "has_more": has_more})


@router.get("/conversations")
def conversations(current_user: Annotated[dict, Depends(get_current_user)]):
    """列出当前登录用户自己的会话。

    :param current_user: 当前登录用户。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回当前用户的会话列表。
    """
    return ok({"items": db.list_conversations(current_user)})


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """为当前登录用户创建空白会话。

    :param payload: 会话创建请求。
    :param current_user: 当前登录用户。
    :return: 返回新建的会话。
    """
    return ok(
        db.create_conversation(current_user["id"], payload.title, request_id=payload.request_id)
    )


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
):
    """读取当前用户指定会话中的消息。

    :param conversation_id: 待读取的会话编号。
    :param current_user: 当前登录用户。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回会话信息和消息列表。
    """
    conversation = require_conversation(current_user, conversation_id)
    items = db.list_chat_history(
        current_user, limit=limit + 1, conversation_id=conversation["id"], before_id=before_id
    )
    has_more = len(items) > limit
    items = items[:limit]
    for item in items:
        try:
            item["tool_events"] = json.loads(item.get("tool_events") or "[]")
        except json.JSONDecodeError:
            item["tool_events"] = []
    return ok({"conversation": conversation, "items": list(reversed(items)), "has_more": has_more})


@router.delete("/history/{history_id}")
def delete_history(history_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """删除当前用户自己的一整轮问答。

    :param history_id: 待删除的聊天记录编号。
    :param current_user: 当前登录用户。
    :return: 返回已删除的整轮问答。
    """
    deleted = db.delete_chat_history(history_id, current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="chat history not found")
    return ok({"deleted": deleted})


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """删除当前登录用户自己的会话及聊天记录。

    :param conversation_id: 待删除的会话编号。
    :param current_user: 当前登录用户。
    :return: 返回被删除的会话。
    """
    deleted = db.delete_conversation(conversation_id, current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ok(deleted)


def done_payload(result: dict, request_id: str, conversation_id: int, saved: dict) -> dict:
    """合并最终回答与持久化标识。

    :param result: 智能体最终结果。
    :param request_id: 本轮请求标识。
    :param conversation_id: 本轮所属会话编号。
    :param saved: 已持久化聊天记录。
    :return: 返回可发送给前端的完成事件数据。
    """
    payload = dict(result)
    payload.update(
        {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "chat_history_id": int(saved["id"]),
            "answer": str(saved.get("answer") or ""),
        }
    )
    return payload


def save_chat_history(
    current_user: dict,
    question: str,
    result: dict,
    conversation_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """保存处理对话历史记录。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``dict``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param result: 函数处理所需的“结果”数据，类型为 ``dict``。
    :param conversation_id: 消息所属的会话编号。
    :param request_id: 本轮请求的幂等标识。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    saved = db.create_chat_history(
        user_id=current_user["id"],
        question=question,
        answer=str(result.get("answer") or ""),
        ticket_id=result.get("ticket_id"),
        tool_events=json.dumps(result.get("tool_events") or [], ensure_ascii=False),
        conversation_id=conversation_id,
        request_id=request_id,
        is_error=bool(result.get("error")),
    )
    safe_log_qa_event(current_user, question, result)
    return saved
