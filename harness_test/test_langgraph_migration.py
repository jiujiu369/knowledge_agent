from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from agent_server.graph_flow.state import AgentState


def test_build_graph_returns_a_compiled_langgraph():
    from agent_server.graph_flow.graph_builder import build_graph

    graph = build_graph()

    assert isinstance(graph, CompiledStateGraph)


def test_langgraph_retries_empty_rag_at_most_three_times(monkeypatch):
    from agent_server.graph_flow import graph_builder, graph_nodes

    rag_calls = 0

    def identity(state: AgentState) -> AgentState:
        state.tool_events.append({"tool": "identity_check", "status": "ok"})
        return state

    def empty_rag(state: AgentState) -> AgentState:
        nonlocal rag_calls
        rag_calls += 1
        state.tool_events.extend(
            [
                {"tool": "doc_retrieve", "count": 0},
                {"tool": "match_similar_ticket", "count": 0},
            ]
        )
        return state

    def llm(state: AgentState) -> AgentState:
        state.llm_answer = "无匹配结果"
        state.tool_events.append({"tool": "llm_decision", "needs_ticket": False})
        return state

    monkeypatch.setattr(graph_nodes, "identity_check_node", identity)
    monkeypatch.setattr(graph_nodes, "parallel_rag_node", empty_rag)
    monkeypatch.setattr(graph_nodes, "llm_decision_node", llm)

    result = graph_builder.run_agent({"id": 1}, "未知问题")

    assert rag_calls == 3
    assert result["answer"] == "无匹配结果"
    assert [event["tool"] for event in result["tool_events"]] == [
        "identity_check",
        "doc_retrieve",
        "match_similar_ticket",
        "doc_retrieve",
        "match_similar_ticket",
        "doc_retrieve",
        "match_similar_ticket",
        "llm_decision",
    ]
