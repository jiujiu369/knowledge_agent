from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent_server.graph_flow import graph_nodes
from agent_server.graph_flow.state import AgentState


MAX_RAG_ROUNDS = 3


def _state_updates(state: AgentState, *names: str) -> dict[str, Any]:
    return {name: getattr(state, name) for name in names}


def _identity_node(state: AgentState) -> dict[str, Any]:
    updated = graph_nodes.identity_check_node(state)
    return _state_updates(updated, "tool_events")


def _rag_node(state: AgentState) -> dict[str, Any]:
    updated = graph_nodes.parallel_rag_node(state)
    updated.rag_rounds += 1
    return _state_updates(updated, "rag_results", "similar_tickets", "tool_events", "rag_rounds")


def _route_after_rag(state: AgentState) -> str:
    if not state.rag_results and state.rag_rounds < MAX_RAG_ROUNDS:
        return "rag"
    return "llm"


def _llm_node(state: AgentState) -> dict[str, Any]:
    updated = graph_nodes.llm_decision_node(state)
    return _state_updates(updated, "llm_answer", "ticket_suggestion", "guardrail", "tool_events")


def _as_agent_state(value: AgentState | dict[str, Any]) -> AgentState:
    if isinstance(value, AgentState):
        return value
    names = {item.name for item in fields(AgentState)}
    return AgentState(**{name: item for name, item in value.items() if name in names})


def _apply_updates(state: AgentState, updates: dict[str, Any]) -> None:
    for name, value in updates.items():
        if hasattr(state, name):
            setattr(state, name, value)


def build_graph():
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
    state = build_graph().invoke(AgentState(user=user, question=question))
    return graph_nodes.output_node(_as_agent_state(state))


def run_agent_events(user: dict[str, Any], question: str) -> Iterator[dict[str, Any]]:
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
