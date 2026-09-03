from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.frontend_api import (
    ERROR_MESSAGE_MAP,
    PAGE_NAMES,
    account_table_rows,
    append_unique_tool_event,
    api_base_url,
    change_password,
    claim_ticket_action,
    claim_ticket_suggestion_render,
    create_conversation,
    create_leave_application,
    create_ticket,
    create_user,
    bulk_approve_consultations,
    bulk_process_open_tickets,
    delete_knowledge_doc,
    delete_chat_history,
    delete_conversation,
    delete_user,
    describe_tool_event,
    display_chat_answer,
    export_ticket_stat,
    get_knowledge_content,
    get_me,
    get_conversation_messages,
    knowledge_table_rows,
    history_table_rows,
    localize_error_message,
    list_chat_history,
    list_conversations,
    list_knowledge,
    list_tickets,
    list_users,
    login,
    rebuild_knowledge,
    resolve_page,
    reset_user_password,
    stream_chat,
    format_ui_datetime,
    format_ui_value,
    role_label,
    ticket_statistics_csv,
    ticket_status_label,
    ticket_table_rows,
    ticket_type_label,
    ticket_suggestion_action_keys,
    ticket_suggestion_id,
    tool_event_details,
    update_ticket_status,
    upload_knowledge_file,
)


st.set_page_config(page_title="企业知识智能助手", page_icon=None, layout="wide")


DEFAULT_PASSWORD = "123456"
UI_ERROR_MESSAGE_MAP = ERROR_MESSAGE_MAP


def init_state() -> None:
    """初始化状态。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    defaults = {
        "api_base_url": api_base_url(),
        "token": "",
        "user_id": None,
        "username": "",
        "role": "",
        "tier": "",
        "messages": [],
        "messages_loaded_for": None,
        "conversations": [],
        "conversations_loaded_for": None,
        "last_chat": None,
        "pending_ticket_suggestion": None,
        "ticket_action_claims": set(),
        "conversation_delete_claims": set(),
        "conversation_create_claimed": False,
        "conversation_create_request_id": uuid4().hex,
        "conversation_notice": "",
        "conversation_error": "",
        "ticket_notice": "",
        "current_conversation_id": None,
        "account_notice": "",
        "chat_processing": False,
        "leave_submit_claim": None,
        "leave_request_id": uuid4().hex,
        "leave_notice": "",
        "bulk_approve_claimed": False,
        "bulk_approve_notice": "",
        "bulk_process_claimed": False,
        "bulk_process_notice": "",
        "history_conversation_id": None,
        "history_items": [],
        "history_has_more": False,
        "history_loaded_for": None,
        "history_notice": "",
        "history_error": "",
        "history_delete_claims": set(),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def is_logged_in() -> bool:
    """判断`logged``in`。

    :return: 返回判断`logged``in`得到的结果，返回类型为 ``bool``。
    """
    return bool(st.session_state.get("token"))


def is_admin() -> bool:
    """判断管理员。

    :return: 返回判断管理员得到的结果，返回类型为 ``bool``。
    """
    return st.session_state.get("tier") == "admin" or st.session_state.get("role") == "admin"


def page_title(title: str, caption: str = "") -> None:
    """页面`title`。

    :param title: 函数处理所需的“`title`”数据，类型为 ``str``。
    :param caption: 函数处理所需的“生成说明文本”数据，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    st.title(title)
    if caption:
        st.caption(caption)


def localize_ui_error(error: Exception) -> str:
    """本地化界面错误信息。

    :param error: 函数处理所需的“错误信息”数据，类型为 ``Exception``。
    :return: 返回本地化界面错误信息得到的结果，返回类型为 ``str``。
    """
    return localize_error_message(error)


def show_error(error: Exception) -> None:
    """显示错误信息。

    :param error: 函数处理所需的“错误信息”数据，类型为 ``Exception``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    st.error(localize_ui_error(error))


status_label = ticket_status_label


def load_history_into_chat() -> None:
    """加载历史记录`into`处理对话。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    conversation_id = st.session_state.get("current_conversation_id")
    loaded_key = (st.session_state.user_id, conversation_id)
    if not conversation_id or st.session_state.messages_loaded_for == loaded_key:
        return
    try:
        items = get_conversation_messages(
            int(conversation_id), st.session_state.token, st.session_state.api_base_url
        ).get("items", [])
    except Exception as exc:
        show_error(exc)
        return

    messages: list[dict[str, Any]] = []
    for item in items:
        question = str(item.get("question") or "")
        answer = str(item.get("answer") or "")
        if question:
            messages.append(
                {
                    "role": "user",
                    "content": question,
                    "request_id": item.get("request_id"),
                    "conversation_id": item.get("conversation_id"),
                }
            )
        if answer:
            messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "tool_events": item.get("tool_events") or [],
                    "request_id": item.get("request_id"),
                    "conversation_id": item.get("conversation_id"),
                    "chat_history_id": item.get("id"),
                    "error": bool(item.get("is_error")),
                }
            )
    st.session_state.messages = messages
    st.session_state.messages_loaded_for = loaded_key


def load_conversations() -> None:
    """加载当前账号会话列表；首次进入时建立一个空白会话。

    :return: 无返回值；函数更新 Streamlit 会话状态。
    """
    if st.session_state.conversations_loaded_for == st.session_state.user_id:
        if st.session_state.current_conversation_id is not None:
            st.session_state.conversation_selector = int(st.session_state.current_conversation_id)
        return
    conversations = list_conversations(st.session_state.token, st.session_state.api_base_url).get("items", [])
    if not conversations:
        conversations = [
            create_conversation(
                st.session_state.token,
                st.session_state.api_base_url,
                request_id=st.session_state.conversation_create_request_id,
            )
        ]
        st.session_state.conversation_create_request_id = uuid4().hex
    st.session_state.conversations = conversations
    ids = {int(item["id"]) for item in conversations}
    if st.session_state.current_conversation_id not in ids:
        select_conversation(int(conversations[0]["id"]))
    else:
        st.session_state.conversation_selector = int(st.session_state.current_conversation_id)
    st.session_state.conversations_loaded_for = st.session_state.user_id


def select_conversation(conversation_id: int, sync_selector: bool = True) -> None:
    """切换当前会话并清理仅属于上一会话的页面状态。

    :param conversation_id: 目标会话编号。
    :param sync_selector: 是否同步写入 selectbox widget state。
    :return: 无返回值；函数更新 Streamlit 会话状态。
    """
    changed = st.session_state.current_conversation_id != conversation_id
    st.session_state.current_conversation_id = conversation_id
    if sync_selector:
        st.session_state.conversation_selector = conversation_id
    if not changed:
        return
    st.session_state.messages = []
    st.session_state.messages_loaded_for = None
    st.session_state.pending_ticket_suggestion = None
    st.session_state.ticket_action_claims = set()
    st.session_state.last_chat = None


def conversation_selector_changed() -> None:
    """通过 selectbox 回调切换当前会话。

    :return: 无返回值；函数读取 widget state 并同步当前会话。
    """
    selected = st.session_state.get("conversation_selector")
    if selected is not None:
        select_conversation(int(selected), sync_selector=False)


def apply_deleted_conversation(conversation_id: int, create_replacement) -> None:
    """将删除结果应用到前端状态，必要时只创建一个替代会话。

    :param conversation_id: 已删除的会话编号。
    :param create_replacement: 无剩余会话时调用一次的创建函数。
    :return: 无返回值；函数切换到有效会话并清理旧会话状态。
    """
    remaining = [
        item for item in st.session_state.conversations if int(item["id"]) != conversation_id
    ]
    if not remaining:
        remaining = [create_replacement()]
    st.session_state.conversations = remaining
    select_conversation(int(remaining[0]["id"]))
    st.session_state.messages = []
    st.session_state.messages_loaded_for = None
    st.session_state.pending_ticket_suggestion = None
    st.session_state.ticket_action_claims = set()
    st.session_state.last_chat = None
    st.session_state.conversations_loaded_for = st.session_state.user_id


def apply_delete_result(result: dict[str, Any]) -> None:
    """应用后端事务返回的删除及后继会话。

    :param result: 后端删除接口返回的数据。
    :return: 无返回值；函数同步当前会话状态。
    """
    deleted_id = int(result["deleted"]["id"])
    active = result["active_conversation"]
    remaining = [
        item for item in st.session_state.conversations if int(item["id"]) != deleted_id
    ]
    if not any(int(item["id"]) == int(active["id"]) for item in remaining):
        remaining.insert(0, active)
    st.session_state.conversations = remaining
    select_conversation(int(active["id"]))
    st.session_state.conversations_loaded_for = st.session_state.user_id


def create_conversation_clicked() -> None:
    """处理一次新建会话按钮回调并同步所有会话状态。

    :return: 无返回值；函数创建会话并激活它。
    """
    if st.session_state.conversation_create_claimed:
        return
    st.session_state.conversation_create_claimed = True
    try:
        conversation = create_conversation(
            st.session_state.token,
            st.session_state.api_base_url,
            request_id=st.session_state.conversation_create_request_id,
        )
        st.session_state.conversations.append(conversation)
        select_conversation(int(conversation["id"]))
        st.session_state.conversations_loaded_for = st.session_state.user_id
        st.session_state.conversation_create_request_id = uuid4().hex
    except Exception as exc:
        st.session_state.conversation_error = localize_ui_error(exc)
    finally:
        st.session_state.conversation_create_claimed = False


def delete_conversation_clicked(conversation_id: int, confirm_key: str) -> None:
    """处理一次删除会话按钮回调，防止重复删除和重复补建。

    :param conversation_id: 待删除的当前会话编号。
    :param confirm_key: 当前会话确认框的 widget key。
    :return: 无返回值；函数删除并切换到有效会话。
    """
    claim = f"delete:{conversation_id}"
    if claim in st.session_state.conversation_delete_claims:
        return
    st.session_state.conversation_delete_claims.add(claim)
    try:
        result = delete_conversation(
            conversation_id, st.session_state.token, st.session_state.api_base_url
        )
        apply_delete_result(result)
        st.session_state.pop(confirm_key, None)
        st.session_state.conversation_notice = "当前对话已删除"
    except Exception as exc:
        st.session_state.conversation_delete_claims.discard(claim)
        st.session_state.conversation_error = localize_ui_error(exc)


def render_ticket_suggestion(rendered: set[str] | None = None) -> None:
    """渲染工单`suggestion`。

    :param rendered: 本次脚本运行已渲染的建议标识集合。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    suggestion = st.session_state.get("pending_ticket_suggestion")
    if not suggestion:
        return
    conversation_id = str(st.session_state.get("current_conversation_id") or "default")
    suggestion_id = ticket_suggestion_id(suggestion)
    suggestion_key = f"{conversation_id}:{suggestion_id}"
    if not claim_ticket_suggestion_render(rendered if rendered is not None else set(), suggestion_key):
        return
    keys = ticket_suggestion_action_keys(conversation_id, suggestion_id)
    st.info("系统建议可创建咨询工单，是否提交给管理员审批？")
    col_create, col_clear = st.columns(2)
    if col_create.button("创建工单", key=keys["create"], width="stretch"):
        if not claim_ticket_action(st.session_state.ticket_action_claims, suggestion_key):
            return
        try:
            ticket = create_ticket(
                str(suggestion.get("title") or "咨询工单"),
                str(suggestion.get("content") or ""),
                str(suggestion.get("answer") or ""),
                st.session_state.token,
                st.session_state.api_base_url,
            )
            st.session_state.pending_ticket_suggestion = None
            st.session_state.ticket_notice = f"工单已提交审批：#{ticket.get('id')}"
            st.rerun()
        except Exception as exc:
            st.session_state.ticket_action_claims.discard(suggestion_key)
            show_error(exc)
    if col_clear.button("暂不创建", key=keys["dismiss"], width="stretch"):
        st.session_state.pending_ticket_suggestion = None
        st.rerun()


def conversation_display_items(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按稳定顺序生成仅供界面使用的连续会话序号。

    :param conversations: 后端返回的真实会话列表。
    :return: 返回附带连续显示序号和规范标题的会话列表。
    """
    ordered = sorted(
        conversations,
        key=lambda item: (str(item.get("created_at") or ""), int(item["id"])),
    )
    result: list[dict[str, Any]] = []
    for display_no, conversation in enumerate(ordered, start=1):
        item = dict(conversation)
        title = str(item.get("title") or "新对话")
        if title == f"新对话 {item.get('sequence_no')}":
            title = "新对话"
        item["display_no"] = display_no
        item["display_title"] = title
        result.append(item)
    return result


def render_sidebar() -> str:
    """渲染侧边栏。

    :return: 返回渲染侧边栏得到的结果，返回类型为 ``str``。
    """
    with st.sidebar:
        st.subheader("服务")
        st.session_state.api_base_url = st.text_input(
            "接口地址", value=st.session_state.api_base_url, key="sidebar_api_base_url"
        )

        if is_logged_in():
            st.divider()
            st.write(f"用户：{st.session_state.username}")
            st.write(f"角色：{role_label(st.session_state.role)}")
            st.success("已登录")
            if st.button("退出登录", key="sidebar_logout", width="stretch"):
                for key in ("token", "username", "role", "tier"):
                    st.session_state[key] = ""
                st.session_state.user_id = None
                st.session_state.messages = []
                st.session_state.messages_loaded_for = None
                st.session_state.conversations = []
                st.session_state.conversations_loaded_for = None
                st.session_state.last_chat = None
                st.session_state.pending_ticket_suggestion = None
                st.session_state.ticket_action_claims = set()
                st.session_state.conversation_delete_claims = set()
                st.session_state.conversation_create_claimed = False
                st.session_state.conversation_notice = ""
                st.session_state.conversation_error = ""
                st.session_state.ticket_notice = ""
                st.session_state.current_conversation_id = None
                st.session_state.account_notice = ""
                st.session_state.chat_processing = False
                st.session_state.leave_submit_claim = None
                st.session_state.leave_request_id = uuid4().hex
                st.session_state.bulk_approve_claimed = False
                st.session_state.pop("conversation_selector", None)
                st.rerun()

        pages = PAGE_NAMES if not is_logged_in() else [page for page in PAGE_NAMES if page != "登录"]
        navigation_key = "sidebar_page_authenticated" if is_logged_in() else "sidebar_page_guest"
        selected_page = st.radio(
            "页面", pages, key=navigation_key, horizontal=False, label_visibility="collapsed"
        )
        query_page = st.query_params.get("page")
        page = resolve_page(selected_page, query_page)
        if is_logged_in() and page == "登录":
            return pages[0]
        return page


def render_login() -> None:
    """渲染执行登录。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("企业知识智能助手", "输入账号和密码后进入问答与工单系统。")
    if is_logged_in():
        st.success(f"已登录：{st.session_state.username} / {role_label(st.session_state.role)}")
        st.info("请从左侧进入对话、工单、上传或账号管理。")
        return

    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.form("login_form"):
            username = st.text_input("账号", key="login_username")
            password = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录", key="login_submit", width="stretch")

        if submitted:
            try:
                data = login(username, password, st.session_state.api_base_url)
                token = data["token"]
                me = get_me(token, st.session_state.api_base_url)
                st.session_state.token = token
                st.session_state.user_id = me.get("id")
                st.session_state.username = me.get("username", username)
                st.session_state.role = me.get("role", data.get("role", ""))
                st.session_state.tier = me.get("tier", data.get("tier", ""))
                st.session_state.messages = []
                st.session_state.messages_loaded_for = None
                st.session_state.conversations = []
                st.session_state.conversations_loaded_for = None
                st.session_state.current_conversation_id = None
                st.session_state.conversation_delete_claims = set()
                st.session_state.conversation_create_claimed = False
                st.session_state.conversation_notice = ""
                st.session_state.conversation_error = ""
                st.session_state.chat_processing = False
                st.session_state.leave_submit_claim = None
                st.session_state.leave_request_id = uuid4().hex
                st.session_state.bulk_approve_claimed = False
                st.session_state.pending_ticket_suggestion = None
                st.success("登录成功")
                st.rerun()
            except Exception as exc:
                show_error(exc)

    with right:
        st.markdown("#### 当前连接")
        st.code(st.session_state.api_base_url, language="text")
        if is_logged_in():
            st.success(f"已登录：{st.session_state.username} / {role_label(st.session_state.role)}")
        else:
            st.info("请使用后端已注册账号登录。")


def render_auth_gate() -> bool:
    """渲染认证`gate`。

    :return: 返回渲染认证`gate`得到的结果，返回类型为 ``bool``。
    """
    if is_logged_in():
        return True
    st.warning("请先登录。")
    return False


def render_chat() -> None:
    """渲染处理对话。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("对话", "流式接收工具事件和最终答复。")
    if not render_auth_gate():
        return

    try:
        load_conversations()
    except Exception as exc:
        show_error(exc)
        return

    st.button(
        "新建对话",
        key="new_conversation",
        width="stretch",
        on_click=create_conversation_clicked,
    )

    if st.session_state.conversation_notice:
        st.success(st.session_state.conversation_notice)
        st.session_state.conversation_notice = ""
    if st.session_state.conversation_error:
        st.error(st.session_state.conversation_error)
        st.session_state.conversation_error = ""

    conversations = conversation_display_items(st.session_state.conversations)
    st.session_state.conversations = conversations
    current_id = int(st.session_state.current_conversation_id)
    conversation_by_id = {int(item["id"]): item for item in conversations}
    st.selectbox(
        "会话列表",
        list(conversation_by_id),
        format_func=lambda conversation_id: (
            f"{conversation_by_id[conversation_id]['display_no']} · "
            f"{conversation_by_id[conversation_id]['display_title']}"
        ),
        key="conversation_selector",
        on_change=conversation_selector_changed,
    )

    current = conversation_by_id[current_id]
    st.subheader(f"{current['display_no']} · {current['display_title']}")

    confirm_delete_key = f"confirm_delete_conversation_{current_id}"
    delete_button_key = f"delete_conversation_{current_id}"
    confirm_delete = st.checkbox("确认删除当前对话", key=confirm_delete_key)
    st.button(
        "删除当前对话",
        key=delete_button_key,
        disabled=not confirm_delete,
        width="stretch",
        on_click=delete_conversation_clicked,
        args=(current_id, confirm_delete_key),
    )
    load_history_into_chat()

    if st.session_state.ticket_notice:
        st.success(st.session_state.ticket_notice)
        st.session_state.ticket_notice = ""

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("error"):
                st.error(message["content"])
            else:
                st.markdown(message["content"])
            if message["role"] == "assistant":
                render_tool_events(message.get("tool_events") or [])

    render_ticket_suggestion(set())

    question = st.chat_input(
        "请输入问题",
        key="chat_question_input",
        submit_mode="disable",
        disabled=bool(st.session_state.chat_processing),
    )
    if not question:
        return

    submitted_conversation_id = int(st.session_state.current_conversation_id)
    request_id = uuid4().hex
    st.session_state.chat_processing = True
    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
            "request_id": request_id,
            "conversation_id": submitted_conversation_id,
        }
    )
    with st.chat_message("user"):
        st.markdown(question)

    current_tool_events: list[dict[str, Any]] = []
    final_data: dict[str, Any] | None = None

    with st.chat_message("assistant"):
        tool_placeholder = st.container()
        answer_placeholder = st.empty()
        try:
            for event in stream_chat(
                question,
                st.session_state.token,
                st.session_state.api_base_url,
                conversation_id=submitted_conversation_id,
                request_id=request_id,
            ):
                if event["event"] == "tool" and isinstance(event["data"], dict):
                    if append_unique_tool_event(current_tool_events, event["data"]):
                        with tool_placeholder:
                            if len(current_tool_events) == 1:
                                st.markdown("#### 工具调用过程")
                            render_tool_event(event["data"])
                elif event["event"] in {"token", "delta"}:
                    answer_placeholder.markdown(str(event["data"]))
                elif event["event"] == "done" and isinstance(event["data"], dict):
                    if valid_done_event(event["data"], request_id, submitted_conversation_id):
                        final_data = event["data"]

            if final_data is None:
                raise RuntimeError("接口未返回有效完成事件")
            answer = display_chat_answer(final_data["answer"], is_error=bool(final_data.get("error")))
            if final_data.get("error"):
                answer_placeholder.error(answer)
            else:
                answer_placeholder.markdown(answer)

            ticket_id = (final_data or {}).get("ticket_id")
            if ticket_id:
                st.info(f"关联工单：#{ticket_id}")
            if ticket_id:
                st.session_state.pending_ticket_suggestion = None
            else:
                suggestion = (final_data or {}).get("ticket_suggestion")
                st.session_state.pending_ticket_suggestion = suggestion if suggestion else None
            st.session_state.last_chat = final_data
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "tool_events": current_tool_events,
                    "request_id": request_id,
                    "conversation_id": submitted_conversation_id,
                    "chat_history_id": final_data["chat_history_id"],
                    "error": bool(final_data.get("error")),
                }
            )
            st.session_state.messages_loaded_for = None
            if st.session_state.current_conversation_id == submitted_conversation_id:
                load_history_into_chat()
            st.session_state.conversations_loaded_for = None
            if current.get("display_title") == "新对话":
                current["title"] = question[:24]
                current["display_title"] = question[:24]
            if st.session_state.pending_ticket_suggestion:
                st.rerun()
        except Exception as exc:
            error_message = localize_ui_error(exc)
            answer_placeholder.markdown(f"请求失败：{error_message}")
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"请求失败：{error_message}",
                    "tool_events": current_tool_events,
                    "error": True,
                    "request_id": request_id,
                    "conversation_id": submitted_conversation_id,
                }
            )
            st.session_state.messages_loaded_for = None
        finally:
            st.session_state.chat_processing = False


def valid_done_event(data: dict[str, Any], request_id: str, conversation_id: int) -> bool:
    """验证完成事件确实属于当前提交且已持久化。

    :param data: 后端完成事件数据。
    :param request_id: 当前提交请求标识。
    :param conversation_id: 当前提交会话编号。
    :return: 完成事件标识完整且匹配时返回真。
    """
    return (
        str(data.get("request_id") or "") == request_id
        and data.get("conversation_id") == conversation_id
        and isinstance(data.get("chat_history_id"), int)
        and isinstance(data.get("answer"), str)
    )


def render_tool_events(events: list[dict[str, Any]]) -> None:
    """渲染工具`events`。

    :param events: 函数处理所需的“`events`”数据，类型为 ``list[dict[str, Any]]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    if not events:
        return
    unique: list[dict[str, Any]] = []
    for event in events:
        append_unique_tool_event(unique, event)
    with st.expander("工具调用过程", expanded=False):
        for event in unique:
            render_tool_event(event)


def render_tool_event(event: dict[str, Any]) -> None:
    """渲染单个工具调用，正文只包含精简来源信息。

    :param event: 单个工具事件。
    :return: 无返回值；函数将状态写入页面。
    """
    details = tool_event_details(event)
    st.markdown(f"**{describe_tool_event(event)}**")
    for detail in details:
        st.write(detail)


def render_chat_history() -> None:
    """按会话浏览和管理当前账号的持久化问答记录。

    :return: 无返回值；函数直接渲染页面并更新会话状态。
    """
    page_title("对话记录", "按会话查看 SQLite 中持久化的完整问答记录。")
    if not render_auth_gate():
        return

    try:
        conversations = conversation_display_items(
            list_conversations(st.session_state.token, st.session_state.api_base_url).get("items", [])
        )
    except Exception as exc:
        show_error(exc)
        return

    if not conversations:
        st.info("暂无会话。")
        return

    by_id = {int(item["id"]): item for item in conversations}
    valid_ids = list(by_id)
    if st.session_state.history_conversation_id not in by_id:
        st.session_state.history_conversation_id = valid_ids[0]
        st.session_state.history_selector = valid_ids[0]
        st.session_state.history_loaded_for = None

    selected_id = st.selectbox(
        "选择会话",
        valid_ids,
        format_func=lambda conversation_id: (
            f"{by_id[conversation_id]['display_no']} · {by_id[conversation_id]['display_title']} · "
            f"{format_ui_datetime(by_id[conversation_id].get('updated_at'))}"
        ),
        key="history_selector",
    )
    if int(selected_id) != st.session_state.history_conversation_id:
        st.session_state.history_conversation_id = int(selected_id)
        st.session_state.history_loaded_for = None
        st.session_state.history_items = []

    if st.session_state.history_loaded_for != int(selected_id):
        try:
            page = get_conversation_messages(
                int(selected_id), st.session_state.token, st.session_state.api_base_url, limit=50
            )
            st.session_state.history_items = page.get("items", [])
            st.session_state.history_has_more = bool(page.get("has_more"))
            st.session_state.history_loaded_for = int(selected_id)
        except Exception as exc:
            show_error(exc)
            return

    if st.session_state.history_notice:
        st.success(st.session_state.history_notice)
        st.session_state.history_notice = ""
    if st.session_state.history_error:
        st.error(st.session_state.history_error)
        st.session_state.history_error = ""

    selected_conversation = by_id[int(selected_id)]
    confirm_conversation_key = f"history_confirm_delete_conversation_{selected_id}"
    st.warning(f"删除整个对话会清除其中全部问答，但不会删除关联工单：{selected_conversation['display_title']}")
    confirm_conversation = st.checkbox("确认删除整个对话", key=confirm_conversation_key)
    if st.button(
        "删除整个对话",
        key=f"history_delete_conversation_{selected_id}",
        disabled=not confirm_conversation,
    ):
        try:
            result = delete_conversation(int(selected_id), st.session_state.token, st.session_state.api_base_url)
            st.session_state.conversations = conversations
            apply_delete_result(result)
            st.session_state.history_conversation_id = int(result["active_conversation"]["id"])
            st.session_state.history_loaded_for = None
            st.session_state.history_items = []
            st.session_state.history_notice = "整个对话已删除"
            st.rerun()
        except Exception as exc:
            st.session_state.history_error = localize_ui_error(exc)
            st.rerun()

    if st.session_state.history_has_more and st.session_state.history_items:
        if st.button("加载更早记录", key=f"history_load_older_{selected_id}"):
            before_id = min(int(item["id"]) for item in st.session_state.history_items)
            try:
                page = get_conversation_messages(
                    int(selected_id), st.session_state.token, st.session_state.api_base_url,
                    limit=50, before_id=before_id,
                )
                st.session_state.history_items = page.get("items", []) + st.session_state.history_items
                st.session_state.history_has_more = bool(page.get("has_more"))
                st.rerun()
            except Exception as exc:
                show_error(exc)

    items = st.session_state.history_items
    if not items:
        st.info("该会话暂无问答记录。")
        return

    for item in items:
        history_id = int(item["id"])
        with st.chat_message("user"):
            st.markdown(str(item.get("question") or ""))
        with st.chat_message("assistant"):
            st.markdown(str(item.get("answer") or ""))
            if item.get("ticket_id"):
                st.info(f"关联工单：#{item['ticket_id']}")
            render_tool_events(item.get("tool_events") or [])
            st.caption(f"创建时间：{format_ui_datetime(item.get('created_at'))}")
            confirm_key = f"history_confirm_delete_record_{selected_id}_{history_id}"
            confirmed = st.checkbox("确认删除这一轮问答", key=confirm_key)
            if st.button(
                "删除这条记录",
                key=f"history_delete_record_{selected_id}_{history_id}",
                disabled=not confirmed or history_id in st.session_state.history_delete_claims,
            ):
                st.session_state.history_delete_claims.add(history_id)
                try:
                    delete_chat_history(history_id, st.session_state.token, st.session_state.api_base_url)
                    st.session_state.history_loaded_for = None
                    st.session_state.history_notice = "这一轮问答已删除"
                    st.session_state.conversations_loaded_for = None
                    st.rerun()
                except Exception as exc:
                    st.session_state.history_delete_claims.discard(history_id)
                    st.session_state.history_error = localize_ui_error(exc)
                    st.rerun()

    with st.expander("表格模式", expanded=False):
        st.dataframe(history_table_rows(items), width="stretch", hide_index=True)


def render_tickets() -> None:
    """渲染`tickets`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    caption = "管理员可查看并管理全部工单。" if is_admin() else "当前用户只能查看自己的工单。"
    page_title("工单列表", caption)
    if not render_auth_gate():
        return

    col_refresh, col_export = st.columns([1, 1])
    refresh = col_refresh.button("刷新工单", key="tickets_refresh", width="stretch")
    if is_admin():
        if col_export.button("导出统计", key="tickets_export", width="stretch"):
            try:
                stat = export_ticket_stat(st.session_state.token, st.session_state.api_base_url)
                st.download_button(
                    "下载统计文件",
                    data=ticket_statistics_csv(stat),
                    file_name="工单统计.csv",
                    mime="text/csv;charset=utf-8",
                    width="stretch",
                    key="tickets_download_stat",
                )
                st.dataframe(
                    [{"状态": "全部", "数量": stat.get("total", 0)}]
                    + [
                        {"状态": ticket_status_label(status), "数量": count}
                        for status, count in (stat.get("by_status") or {}).items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            except Exception as exc:
                show_error(exc)

    if refresh:
        st.cache_data.clear()

    try:
        data = list_tickets(st.session_state.token, st.session_state.api_base_url)
        items = data.get("items", [])
    except Exception as exc:
        show_error(exc)
        return

    pending_consultations = [
        item
        for item in items
        if item.get("ticket_type") == "consultation" and item.get("status") == "pending"
    ]
    open_non_leave_tickets = [
        item
        for item in items
        if item.get("ticket_type") != "leave" and item.get("status") == "open"
    ]
    if is_admin():
        st.write(f"待审批普通咨询工单：{len(pending_consultations)}")
        confirm_bulk = st.checkbox(
            "确认：只会通过普通咨询工单，不会处理请假申请。",
            key="confirm_bulk_approve_consultations",
            disabled=not pending_consultations,
        )
        if st.button(
            "一键通过普通咨询工单",
            key="bulk_approve_consultations",
            disabled=not pending_consultations or not confirm_bulk or st.session_state.bulk_approve_claimed,
            width="stretch",
        ):
            st.session_state.bulk_approve_claimed = True
            try:
                result = bulk_approve_consultations(
                    st.session_state.token, st.session_state.api_base_url
                )
                st.session_state.bulk_approve_notice = (
                    f"已通过 {result.get('updated_count', 0)} 张普通咨询工单。"
                )
                st.session_state.bulk_approve_claimed = False
                st.rerun()
            except Exception as exc:
                st.session_state.bulk_approve_claimed = False
                show_error(exc)
        st.write(f"待处理非请假工单：{len(open_non_leave_tickets)}")
        confirm_process = st.checkbox(
            "确认：本次操作不会处理请假申请。",
            key="confirm_bulk_process_open",
            disabled=not open_non_leave_tickets,
        )
        if st.button(
            "一键已处理",
            key="bulk_process_open",
            disabled=(
                not open_non_leave_tickets
                or not confirm_process
                or st.session_state.bulk_process_claimed
            ),
            width="stretch",
        ):
            st.session_state.bulk_process_claimed = True
            try:
                result = bulk_process_open_tickets(
                    st.session_state.token, st.session_state.api_base_url
                )
                st.session_state.bulk_process_notice = (
                    f"已处理 {result.get('updated_count', 0)} 张非请假工单。"
                )
                st.session_state.bulk_process_claimed = False
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.session_state.bulk_process_claimed = False
                show_error(exc)
    if st.session_state.bulk_approve_notice:
        st.success(st.session_state.bulk_approve_notice)
        st.session_state.bulk_approve_notice = ""
    if st.session_state.bulk_process_notice:
        st.success(st.session_state.bulk_process_notice)
        st.session_state.bulk_process_notice = ""
    if not items:
        st.info("暂无工单。")
        return

    st.dataframe(ticket_table_rows(items), width="stretch", hide_index=True)

    st.divider()
    st.markdown("#### 管理工单" if is_admin() else "#### 查看工单")
    selected_ticket = st.selectbox(
        "选择工单",
        items,
        format_func=lambda item: (
            f"#{item.get('id')} {item.get('creator_username') or '账号已删除'} / "
            f"{ticket_type_label(item.get('ticket_type'))} / "
            f"{status_label(str(item.get('status') or ''))}"
        ),
        key="ticket_admin_selector",
    )
    st.write(f"申请人：{selected_ticket.get('creator_username') or '账号已删除'}")
    if selected_ticket.get("ticket_type") == "leave":
        st.write(f"请假类型：{format_ui_value(selected_ticket.get('leave_type'))}")
        st.write(f"开始时间：{format_ui_datetime(selected_ticket.get('start_at'))}")
        st.write(f"结束时间：{format_ui_datetime(selected_ticket.get('end_at'))}")
        st.write(f"请假天数：{format_ui_value(selected_ticket.get('leave_days'))}")
        st.write(f"请假原因：{format_ui_value(selected_ticket.get('leave_reason'))}")
        status_options = ["approved", "rejected"]
    else:
        status_options = ["pending", "approved", "rejected", "processed", "closed"]
    if not is_admin():
        return
    current_status = str(selected_ticket.get("status") or "pending")
    next_status = st.selectbox(
        "更新状态",
        status_options,
        index=status_options.index(current_status)
        if current_status in status_options
        else 0,
        format_func=status_label,
        key=f"ticket_status_{selected_ticket['id']}",
    )
    if st.button("保存工单状态", key=f"ticket_save_{selected_ticket['id']}", width="stretch"):
        try:
            update_ticket_status(
                int(selected_ticket["id"]),
                next_status,
                st.session_state.token,
                st.session_state.api_base_url,
            )
            st.success("工单状态已更新。")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def render_leave_application() -> None:
    """渲染独立请假申请表单。

    :return: 无返回值；函数渲染并处理请假表单。
    """
    page_title("请假申请", "提交后进入待审批状态，由管理员逐条审核。")
    if not render_auth_gate():
        return
    if st.session_state.leave_notice:
        st.success(st.session_state.leave_notice)
        st.session_state.leave_notice = ""
    with st.form("leave_application_form", clear_on_submit=True):
        leave_type = st.selectbox(
            "请假类型",
            ["年假", "事假", "病假", "调休", "婚假", "产假/陪产假", "其他"],
            key="leave_type",
        )
        start_date = st.date_input("开始日期", value=date.today(), key="leave_start_date")
        start_time = st.time_input("开始时间", value=time(9, 0), key="leave_start_time")
        end_date = st.date_input("结束日期", value=date.today(), key="leave_end_date")
        end_time = st.time_input("结束时间", value=time(18, 0), key="leave_end_time")
        leave_days = st.number_input(
            "请假天数", min_value=0.0, step=0.5, key="leave_days"
        )
        reason = st.text_area("请假原因", key="leave_reason")
        submitted = st.form_submit_button(
            "提交请假申请", key="leave_submit", width="stretch"
        )
    if not submitted:
        return
    start_at = datetime.combine(start_date, start_time)
    end_at = datetime.combine(end_date, end_time)
    if end_at < start_at:
        st.error("结束时间不能早于开始时间。")
        return
    if leave_days <= 0:
        st.error("请假天数必须大于 0。")
        return
    if not reason.strip():
        st.error("请假原因不能为空。")
        return
    request_id = str(st.session_state.leave_request_id)
    if st.session_state.leave_submit_claim == request_id:
        return
    st.session_state.leave_submit_claim = request_id
    try:
        ticket = create_leave_application(
            {
                "leave_type": leave_type,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "leave_days": leave_days,
                "reason": reason,
                "request_id": request_id,
            },
            st.session_state.token,
            st.session_state.api_base_url,
        )
        st.session_state.leave_notice = f"请假申请已提交：#{ticket.get('id')}"
        st.session_state.leave_request_id = uuid4().hex
        st.session_state.leave_submit_claim = None
        st.rerun()
    except Exception as exc:
        st.session_state.leave_submit_claim = None
        show_error(exc)


def render_upload() -> None:
    """渲染上传。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("文档上传", "管理员上传文档后触发知识库入库。")
    if not render_auth_gate():
        return
    if not is_admin():
        st.error("当前角色无上传权限。")
        return

    uploaded = st.file_uploader(
        "选择 PDF、DOC 或 DOCX 文档", type=["pdf", "docx", "doc"], key="knowledge_upload_file"
    )
    if st.button(
        "上传并入库", key="knowledge_upload_submit", disabled=uploaded is None, width="stretch"
    ):
        assert uploaded is not None
        progress = st.progress(0, text="准备上传")
        tmp_path: Path | None = None
        try:
            suffix = Path(uploaded.name).suffix
            with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = Path(tmp.name)
            progress.progress(25, text="正在上传文档")
            upload_result = upload_knowledge_file(
                tmp_path,
                st.session_state.token,
                st.session_state.api_base_url,
                filename=uploaded.name,
            )
            progress.progress(55, text="上传完成，正在重建索引")
            rebuild_result = rebuild_knowledge(st.session_state.token, st.session_state.api_base_url)
            progress.progress(100, text="入库完成")
            st.success("文档已上传并入库")
            source_path = str(upload_result.get("source_path") or uploaded.name)
            rebuild_stats = rebuild_result.get("stats") if isinstance(rebuild_result, dict) else []
            indexed_files = len(rebuild_stats) if isinstance(rebuild_stats, list) else 0
            indexed_chunks = sum(
                int(item.get("chunks") or 0) for item in rebuild_stats if isinstance(item, dict)
            ) if isinstance(rebuild_stats, list) else 0
            st.write(f"上传文件：{Path(source_path).name}")
            st.write(f"本次索引：{indexed_files} 个文件，共 {indexed_chunks} 个文本块")
            if isinstance(rebuild_result, dict) and rebuild_result.get("warning"):
                st.warning("索引已重建，但向量检索暂不可用，系统将使用关键词检索。")
        except Exception as exc:
            progress.progress(100, text="入库失败")
            show_error(exc)
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    with st.expander("已入库文档", expanded=True):
        try:
            docs = list_knowledge(st.session_state.token, st.session_state.api_base_url).get("items", [])
            if docs:
                st.dataframe(knowledge_table_rows(docs), width="stretch", hide_index=True)
                selected_preview_doc = st.selectbox(
                    "选择要查看的文档",
                    docs,
                    format_func=lambda item: (
                        f"#{docs.index(item) + 1} {item.get('title') or item.get('source_path')}"
                    ),
                    key="knowledge_preview_selector",
                )
                if st.button("查看原始内容", key="knowledge_preview_open", width="stretch"):
                    preview = get_knowledge_content(
                        int(selected_preview_doc["id"]),
                        st.session_state.token,
                        st.session_state.api_base_url,
                    )
                    st.text_area(
                        f"{preview.get('title') or '文档'}的原始内容",
                        value=str(preview.get("content") or "（未提取到文字内容）"),
                        height=420,
                        disabled=True,
                        key=f"knowledge_preview_content_{selected_preview_doc['id']}",
                    )
                selected_doc = st.selectbox(
                    "选择要删除的文档",
                    docs,
                    format_func=lambda item: (
                        f"#{docs.index(item) + 1} {item.get('title') or item.get('source_path')}"
                    ),
                    key="knowledge_delete_selector",
                )
                confirm_doc_delete = st.checkbox(
                    "确认删除所选文档", key=f"knowledge_delete_confirm_{selected_doc['id']}"
                )
                if st.button(
                    "删除文档",
                    key=f"knowledge_delete_submit_{selected_doc['id']}",
                    disabled=not confirm_doc_delete,
                    width="stretch",
                ):
                    delete_knowledge_doc(int(selected_doc["id"]), st.session_state.token, st.session_state.api_base_url)
                    st.success("文档已删除，知识库索引已重建")
                    st.rerun()
            else:
                st.info("暂无入库记录。")
        except Exception as exc:
            show_error(exc)


def render_accounts() -> None:
    """渲染`accounts`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("账号管理", "管理员创建账号；用户可修改自己的密码。")
    if not render_auth_gate():
        return

    if st.session_state.account_notice:
        st.success(st.session_state.account_notice)
        st.session_state.account_notice = ""

    st.markdown("#### 修改我的密码")
    with st.form("change_password_form"):
        old_password = st.text_input("旧密码", type="password", key="account_old_password")
        new_password = st.text_input(
            "新密码", type="password", help="至少 6 位", key="account_new_password"
        )
        submitted = st.form_submit_button(
            "修改密码", key="account_change_password_submit", width="stretch"
        )
    if submitted:
        try:
            change_password(old_password, new_password, st.session_state.token, st.session_state.api_base_url)
            st.success("密码已修改，请重新登录。")
            for key in ("token", "username", "role", "tier"):
                st.session_state[key] = ""
            st.session_state.user_id = None
        except Exception as exc:
            show_error(exc)

    if not is_admin():
        return

    st.divider()
    create_user_tab, create_admin_tab, manage_tab = st.tabs(["创建用户", "添加管理员", "管理账号"])

    with create_user_tab:
        with st.form("create_user_form"):
            username = st.text_input("新账号", key="admin_new_username")
            role = st.selectbox(
                "身份",
                ["employee", "hr", "finance", "ops"],
                format_func=role_label,
                key="admin_new_role",
            )
            created = st.form_submit_button(
                "创建账号", key="admin_create_user_submit", width="stretch"
            )
        if created:
            try:
                data = create_user(username, role, st.session_state.token, st.session_state.api_base_url)
                st.success(f"账号已创建：{data['username']}，默认密码：{data['default_password']}")
            except Exception as exc:
                show_error(exc)

    with create_admin_tab:
        with st.form("create_admin_form"):
            admin_username = st.text_input("管理员账号", key="admin_new_admin_username")
            admin_created = st.form_submit_button(
                "添加管理员", key="admin_create_admin_submit", width="stretch"
            )
        if admin_created:
            try:
                data = create_user(admin_username, "admin", st.session_state.token, st.session_state.api_base_url)
                st.success(f"管理员已创建：{data['username']}，默认密码：{data['default_password']}")
            except Exception as exc:
                show_error(exc)

    try:
        users = list_users(st.session_state.token, st.session_state.api_base_url).get("items", [])
    except Exception as exc:
        show_error(exc)
        return

    with manage_tab:
        if not users:
            st.info("暂无账号。")
            return

        st.dataframe(account_table_rows(users), width="stretch", hide_index=True)

        manageable_users = [item for item in users if item.get("id") != st.session_state.get("user_id")]
        manageable_users = [item for item in manageable_users if item.get("username") != st.session_state.username]
        if not manageable_users:
            st.info("没有可管理的其他账号。")
            return

        selected_user = st.selectbox(
            "选择账号",
            manageable_users,
            format_func=lambda item: f"{item.get('username')} / {role_label(str(item.get('role') or ''))}",
            key="admin_user_selector",
        )
        confirm_delete = st.checkbox(
            "确认删除所选账号", key=f"admin_delete_confirm_{selected_user['id']}"
        )
        col_reset, col_delete = st.columns(2)
        if col_reset.button(
            "重置为默认密码", key=f"admin_reset_password_{selected_user['id']}", width="stretch"
        ):
            try:
                data = reset_user_password(int(selected_user["id"]), st.session_state.token, st.session_state.api_base_url)
                st.success(f"{selected_user['username']} 的密码已重置为：{data.get('default_password', DEFAULT_PASSWORD)}")
            except Exception as exc:
                show_error(exc)
        if col_delete.button(
            "删除账号",
            key=f"admin_delete_user_{selected_user['id']}",
            disabled=not confirm_delete,
            width="stretch",
        ):
            try:
                delete_user(int(selected_user["id"]), st.session_state.token, st.session_state.api_base_url)
                st.session_state.account_notice = f"账号已删除：{selected_user['username']}"
                st.rerun()
            except Exception as exc:
                show_error(exc)


def main() -> None:
    """执行当前模块的主流程并协调各项处理步骤。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    init_state()
    page = render_sidebar()
    if page == "登录":
        render_login()
    elif page == "对话":
        render_chat()
    elif page == "对话记录":
        render_chat_history()
    elif page == "请假申请":
        render_leave_application()
    elif page == "工单":
        render_tickets()
    elif page == "上传":
        render_upload()
    else:
        render_accounts()


def _running_in_streamlit() -> bool:
    """`running``in``streamlit`。

    :return: 返回`running``in``streamlit`得到的结果，返回类型为 ``bool``。
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        try:
            return get_script_run_ctx(suppress_warning=True) is not None
        except TypeError:
            return get_script_run_ctx() is not None
    except Exception:
        return False


def _launch_with_streamlit() -> None:
    """`launch``with``streamlit`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    app_path = str(Path(__file__).resolve())
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            app_path,
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
    )


if __name__ == "__main__":
    if _running_in_streamlit():
        main()
    else:
        _launch_with_streamlit()
