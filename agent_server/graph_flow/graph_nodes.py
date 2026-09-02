from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from fastapi import HTTPException

from agent_server.core import db
from agent_server.core.auth import get_current_user
from agent_server.core.llm_client import stream_chat_completion
from agent_server.graph_flow.prompt_template import build_decision_messages
from agent_server.graph_flow.state import AgentState
from agent_server.tools.business_tools import (
    doc_retrieve,
    match_similar_ticket,
)
from agent_server.tools.schemas import DocRetrieveInput, MatchSimilarTicketInput


def identity_check_node(state: AgentState) -> AgentState:
    """`identity`检查`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回`identity`检查`node`得到的结果，返回类型为 ``AgentState``。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not state.user:
        raise HTTPException(status_code=401, detail="missing user")
    state.tool_events.append({"event_id": "identity_check:1", "tool": "identity_check", "status": "ok"})
    return state


def parallel_rag_node(state: AgentState) -> AgentState:
    """`parallel`RAG 检索`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回`parallel`RAG 检索`node`得到的结果，返回类型为 ``AgentState``。
    """
    rag = doc_retrieve(DocRetrieveInput(query=state.question, top_k=5), state.user)
    similar = match_similar_ticket(MatchSimilarTicketInput(query=state.question, limit=5), state.user)
    state.rag_results = rag["items"]
    state.similar_tickets = similar["items"]
    round_number = state.rag_rounds + 1
    retrieval_hits = []
    for item in state.rag_results:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source_path = str(item.get("source_path") or metadata.get("source_path") or "")
        retrieval_hits.append(
            {
                "title": str(metadata.get("title") or Path(source_path).name or "未知来源"),
                "source_path": source_path,
                "page": metadata.get("page"),
                "chunk": metadata.get("block_index", metadata.get("chunk_index")),
                "score": item.get("score"),
            }
        )
    ticket_hits = [
        {"ticket_id": item.get("id"), "title": str(item.get("title") or "未命名工单")}
        for item in state.similar_tickets
    ]
    state.tool_events.append(
        {
            "event_id": f"doc_retrieve:{round_number}",
            "tool": "doc_retrieve",
            "count": len(state.rag_results),
            "hits": retrieval_hits,
        }
    )
    state.tool_events.append(
        {
            "event_id": f"match_similar_ticket:{round_number}",
            "tool": "match_similar_ticket",
            "count": len(state.similar_tickets),
            "hits": ticket_hits,
        }
    )
    return state


def decide_with_llm(question: str, context: str) -> dict[str, Any]:
    """生成决策`with`大语言模型。

    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param conversation_id: 当前会话编号。
    :param context: 函数处理所需的“`context`”数据，类型为 ``str``。
    :return: 返回生成决策`with`大语言模型得到的结果，返回类型为 ``dict[str, Any]``。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    content = "".join(stream_chat_completion(build_decision_messages(question, context))).strip()
    if not content:
        raise RuntimeError("LLM returned empty content")
    try:
        start = content.find("{")
        end = content.rfind("}")
        parsed = json.loads(content[start : end + 1]) if start >= 0 and end > start else {}
    except json.JSONDecodeError:
        parsed = {}
    answer = str(parsed.get("answer") or content)
    return {
        "answer": answer,
        "needs_ticket": bool(parsed.get("needs_ticket", True)),
        "title": str(parsed.get("title") or question[:40] or "咨询工单"),
    }


def build_agent_context(state: AgentState) -> str:
    """构建智能体`context`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回构建智能体`context`得到的结果，返回类型为 ``str``。
    """
    sections: list[str] = []
    history = db.list_recent_chat_history(state.user, limit=5, conversation_id=state.conversation_id)
    if history:
        history_lines = [f"User: {item['question']}\nAssistant: {item['answer']}" for item in history]
        sections.append("Recent chat history:\n" + "\n\n".join(history_lines))
    if state.rag_results:
        sections.append("Retrieved knowledge:\n" + "\n\n".join(item["content"] for item in state.rag_results[:5]))
    return "\n\n".join(sections)


def llm_decision_node(state: AgentState) -> AgentState:
    """大语言模型智能体决策`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回大语言模型智能体决策`node`得到的结果，返回类型为 ``AgentState``。
    """
    context = build_agent_context(state)
    decision = decide_with_llm(state.question, context)
    state.llm_answer = decision["answer"]
    state.guardrail = guardrail_check(state.llm_answer, context)
    state.tool_events.append({"event_id": "llm_decision:1", "tool": "llm_decision", "needs_ticket": decision["needs_ticket"]})
    if decision["needs_ticket"]:
        state.ticket_suggestion = {
            "recommended": True,
            "title": decision["title"][:80],
            "content": state.question,
            "answer": state.llm_answer,
        }
    return state


def guardrail_check(answer: str, context: str) -> dict[str, Any]:
    """执行安全护栏检查检查。

    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param context: 函数处理所需的“`context`”数据，类型为 ``str``。
    :return: 返回执行安全护栏检查检查得到的结果，返回类型为 ``dict[str, Any]``。
    """
    patterns = {
        "ticket_ids": r"\b(?:TK|工单)[-_\dA-Za-z]+\b",
        "amounts": r"\d+(?:\.\d+)?\s*(?:元|万元|块)",
        "clauses": r"第[一二三四五六七八九十百\d]+条",
    }
    checked = 0
    misses = 0
    details: dict[str, list[str]] = {}
    for name, pattern in patterns.items():
        values = sorted(set(re.findall(pattern, answer)))
        if not values:
            continue
        checked += len(values)
        missing = [value for value in values if value not in context]
        misses += len(missing)
        details[name] = missing
    risk_score = round(misses / checked, 4) if checked else 0.0
    return {"risk_score": risk_score, "checked_items": checked, "unmatched": details}


def output_node(state: AgentState) -> dict[str, Any]:
    """输出`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回输出`node`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    return {
        "answer": state.llm_answer,
        "ticket_id": state.ticket["id"] if state.ticket else None,
        "ticket_suggestion": state.ticket_suggestion,
        "retrieval": state.rag_results,
        "similar_tickets": state.similar_tickets,
        "guardrail": state.guardrail,
        "tool_events": state.tool_events,
    }


def run_agent(user: dict[str, Any], question: str, conversation_id: int | None = None) -> dict[str, Any]:
    """运行智能体。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param conversation_id: 当前会话编号。
    :return: 返回运行智能体得到的结果，返回类型为 ``dict[str, Any]``。
    """
    state = AgentState(user=user, question=question, conversation_id=conversation_id)
    for node in (identity_check_node, parallel_rag_node, llm_decision_node):
        state = node(state)
    return output_node(state)


def run_agent_events(
    user: dict[str, Any], question: str, conversation_id: int | None = None
) -> Iterator[dict[str, Any]]:
    """运行智能体`events`。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param conversation_id: 当前会话编号。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    state = identity_check_node(AgentState(user=user, question=question, conversation_id=conversation_id))
    yield {"event": "tool", "data": state.tool_events[-1]}
    state = parallel_rag_node(state)
    yield {"event": "tool", "data": state.tool_events[-2]}
    yield {"event": "tool", "data": state.tool_events[-1]}
    state = llm_decision_node(state)
    for event in state.tool_events[3:]:
        yield {"event": "tool", "data": event}
    yield {"event": "done", "data": output_node(state)}
