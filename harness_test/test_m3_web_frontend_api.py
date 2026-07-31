from __future__ import annotations


def test_parse_sse_events_handles_named_events_and_json_data():
    from web.frontend_api import parse_sse_events

    raw_lines = [
        "event: tool",
        'data: {"tool":"doc_retrieve","count":2}',
        "",
        "event: done",
        'data: {"answer":"ok","ticket_id":7}',
        "",
    ]

    events = list(parse_sse_events(raw_lines))

    assert events == [
        {"event": "tool", "data": {"tool": "doc_retrieve", "count": 2}},
        {"event": "done", "data": {"answer": "ok", "ticket_id": 7}},
    ]


def test_describe_tool_event_maps_backend_tools_to_chinese_status():
    from web.frontend_api import describe_tool_event

    assert describe_tool_event({"tool": "identity_check", "status": "ok"}) == "已确认当前登录身份"
    assert describe_tool_event({"tool": "doc_retrieve", "count": 3}) == "正在检索知识库，命中 3 条片段"
    assert describe_tool_event({"tool": "match_similar_ticket", "count": 1}) == "正在匹配历史工单，找到 1 条相似记录"
    assert describe_tool_event({"tool": "llm_decision", "needs_ticket": True}) == "正在生成答复，并判断需要创建工单"
    assert describe_tool_event({"tool": "create_consult_ticket", "ticket_id": 9}) == "已创建咨询工单 #9"


def test_page_param_selects_valid_sidebar_page_without_changing_invalid_values():
    from web.frontend_api import resolve_page

    assert resolve_page("登录", "工单") == "工单"
    assert resolve_page("登录", "bad") == "登录"
    assert resolve_page("unknown", None) == "登录"


def test_local_launcher_can_parse_backend_port_pids():
    from web.local_launcher import parse_netstat_pids

    output = """
      TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       12345
      TCP    127.0.0.1:8501         0.0.0.0:0              LISTENING       54321
      TCP    [::1]:8000             [::]:0                 LISTENING       67890
    """

    assert parse_netstat_pids(output, 8000) == {12345, 67890}
