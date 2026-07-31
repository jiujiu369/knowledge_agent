from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from agent_server.graph_flow import graph_nodes
from agent_server.graph_flow.state import AgentState


NodeFunc = Callable[[AgentState], AgentState]


@dataclass(frozen=True)
class DirectedAgentGraph:
    nodes: dict[str, NodeFunc]
    start: str = "identity"
    max_tool_rounds: int = 3

    def next_node(self, name: str, state: AgentState, round_index: int) -> str | None:
        if name == "identity":
            return "rag"
        if name == "rag":
            if not state.rag_results and round_index + 1 < self.max_tool_rounds:
                return "rag"
            return "llm"
        if name == "llm":
            return None
        return None

    def invoke(self, user: dict[str, Any], question: str) -> dict[str, Any]:
        state = AgentState(user=user, question=question)
        current = self.start
        round_index = 0
        while current:
            state = self.nodes[current](state)
            next_name = self.next_node(current, state, round_index)
            if current == "rag":
                round_index += 1
            current = next_name
        return graph_nodes.output_node(state)

    def stream(self, user: dict[str, Any], question: str) -> Iterator[dict[str, Any]]:
        state = AgentState(user=user, question=question)
        current = self.start
        round_index = 0
        emitted = 0
        while current:
            state = self.nodes[current](state)
            for event in state.tool_events[emitted:]:
                yield {"event": "tool", "data": event}
            emitted = len(state.tool_events)
            next_name = self.next_node(current, state, round_index)
            if current == "rag":
                round_index += 1
            current = next_name
        yield {"event": "done", "data": graph_nodes.output_node(state)}


def build_graph():
    return DirectedAgentGraph(
        nodes={
            "identity": graph_nodes.identity_check_node,
            "rag": graph_nodes.parallel_rag_node,
            "llm": graph_nodes.llm_decision_node,
        }
    )


def run_agent(user: dict[str, Any], question: str) -> dict[str, Any]:
    return build_graph().invoke(user, question)


def run_agent_events(user: dict[str, Any], question: str) -> Iterator[dict[str, Any]]:
    yield from build_graph().stream(user, question)


__all__ = ["build_graph", "run_agent", "run_agent_events"]
