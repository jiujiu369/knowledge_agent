from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent_server.graph_flow import graph_nodes
from agent_server.graph_flow.state import AgentState


MAX_RAG_ROUNDS = 3


def _state_updates(state: AgentState, *names: str) -> dict[str, Any]:
    """状态`updates`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :param names: 函数处理所需的“`names`”数据，类型为 ``str``。
    :return: 返回状态`updates`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    return {name: getattr(state, name) for name in names}


def _identity_node(state: AgentState) -> dict[str, Any]:
    """`identity``node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回`identity``node`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    updated = graph_nodes.identity_check_node(state)
    return _state_updates(updated, "tool_events")


def _rag_node(state: AgentState) -> dict[str, Any]:
    """RAG 检索`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回RAG 检索`node`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    updated = graph_nodes.parallel_rag_node(state)
    updated.rag_rounds += 1
    return _state_updates(updated, "rag_results", "similar_tickets", "tool_events", "rag_rounds")


def _route_after_rag(state: AgentState) -> str:
    """`route``after`RAG 检索。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回`route``after`RAG 检索得到的结果，返回类型为 ``str``。
    """
    if not state.rag_results and state.rag_rounds < MAX_RAG_ROUNDS:
        return "rag"
    return "llm"


def _llm_node(state: AgentState) -> dict[str, Any]:
    """大语言模型`node`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :return: 返回大语言模型`node`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    updated = graph_nodes.llm_decision_node(state)
    return _state_updates(updated, "llm_answer", "ticket_suggestion", "guardrail", "tool_events")


def _as_agent_state(value: AgentState | dict[str, Any]) -> AgentState:
    """`as`智能体状态。

    :param value: 函数处理所需的“`value`”数据，类型为 ``AgentState | dict[str, Any]``。
    :return: 返回`as`智能体状态得到的结果，返回类型为 ``AgentState``。
    """
    if isinstance(value, AgentState):
        return value
    names = {item.name for item in fields(AgentState)}
    return AgentState(**{name: item for name, item in value.items() if name in names})


def _apply_updates(state: AgentState, updates: dict[str, Any]) -> None:
    """应用`updates`。

    :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
    :param updates: 函数处理所需的“`updates`”数据，类型为 ``dict[str, Any]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    for name, value in updates.items():
        if hasattr(state, name):
            setattr(state, name, value)


def build_graph():
    """构建LangGraph 工作流。

    :return: 返回构建LangGraph 工作流得到的处理结果；具体类型由实际执行分支决定。
    """
    graph = StateGraph(AgentState)
    graph.add_node("identity", _identity_node)
    graph.add_node("rag", _rag_node)
    graph.add_node("llm", _llm_node)
    graph.add_edge(START, "identity")
    graph.add_edge("identity", "rag")
    graph.add_conditional_edges("rag", _route_after_rag, {"rag": "rag", "llm": "llm"})
    graph.add_edge("llm", END)
    return graph.compile()


def run_agent(user: dict[str, Any], question: str) -> dict[str, Any]:
    """运行智能体。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :return: 返回运行智能体得到的结果，返回类型为 ``dict[str, Any]``。
    """
    state = build_graph().invoke(AgentState(user=user, question=question))
    return graph_nodes.output_node(_as_agent_state(state))


def run_agent_events(user: dict[str, Any], question: str) -> Iterator[dict[str, Any]]:
    """运行智能体`events`。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    state = AgentState(user=user, question=question)
    emitted = 0
    for chunk in build_graph().stream(state, stream_mode="updates"):
        for updates in chunk.values():
            _apply_updates(state, updates)
            for event in state.tool_events[emitted:]:
                yield {"event": "tool", "data": event}
            emitted = len(state.tool_events)
    yield {"event": "done", "data": graph_nodes.output_node(state)}


__all__ = ["build_graph", "run_agent", "run_agent_events"]
