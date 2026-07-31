from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent_server.api.utils import ChatRequest, ok
from agent_server.core import db
from agent_server.core.auth import get_current_user
from agent_server.core.qa_logger import safe_log_qa_event
from agent_server.graph_flow.graph_builder import run_agent, run_agent_events


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
def chat(payload: ChatRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    result = run_agent(current_user, payload.message)
    save_chat_history(current_user, payload.message, result)
    return ok(result)


@router.post("/stream")
def chat_stream(payload: ChatRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    def events():
        for item in run_agent_events(current_user, payload.message):
            if item["event"] == "done" and isinstance(item["data"], dict):
                save_chat_history(current_user, payload.message, item["data"])
            yield f"event: {item['event']}\n"
            yield "data: " + json.dumps(item["data"], ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/history")
def chat_history(current_user: Annotated[dict, Depends(get_current_user)]):
    items = db.list_chat_history(current_user)
    for item in items:
        try:
            item["tool_events"] = json.loads(item.get("tool_events") or "[]")
        except json.JSONDecodeError:
            item["tool_events"] = []
    return ok({"items": items})


def save_chat_history(current_user: dict, question: str, result: dict) -> None:
    db.create_chat_history(
        user_id=current_user["id"],
        question=question,
        answer=str(result.get("answer") or ""),
        ticket_id=result.get("ticket_id"),
        tool_events=json.dumps(result.get("tool_events") or [], ensure_ascii=False),
    )
    safe_log_qa_event(current_user, question, result)
