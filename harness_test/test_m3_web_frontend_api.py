from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_upload_knowledge_file_uses_original_filename(monkeypatch):
    """上传临时文件时仍向后端传递用户选择的原始文件名。"""
    from web import frontend_api

    temporary_file = Path(__file__)
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": "ok", "data": {}}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(frontend_api.requests, "post", fake_post)

    frontend_api.upload_knowledge_file(
        temporary_file,
        "token",
        "http://127.0.0.1:8000",
        filename="办公用品采购管理制度.pdf",
    )

    assert captured["files"]["file"][0] == "办公用品采购管理制度.pdf"


def test_parse_sse_events_handles_named_events_and_json_data():
    """验证解析`sse``events``handles``named``events``and``json`数据。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
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
    """验证生成说明工具事件`maps`后端服务`tools``to``chinese`获取状态。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from web.frontend_api import describe_tool_event

    assert describe_tool_event({"tool": "identity_check", "status": "ok"}) == "已确认当前登录身份"
    assert describe_tool_event({"tool": "doc_retrieve", "count": 3}) == "正在检索知识库，命中 3 条片段"
    assert describe_tool_event({"tool": "match_similar_ticket", "count": 1}) == "正在匹配历史工单，找到 1 条相似记录"
    assert describe_tool_event({"tool": "llm_decision", "needs_ticket": True}) == "正在生成答复，并判断需要创建工单"
    assert describe_tool_event({"tool": "create_consult_ticket", "ticket_id": 9}) == "已创建咨询工单 #9"


def test_localize_error_message_translates_common_backend_errors():
    """验证本地化错误信息消息`translates``common`后端服务`errors`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from web.frontend_api import localize_error_message

    assert localize_error_message("invalid username or password") == "账号或密码错误"
    assert localize_error_message("missing bearer token") == "缺少登录令牌，请重新登录"
    assert localize_error_message([{"loc": ["body", "username"], "msg": "field required"}]) == "请求参数不合法"


def test_page_param_selects_valid_sidebar_page_without_changing_invalid_values():
    """验证页面`param``selects``valid`侧边栏页面`without``changing``invalid``values`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from web.frontend_api import resolve_page

    assert resolve_page("登录", "工单") == "工单"
    assert resolve_page("登录", "bad") == "登录"
    assert resolve_page("unknown", None) == "登录"


def test_response_data_formats_backend_errors_in_chinese():
    """验证响应数据`formats`后端服务`errors``in``chinese`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises AssertionError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    from web.frontend_api import response_data

    class FakeResponse:
        status_code = 401

        def json(self):
            """`json`。

            :return: 返回`json`得到的处理结果；具体类型由实际执行分支决定。
            """
            return {"code": "error", "message": "invalid username or password", "data": None}

    try:
        response_data(FakeResponse())
    except RuntimeError as exc:
        assert str(exc) == "接口调用失败：HTTP 401，账号或密码错误"
    else:
        raise AssertionError("expected RuntimeError")


def test_local_launcher_can_parse_backend_port_pids():
    """验证`local`本地启动器`can`解析后端服务端口`pids`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from web.local_launcher import parse_netstat_pids

    output = """
      TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       12345
      TCP    127.0.0.1:8501         0.0.0.0:0              LISTENING       54321
      TCP    [::1]:8000             [::]:0                 LISTENING       67890
    """

    assert parse_netstat_pids(output, 8000) == {12345, 67890}


def test_knowledge_table_rows_have_chinese_headers():
    """已入库文档表格使用中文表头，并保留原始字段值。

    :return: 无返回值；断言表格字段映射。
    """
    from web.frontend_api import knowledge_table_rows

    docs = [
        {
            "id": 8,
            "source_path": r"F:\code\knowledge_agent\datas\制度.pdf",
            "title": "制度.pdf",
            "checksum": None,
            "chunk_count": 12,
            "created_at": "2026-09-01T10:00:00",
            "updated_at": "2026-09-01T11:00:00",
        }
    ]

    assert knowledge_table_rows(docs) == [
        {
            "编号": 8,
            "文件路径": r"F:\code\knowledge_agent\datas\制度.pdf",
            "文件名": "制度.pdf",
            "校验值": "—",
            "文本块数": 12,
            "创建时间": "2026-09-01 10:00",
            "更新时间": "2026-09-01 11:00",
        }
    ]


def test_backend_control_states_prevent_duplicate_start_and_invalid_stop():
    """后端控制按钮只允许当前状态下有效的操作。

    :return: 无返回值；断言各运行状态下的按钮状态。
    """
    from web.local_launcher import backend_control_states

    assert backend_control_states(running=False) == {
        "start": "normal",
        "stop": "disabled",
        "restart": "disabled",
    }
    assert backend_control_states(running=True) == {
        "start": "disabled",
        "stop": "normal",
        "restart": "normal",
    }
    assert backend_control_states(running=True, busy=True) == {
        "start": "disabled",
        "stop": "disabled",
        "restart": "disabled",
    }


def test_tool_events_are_appended_once_by_stable_event_id():
    """重复 SSE 事件只进入展示模型一次，不同调用均被保留。

    :return: 无返回值；断言事件稳定去重行为。
    """
    from web.frontend_api import append_unique_tool_event

    events: list[dict] = []
    first = {"event_id": "doc_retrieve:1", "tool": "doc_retrieve", "count": 2}
    second = {"event_id": "doc_retrieve:2", "tool": "doc_retrieve", "count": 2}

    assert append_unique_tool_event(events, first) is True
    assert append_unique_tool_event(events, first.copy()) is False
    assert append_unique_tool_event(events, second) is True
    assert events == [first, second]


def test_tool_event_details_show_sources_and_explicit_empty_results():
    """工具状态展开内容展示来源，零命中时不为空白。

    :return: 无返回值；断言工具事件详情文本。
    """
    from web.frontend_api import tool_event_details

    retrieval = {
        "tool": "doc_retrieve",
        "count": 3,
        "hits": [
            {"title": "员工手册.pdf", "page": 2},
            {"title": "员工手册.pdf", "page": 3},
            {"title": "报销制度.docx", "chunk": 4},
        ],
    }
    assert tool_event_details(retrieval) == [
        "员工手册.pdf（2 个片段，第 2、3 页）",
        "报销制度.docx（1 个片段，分块 4）",
    ]
    assert tool_event_details({"tool": "doc_retrieve", "count": 0}) == ["未检索到相关知识片段"]
    assert tool_event_details({"tool": "match_similar_ticket", "count": 0}) == ["未找到相似历史工单"]
    assert tool_event_details(
        {
            "tool": "match_similar_ticket",
            "count": 1,
            "hits": [{"ticket_id": 9, "title": "差旅报销咨询"}],
        }
    ) == ["工单 #9：差旅报销咨询"]


def test_ticket_suggestion_buttons_use_unique_stable_keys():
    """同一建议的两个操作按钮拥有不同且稳定的显式 key。

    :return: 无返回值；断言按钮 key 唯一且稳定。
    """
    from web.frontend_api import ticket_suggestion_action_keys

    keys = ticket_suggestion_action_keys("conversation-7", "suggestion-12")

    assert keys == {
        "create": "ticket_create_conversation-7_suggestion-12",
        "dismiss": "ticket_dismiss_conversation-7_suggestion-12",
    }
    assert keys["create"] != keys["dismiss"]


def test_ticket_suggestion_render_guard_allows_one_button_group_per_run():
    """同一次脚本运行不会为同一建议生成两组按钮。

    :return: 无返回值；断言同轮渲染认领规则。
    """
    from web.frontend_api import claim_ticket_suggestion_render

    rendered: set[str] = set()

    assert claim_ticket_suggestion_render(rendered, "conversation-7:suggestion-12") is True
    assert claim_ticket_suggestion_render(rendered, "conversation-7:suggestion-12") is False


def test_ticket_action_claim_prevents_fast_duplicate_creation():
    """同一建议的创建动作只能被当前会话状态认领一次。

    :return: 无返回值；断言重复动作被拒绝。
    """
    from web.frontend_api import claim_ticket_action

    claimed: set[str] = set()

    assert claim_ticket_action(claimed, "conversation-7:suggestion-12") is True
    assert claim_ticket_action(claimed, "conversation-7:suggestion-12") is False


def test_frontend_loads_messages_for_selected_conversation(monkeypatch):
    """切换会话时前端请求明确携带选中的会话 ID。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言请求路径和认证头。
    """
    from web import frontend_api

    captured: dict[str, object] = {}

    class Response:
        status_code = 200

        def json(self):
            """返回固定接口响应。

            :return: 返回模拟的会话消息数据。
            """
            return {"code": "ok", "message": "ok", "data": {"items": [{"question": "会话二"}]}}

    def fake_get(url, **kwargs):
        """记录模拟 GET 请求。

        :param url: 请求地址。
        :param kwargs: 请求关键字参数。
        :return: 返回模拟响应对象。
        """
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return Response()

    monkeypatch.setattr(frontend_api.requests, "get", fake_get)

    data = frontend_api.get_conversation_messages(22, "token", "http://api.test")

    assert captured["url"] == "http://api.test/api/chat/conversations/22/messages"
    assert captured["headers"] == {"Authorization": "Bearer token"}
    assert data["items"][0]["question"] == "会话二"


class _SessionState(dict):
    """供 Streamlit 页面函数测试使用的最小 session_state。"""

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class _Rerun(BaseException):
    pass


def _ticket_test_streamlit(clicked_label: str):
    """构造只覆盖工单建议交互所需的 Streamlit 替身。

    :param clicked_label: 本次模拟点击的按钮文字。
    :return: 返回最小 Streamlit 替身。
    """

    class Column:
        def __init__(self, owner):
            """保存所属 Streamlit 替身。

            :param owner: 所属 Streamlit 替身。
            :return: 无返回值；初始化列替身。
            """
            self.owner = owner

        def button(self, label, *, key, **kwargs):
            """记录按钮 key 并返回模拟点击状态。

            :param label: 按钮文字。
            :param key: 显式按钮 key。
            :param kwargs: 其他按钮参数。
            :return: 当前按钮被指定点击时返回真。
            """
            self.owner.keys[label] = key
            return label == clicked_label

    class FakeStreamlit:
        def __init__(self):
            """初始化页面测试状态。

            :return: 无返回值；初始化 Streamlit 替身。
            """
            self.keys = {}
            self.session_state = _SessionState(
                pending_ticket_suggestion={"title": "咨询", "content": "问题", "answer": "回答"},
                current_conversation_id=7,
                ticket_action_claims=set(),
                ticket_notice="",
                token="token",
                api_base_url="http://api.test",
            )

        def info(self, message):
            """接收提示文字。

            :param message: 提示内容。
            :return: 返回空值。
            """
            return None

        def columns(self, count):
            """创建两个按钮列。

            :param count: 请求的列数量。
            :return: 返回两个列替身。
            """
            return Column(self), Column(self)

        def rerun(self):
            """模拟 Streamlit rerun。

            :return: 不返回；通过异常中断本次运行。
            """
            raise _Rerun()

    return FakeStreamlit()


def test_ticket_creation_clears_pending_and_cannot_create_twice(monkeypatch):
    """创建成功后立即清空建议，重复执行不会再次创建。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言创建后的状态和调用次数。
    """
    from web import app

    fake_st = _ticket_test_streamlit("创建工单")
    calls: list[tuple] = []
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app, "create_ticket", lambda *args: calls.append(args) or {"id": 18})

    with pytest.raises(_Rerun):
        app.render_ticket_suggestion(set())

    assert fake_st.session_state.pending_ticket_suggestion is None
    assert fake_st.session_state.ticket_notice == "工单已提交审批：#18"
    app.render_ticket_suggestion(set())
    assert len(calls) == 1


def test_ticket_dismissal_clears_pending_immediately(monkeypatch):
    """拒绝创建后立即清空建议并触发安全 rerun。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言拒绝后的状态。
    """
    from web import app

    fake_st = _ticket_test_streamlit("暂不创建")
    monkeypatch.setattr(app, "st", fake_st)

    with pytest.raises(_Rerun):
        app.render_ticket_suggestion(set())

    assert fake_st.session_state.pending_ticket_suggestion is None


def test_select_conversation_synchronizes_widget_and_current_state(monkeypatch):
    """程序化切换会话会同步选择器和当前会话唯一状态。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言会话状态同步。
    """
    from web import app

    state = _SessionState(
        current_conversation_id=1,
        conversation_selector=1,
        messages=[{"role": "user", "content": "旧消息"}],
        messages_loaded_for=(1, 1),
        pending_ticket_suggestion={"title": "旧建议"},
        ticket_action_claims={"old"},
        last_chat={"answer": "旧回答"},
    )
    monkeypatch.setattr(app.st, "session_state", state)

    app.select_conversation(2)

    assert state.current_conversation_id == 2
    assert state.conversation_selector == 2
    assert state.messages == []
    assert state.messages_loaded_for is None


def test_deleted_current_conversation_switches_or_creates_exactly_one(monkeypatch):
    """删除当前会话后切换剩余会话；删除最后会话时仅创建一个。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言删除后的选择与单次创建。
    """
    from web import app

    state = _SessionState(
        user_id=1,
        current_conversation_id=2,
        conversation_selector=2,
        conversations=[
            {"id": 2, "sequence_no": 2, "title": "新对话 2"},
            {"id": 1, "sequence_no": 1, "title": "新对话 1"},
        ],
        messages=[],
        messages_loaded_for=None,
        pending_ticket_suggestion=None,
        ticket_action_claims=set(),
        last_chat=None,
    )
    monkeypatch.setattr(app.st, "session_state", state)
    created: list[int] = []

    app.apply_deleted_conversation(2, lambda: created.append(3) or {"id": 3, "sequence_no": 3, "title": "新对话 3"})
    assert state.current_conversation_id == 1
    assert state.conversation_selector == 1
    assert created == []

    app.apply_deleted_conversation(1, lambda: created.append(3) or {"id": 3, "sequence_no": 3, "title": "新对话 3"})
    assert state.current_conversation_id == 3
    assert state.conversation_selector == 3
    assert [item["id"] for item in state.conversations] == [3]
    assert created == [3]


class _ChatPlaceholder:
    """记录聊天占位内容。

    :return: 测试辅助对象，不直接产生返回值。
    """

    def __init__(self):
        """初始化内容列表。

        :return: 无返回值；初始化占位对象。
        """
        self.values = []

    def markdown(self, value):
        """记录 Markdown 内容。

        :param value: 页面写入内容。
        :return: 无返回值；记录内容。
        """
        self.values.append(value)


class _ChatContext:
    """提供聊天容器上下文。

    :return: 测试辅助对象，不直接产生返回值。
    """

    def __enter__(self):
        """进入容器。

        :return: 返回当前容器。
        """
        return self

    def __exit__(self, exc_type, exc, traceback):
        """退出容器。

        :param exc_type: 异常类型。
        :param exc: 异常对象。
        :param traceback: 异常堆栈。
        :return: 返回假，不屏蔽异常。
        """
        return False


class _ChatStreamlit:
    """覆盖 render_chat 所需接口的最小 Streamlit 替身。

    :return: 测试辅助对象，不直接产生返回值。
    """

    def __init__(self, question="提交的问题"):
        """初始化聊天页面状态。

        :param question: 模拟提交的问题。
        :return: 无返回值；初始化替身。
        """
        self.question = question
        self.reruns = 0
        self.chat_input_kwargs = {}
        self.session_state = _SessionState(
            token="token",
            user_id=1,
            api_base_url="http://api.test",
            current_conversation_id=2,
            conversation_selector=1,
            conversations=[
                {"id": 2, "sequence_no": 2, "title": "新对话 2"},
                {"id": 1, "sequence_no": 1, "title": "新对话 1"},
            ],
            conversations_loaded_for=1,
            messages=[],
            messages_loaded_for=(1, 2),
            pending_ticket_suggestion=None,
            ticket_action_claims=set(),
            ticket_notice="",
            conversation_notice="",
            conversation_error="",
            conversation_create_claimed=False,
            conversation_delete_claims=set(),
            last_chat=None,
            chat_processing=False,
        )

    def button(self, *args, **kwargs):
        """模拟未点击按钮。

        :param args: 按钮位置参数。
        :param kwargs: 按钮关键字参数。
        :return: 始终返回假。
        """
        return False

    def checkbox(self, *args, **kwargs):
        """模拟未勾选确认框。

        :param args: 复选框位置参数。
        :param kwargs: 复选框关键字参数。
        :return: 始终返回假。
        """
        return False

    def selectbox(self, label, options, **kwargs):
        """返回当前 widget state 对应的选项。

        :param label: 控件标签。
        :param options: 可选会话编号。
        :param kwargs: 其他控件参数。
        :return: 返回 selector 当前值。
        """
        return self.session_state.conversation_selector

    def subheader(self, value):
        """接收标题。

        :param value: 标题内容。
        :return: 无返回值。
        """
        return None

    def success(self, value):
        """接收成功提示。

        :param value: 提示内容。
        :return: 无返回值。
        """
        return None

    def chat_message(self, role):
        """创建聊天容器。

        :param role: 消息角色。
        :return: 返回上下文替身。
        """
        return _ChatContext()

    def markdown(self, value):
        """接收 Markdown。

        :param value: 页面内容。
        :return: 无返回值。
        """
        return None

    def chat_input(self, label, **kwargs):
        """返回一次模拟输入。

        :param label: 输入框标签。
        :param kwargs: 输入框的稳定键及禁用参数。
        :return: 返回模拟问题。
        """
        self.chat_input_kwargs = dict(kwargs)
        value, self.question = self.question, None
        return value

    def container(self):
        """创建普通容器。

        :return: 返回上下文替身。
        """
        return _ChatContext()

    def empty(self):
        """创建回答占位符。

        :return: 返回占位符替身。
        """
        return _ChatPlaceholder()

    def info(self, value):
        """接收信息提示。

        :param value: 提示内容。
        :return: 无返回值。
        """
        return None

    def error(self, value):
        """接收错误提示。

        :param value: 错误内容。
        :return: 无返回值。
        """
        return None

    def rerun(self):
        """记录意外 rerun 并中断。

        :return: 不返回；通过异常中断。
        """
        self.reruns += 1
        raise _Rerun()


def test_chat_submission_reaches_stream_before_any_selector_rerun(monkeypatch):
    """旧 selector 状态不得在提交问题后抢先触发 rerun。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言问题进入当前会话 SSE。
    """
    from web import app

    fake_st = _ChatStreamlit()
    calls = []
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app, "page_title", lambda *args: None)
    monkeypatch.setattr(app, "render_auth_gate", lambda: True)
    monkeypatch.setattr(app, "load_conversations", lambda: None)
    monkeypatch.setattr(app, "load_history_into_chat", lambda: None)
    monkeypatch.setattr(app, "render_ticket_suggestion", lambda *args: None)
    def fake_stream(question, token, base_url, conversation_id, request_id):
        """返回与提交标识一致的完成事件。

        :param question: 用户问题。
        :param token: 登录令牌。
        :param base_url: 后端基础地址。
        :param conversation_id: 提交时会话编号。
        :param request_id: 提交时请求标识。
        :return: 返回模拟 SSE 事件迭代器。
        """
        calls.append((question, conversation_id))
        return iter(
            [
                {
                    "event": "done",
                    "data": {
                        "answer": "成功回答",
                        "tool_events": [],
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "chat_history_id": 99,
                    },
                }
            ]
        )

    monkeypatch.setattr(app, "stream_chat", fake_stream)

    app.render_chat()

    assert calls == [("提交的问题", 2)]
    assert fake_st.reruns == 0
    assert fake_st.session_state.messages[0]["role"] == "user"
    assert fake_st.session_state.messages[0]["content"] == "提交的问题"
    assert fake_st.session_state.messages[0]["conversation_id"] == 2
    assert fake_st.session_state.messages[0]["request_id"]
    assert fake_st.session_state.messages[-1]["content"] == "成功回答"
    assert fake_st.chat_input_kwargs["submit_mode"] == "disable"
    assert fake_st.chat_input_kwargs["key"] == "chat_question_input"


def test_stream_failure_keeps_question_and_adds_assistant_error(monkeypatch):
    """SSE 失败时保留用户问题，并在对应助手位置写入中文错误。

    :param monkeypatch: pytest 运行时替换夹具。
    :return: 无返回值；断言失败消息模型。
    """
    from web import app

    fake_st = _ChatStreamlit()
    monkeypatch.setattr(app, "st", fake_st)
    monkeypatch.setattr(app, "page_title", lambda *args: None)
    monkeypatch.setattr(app, "render_auth_gate", lambda: True)
    monkeypatch.setattr(app, "load_conversations", lambda: None)
    monkeypatch.setattr(app, "load_history_into_chat", lambda: None)
    monkeypatch.setattr(app, "render_ticket_suggestion", lambda *args: None)
    monkeypatch.setattr(app, "stream_chat", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("connection refused")))

    app.render_chat()

    assert fake_st.session_state.messages[0]["content"] == "提交的问题"
    assert fake_st.session_state.messages[-1]["role"] == "assistant"
    assert fake_st.session_state.messages[-1]["error"] is True
    assert "无法连接后端服务" in fake_st.session_state.messages[-1]["content"]


def test_completed_tool_events_use_one_collapsed_expander_and_deduplicate(monkeypatch):
    """验证完成工具事件仅使用一个默认折叠容器。

    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证容器和去重。
    """
    from web import app

    calls = {"expanders": [], "events": []}

    class Context:
        def __enter__(self):
            """进入模拟上下文。

            :return: 返回当前上下文对象。
            """
            return self

        def __exit__(self, *args):
            """退出模拟上下文。

            :param args: 上下文退出参数。
            :return: 返回假以保留异常传播。
            """
            return False

    class FakeStreamlit:
        def expander(self, label, expanded):
            """记录折叠容器参数。

            :param label: 折叠标题。
            :param expanded: 默认展开状态。
            :return: 返回模拟上下文。
            """
            calls["expanders"].append((label, expanded))
            return Context()

    monkeypatch.setattr(app, "st", FakeStreamlit())
    monkeypatch.setattr(app, "render_tool_event", lambda event: calls["events"].append(event["event_id"]))
    events = [
        {"event_id": "one", "tool": "identity_check"},
        {"event_id": "one", "tool": "identity_check"},
        {"event_id": "two", "tool": "doc_retrieve"},
    ]

    app.render_tool_events(events)

    assert calls["expanders"] == [("工具调用过程", False)]
    assert calls["events"] == ["one", "two"]


def test_no_tool_events_does_not_render_empty_expander(monkeypatch):
    """验证没有工具事件时不创建空容器。

    :param monkeypatch: 运行时替换夹具。
    :return: 无返回值；函数通过断言验证空事件行为。
    """
    from web import app

    class FakeStreamlit:
        def expander(self, *args, **kwargs):
            """拒绝意外创建折叠容器。

            :param args: 折叠容器位置参数。
            :param kwargs: 折叠容器关键字参数。
            :return: 无正常返回；函数抛出断言异常。
            """
            raise AssertionError("不应创建空 expander")

    monkeypatch.setattr(app, "st", FakeStreamlit())
    app.render_tool_events([])


def test_done_event_must_match_submitted_request_and_conversation():
    """验证完成事件必须匹配请求、会话和持久化记录。

    :return: 无返回值；函数通过断言验证完成事件。
    """
    from web.app import valid_done_event

    valid = {
        "request_id": "req-1",
        "conversation_id": 7,
        "chat_history_id": 10,
        "answer": "回答",
    }
    assert valid_done_event(valid, "req-1", 7) is True
    assert valid_done_event({**valid, "request_id": "req-2"}, "req-1", 7) is False
    assert valid_done_event({**valid, "conversation_id": 8}, "req-1", 7) is False
    assert valid_done_event({**valid, "chat_history_id": None}, "req-1", 7) is False


def test_all_streamlit_controls_have_explicit_stable_keys():
    """验证所有 Streamlit 输入控件都声明稳定键。

    :return: 无返回值；函数通过 AST 断言控件键完整。
    """
    widget_names = {
        "button",
        "checkbox",
        "selectbox",
        "radio",
        "text_input",
        "text_area",
        "number_input",
        "date_input",
        "time_input",
        "file_uploader",
        "form_submit_button",
        "download_button",
        "chat_input",
    }
    app_path = Path(__file__).resolve().parents[1] / "web" / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in widget_names:
            continue
        if not any(keyword.arg == "key" for keyword in node.keywords):
            missing.append((node.lineno, node.func.attr))
    assert missing == []
