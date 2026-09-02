from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERIC_ERROR = "操作失败，请稍后重试；详细原因已记录到服务日志。"


def _frontend_api():
    """加载前端 API 模块。

    :return: 前端 API 模块。
    """
    from web import frontend_api

    return frontend_api


def _require(name: str):
    """获取本次中文化要求的前端函数。

    :param name: 函数名称。
    :return: 可调用的前端函数。
    """
    value = getattr(_frontend_api(), name, None)
    assert callable(value), f"web.frontend_api 需要提供 {name}"
    return value


def test_role_internal_values_are_displayed_in_chinese():
    """验证内部角色值展示为中文。

    :return: 无返回值。
    """
    role_label = _require("role_label")

    assert role_label("admin") == "管理员"
    assert role_label("employee") == "普通员工"
    assert role_label("hr") == "人事"
    assert role_label("finance") == "财务"
    assert role_label("ops") == "运维"


def test_all_ticket_statuses_are_displayed_in_chinese():
    """验证全部工单状态展示为中文。

    :return: 无返回值。
    """
    status_label = _require("ticket_status_label")

    assert {value: status_label(value) for value in ("pending", "approved", "rejected", "closed")} == {
        "pending": "待审批",
        "approved": "已批准",
        "rejected": "已驳回",
        "closed": "已关闭",
    }


def test_all_ticket_types_are_displayed_in_chinese():
    """验证全部工单类型展示为中文。

    :return: 无返回值。
    """
    type_label = _require("ticket_type_label")

    assert type_label("consultation") == "普通咨询"
    assert type_label("leave") == "请假申请"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "是"), (False, "否"), (None, "—"), ("", "—")],
)
def test_ui_values_do_not_expose_python_boolean_or_empty_values(value, expected):
    """验证布尔值和空值使用中文界面表示。

    :param value: 原始值。
    :param expected: 期望展示值。
    :return: 无返回值。
    """
    assert _require("format_ui_value")(value) == expected


def test_ui_datetime_uses_human_readable_minute_format():
    """验证日期时间展示到分钟且不含 ISO 分隔符。

    :return: 无返回值。
    """
    format_ui_datetime = _require("format_ui_datetime")

    assert format_ui_datetime("2026-09-02T09:00:31") == "2026-09-02 09:00"
    assert format_ui_datetime(None) == "—"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "登录状态已失效，请重新登录"),
        (403, "当前账号没有执行此操作的权限"),
        (404, "请求的数据不存在或无权访问"),
        (409, "请求已处理，请勿重复提交"),
        (422, "提交内容格式不正确"),
        (429, "操作过于频繁，请稍后重试"),
        (500, "服务处理失败，请稍后重试"),
    ],
)
def test_common_http_errors_have_chinese_fallbacks(status_code, expected):
    """验证常见 HTTP 状态使用中文兜底提示。

    :param status_code: HTTP 状态码。
    :param expected: 期望中文提示。
    :return: 无返回值。
    """
    localize_http_error = _require("localize_http_error")

    assert localize_http_error(status_code, "Unmapped backend exception") == expected


@pytest.mark.parametrize(
    "message",
    [
        "conversation not found",
        "chat history not found",
        "ticket not found",
        "document not found",
        "document source not found",
        "invalid username or password",
        "username already exists",
        "admin approval required",
        "unsupported ticket status",
        "unsupported ticket type",
        "invalid leave application",
        "request already exists",
        "permission denied",
        "unauthorized",
        "forbidden",
        "connection refused",
        "timeout",
        "rate limit exceeded",
        "validation error",
        "field required",
        "LLM returned empty content",
        "interface did not return a valid completion event",
    ],
)
def test_known_backend_errors_are_localized_without_original_english(message):
    """验证已知后端错误不会泄露原始英文。

    :param message: 后端英文错误。
    :return: 无返回值。
    """
    localized = _frontend_api().localize_error_message(message)

    assert any("\u4e00" <= char <= "\u9fff" for char in localized)
    assert message.lower() not in localized.lower()


def test_unknown_english_exception_is_not_exposed_to_user():
    """验证未知英文异常使用安全统一提示。

    :return: 无返回值。
    """
    localize = _frontend_api().localize_error_message

    assert localize("OperationalError: secret database detail") == GENERIC_ERROR


def test_navigation_and_product_title_are_chinese():
    """验证页面导航和产品标题均为中文。

    :return: 无返回值。
    """
    api = _frontend_api()
    app_source = (PROJECT_ROOT / "web" / "app.py").read_text(encoding="utf-8")

    assert api.PAGE_NAMES == ["登录", "对话", "对话记录", "请假申请", "工单", "上传", "账号"]
    assert 'page_title="企业知识智能助手"' in app_source
    assert 'page_title("企业知识智能助手"' in app_source
    assert 'page_title="Knowledge Agent"' not in app_source
    assert 'page_title("Knowledge Agent"' not in app_source


def test_streamlit_page_fixed_copy_has_no_unnecessary_english():
    """验证 Streamlit 固定界面文案不含多余英文。

    :return: 无返回值。
    """
    source = (PROJECT_ROOT / "web" / "app.py").read_text(encoding="utf-8")

    for english_ui in (
        "Knowledge Agent",
        "Login failed",
        "Request failed",
        "Loading",
        "No history",
        "User:",
        "Assistant:",
    ):
        assert english_ui not in source
    assert 'st.json({"upload": upload_result, "rebuild": rebuild_result})' not in source


def test_local_launcher_fixed_controls_and_prompts_are_chinese():
    """验证本地启动器固定控件和弹窗按钮均为中文。

    :return: 无返回值。
    """
    source_path = PROJECT_ROOT / "web" / "local_launcher.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    visible_methods = {"title", "showinfo", "showwarning", "showerror", "askyesno"}
    visible_values: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if func_name in visible_methods:
            visible_values.extend(
                arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )

    assert "本地启动器" in source
    assert "启动后端" in source
    assert "停止后端" in source
    assert "重启后端" in source
    assert all("Knowledge Agent" not in value for value in visible_values)
    assert "simpledialog.askstring" not in source
    assert 'text="确定"' in source
    assert 'text="取消"' in source


def test_local_launcher_unknown_exception_is_not_exposed():
    """验证启动器不会展示未知英文异常。

    :return: 无返回值。
    """
    from web import local_launcher

    localize = getattr(local_launcher, "localize_launcher_error", None)
    assert callable(localize), "本地启动器需要统一转换用户可见异常"
    assert localize(RuntimeError("sqlite secret failure")) == GENERIC_ERROR


def test_server_logs_original_exception_but_returns_safe_message(caplog):
    """验证服务日志保留异常且响应使用安全中文提示。

    :param caplog: pytest 日志捕获夹具。
    :return: 无返回值。
    """
    from agent_server.api.utils import uniform_exception_middleware

    async def failing_handler(_request):
        """模拟抛出底层异常的请求处理器。

        :param _request: 模拟请求对象。
        :return: 不返回，始终抛出异常。
        """
        raise RuntimeError("private backend stack detail")

    response = asyncio.run(uniform_exception_middleware(object(), failing_handler))
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 500
    assert payload["message"] == GENERIC_ERROR
    assert "private backend stack detail" not in payload["message"]
    assert "private backend stack detail" in caplog.text


def test_ticket_table_rows_have_chinese_headers_and_localized_values():
    """验证工单表格使用中文表头和展示值。

    :return: 无返回值。
    """
    rows = _require("ticket_table_rows")(
        [
            {
                "id": 7,
                "creator_username": "alice",
                "title": None,
                "ticket_type": "leave",
                "status": "pending",
                "content": "请假",
                "answer": None,
                "created_at": "2026-09-02T09:00:31",
            }
        ]
    )

    assert rows == [
        {
            "编号": 7,
            "申请人": "alice",
            "标题": "—",
            "类型": "请假申请",
            "状态": "待审批",
            "问题": "请假",
            "答复": "—",
            "创建时间": "2026-09-02 09:00",
        }
    ]


def test_history_and_account_tables_localize_empty_values_and_datetimes():
    """验证记录和账号表格转换空值、角色与时间。

    :return: 无返回值。
    """
    history_rows = _require("history_table_rows")(
        [{"id": 2, "question": "问题", "answer": None, "ticket_id": None, "created_at": "2026-09-02T09:00:31"}]
    )
    account_rows = _require("account_table_rows")(
        [{"id": 3, "username": "bob", "role": "employee", "created_at": "2026-09-02T09:00:31"}]
    )

    assert history_rows == [
        {"编号": 2, "问题": "问题", "答复": "—", "关联工单": "—", "创建时间": "2026-09-02 09:00"}
    ]
    assert account_rows == [
        {"编号": 3, "账号": "bob", "身份": "普通员工", "创建时间": "2026-09-02 09:00"}
    ]


def test_backend_error_answer_is_localized_but_normal_model_answer_is_unchanged():
    """验证仅错误答复被转换，正常模型答复保持原文。

    :return: 无返回值。
    """
    display_chat_answer = _require("display_chat_answer")

    assert display_chat_answer("LLM returned empty content", is_error=True) == "模型未返回有效内容"
    assert display_chat_answer("English policy title: PTO", is_error=False) == "English policy title: PTO"


def test_knowledge_table_rows_format_null_and_datetime_values():
    """验证知识库表格转换空值和日期时间。

    :return: 无返回值。
    """
    rows = _frontend_api().knowledge_table_rows(
        [
            {
                "id": 8,
                "source_path": r"F:\code\knowledge_agent\datas\制度.pdf",
                "title": "制度.pdf",
                "checksum": None,
                "chunk_count": 12,
                "created_at": "2026-09-01T10:00:00",
                "updated_at": None,
            }
        ]
    )

    assert rows[0]["校验值"] == "—"
    assert rows[0]["创建时间"] == "2026-09-01 10:00"
    assert rows[0]["更新时间"] == "—"


def test_ticket_statistics_csv_has_chinese_headers_and_utf8_bom():
    """验证工单统计 CSV 使用中文表头和 UTF-8 BOM。

    :return: 无返回值。
    """
    content = _require("ticket_statistics_csv")(
        {"total": 4, "by_status": {"pending": 2, "approved": 1, "closed": 1}}
    )

    assert content.startswith(b"\xef\xbb\xbf")
    decoded = content.decode("utf-8-sig")
    assert decoded.splitlines()[0] == "状态,数量"
    assert "全部,4" in decoded
    assert "待审批,2" in decoded
    assert "已批准,1" in decoded
    assert "已关闭,1" in decoded
    assert "pending" not in decoded


def test_display_mapping_does_not_change_internal_api_values():
    """验证展示映射不会修改 API 内部值。

    :return: 无返回值。
    """
    api = _frontend_api()
    payload = {"role": "admin", "status": "pending", "ticket_type": "consultation"}

    assert api.role_label(payload["role"]) == "管理员"
    assert api.ticket_status_label(payload["status"]) == "待审批"
    assert api.ticket_type_label(payload["ticket_type"]) == "普通咨询"
    assert payload == {"role": "admin", "status": "pending", "ticket_type": "consultation"}


def test_prompt_defaults_to_chinese_and_mock_answer_is_chinese():
    """验证提示词默认中文且模拟回答不含英文固定文案。

    :return: 无返回值。
    """
    from agent_server.core.llm_client import MOCK_LLM_RESPONSE
    from agent_server.graph_flow.prompt_template import SYSTEM_PROMPT

    mock_payload = json.loads(MOCK_LLM_RESPONSE)
    assert "默认使用中文回答" in SYSTEM_PROMPT
    assert "mock" not in mock_payload["answer"].lower()
    assert "mock" not in mock_payload["title"].lower()
