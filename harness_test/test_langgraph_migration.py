from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from agent_server.graph_flow.state import AgentState


def test_build_graph_returns_a_compiled_langgraph():
    """验证构建LangGraph 工作流`returns``a``compiled``langgraph`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.graph_flow.graph_builder import build_graph

    graph = build_graph()

    assert isinstance(graph, CompiledStateGraph)


def test_langgraph_retries_empty_rag_at_most_three_times(monkeypatch):
    """验证`langgraph``retries``empty`RAG 检索`at``most``three``times`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.graph_flow import graph_builder, graph_nodes

    rag_calls = 0

    def identity(state: AgentState) -> AgentState:
        """`identity`。

        :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
        :return: 返回`identity`得到的结果，返回类型为 ``AgentState``。
        """
        state.tool_events.append({"tool": "identity_check", "status": "ok"})
        return state

    def empty_rag(state: AgentState) -> AgentState:
        """`empty`RAG 检索。

        :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
        :return: 返回`empty`RAG 检索得到的结果，返回类型为 ``AgentState``。
        """
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
        """大语言模型。

        :param state: 函数处理所需的“状态”数据，类型为 ``AgentState``。
        :return: 返回大语言模型得到的结果，返回类型为 ``AgentState``。
        """
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
