from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.frontend_api import (
    PAGE_NAMES,
    api_base_url,
    change_password,
    create_ticket,
    create_user,
    delete_knowledge_doc,
    delete_user,
    describe_tool_event,
    export_ticket_stat,
    get_me,
    list_chat_history,
    list_knowledge,
    list_tickets,
    list_users,
    login,
    rebuild_knowledge,
    resolve_page,
    reset_user_password,
    stream_chat,
    update_ticket_status,
    upload_knowledge_file,
)


st.set_page_config(page_title="Knowledge Agent", page_icon=None, layout="wide")


DEFAULT_PASSWORD = "123456"
ROLE_LABELS = {
    "admin": "管理员",
    "hr": "人事",
    "finance": "财务",
    "ops": "运维",
    "employee": "普通用户",
}
UI_ERROR_MESSAGE_MAP = {
    "invalid username or password": "账号或密码错误",
    "missing bearer token": "缺少登录令牌，请重新登录",
    "invalid bearer token": "登录状态已失效，请重新登录",
    "invalid old password": "旧密码错误",
    "invalid role": "角色无效",
    "username already exists": "账号已存在",
    "user not found": "用户不存在",
    "admin only": "仅管理员可操作",
    "cannot reset current user": "不能重置当前登录账号的密码",
    "cannot delete current user": "不能删除当前登录账号",
    "unsupported file type": "不支持的文件类型",
    "document not found": "文档不存在",
    "ticket not found": "工单不存在",
    "admin approval required": "该工单需要管理员审批",
    "unsupported ticket status": "不支持的工单状态",
    "tool not found": "工具不存在",
    "tool forbidden": "当前角色无权使用该工具",
    "unsupported export format": "不支持的导出格式",
    "missing user": "缺少登录用户信息",
    "llm returned empty content": "模型未返回有效内容",
    "too many requests": "请求过于频繁，请稍后再试",
}
STATUS_LABELS = {
    "pending": "待审批",
    "approved": "已批准",
    "rejected": "已驳回",
    "open": "待处理",
    "processing": "处理中",
    "closed": "已关闭",
}


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
        "tool_events": [],
        "last_chat": None,
        "pending_ticket_suggestion": None,
        "account_notice": "",
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
    text = str(error).strip()
    lowered = text.lower()
    for source, target in UI_ERROR_MESSAGE_MAP.items():
        if source in lowered:
            return text.replace(source, target)
    if any(keyword in lowered for keyword in ("field required", "value error", "input should", "validation error")):
        return "请求参数不合法"
    if any(
        keyword in lowered
        for keyword in (
            "httpconnectionpool",
            "connection refused",
            "failed to establish a new connection",
            "connection aborted",
        )
    ):
        return "无法连接后端服务，请确认后端已启动"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return text
    return f"操作失败：{text}"


def show_error(error: Exception) -> None:
    """显示错误信息。

    :param error: 函数处理所需的“错误信息”数据，类型为 ``Exception``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    st.error(localize_ui_error(error))


def role_label(role: str) -> str:
    """获取角色`label`。

    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回获取角色`label`得到的结果，返回类型为 ``str``。
    """
    return ROLE_LABELS.get(role, role or "未知")


def status_label(status: str) -> str:
    """获取状态`label`。

    :param status: 函数处理所需的“获取状态”数据，类型为 ``str``。
    :return: 返回获取状态`label`得到的结果，返回类型为 ``str``。
    """
    return STATUS_LABELS.get(status, status or "未知")


def load_history_into_chat() -> None:
    """加载历史记录`into`处理对话。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    if st.session_state.messages_loaded_for == st.session_state.user_id:
        return
    try:
        items = list_chat_history(st.session_state.token, st.session_state.api_base_url).get("items", [])
    except Exception as exc:
        show_error(exc)
        st.session_state.messages_loaded_for = st.session_state.user_id
        return

    messages: list[dict[str, str]] = []
    for item in reversed(items):
        question = str(item.get("question") or "")
        answer = str(item.get("answer") or "")
        if question:
            messages.append({"role": "user", "content": question})
        if answer:
            messages.append({"role": "assistant", "content": answer})
    st.session_state.messages = messages
    st.session_state.messages_loaded_for = st.session_state.user_id


def render_ticket_suggestion() -> None:
    """渲染工单`suggestion`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    suggestion = st.session_state.get("pending_ticket_suggestion")
    if not suggestion:
        return
    st.info("系统建议可创建咨询工单，是否提交给管理员审批？")
    col_create, col_clear = st.columns(2)
    if col_create.button("创建工单", width="stretch"):
        try:
            ticket = create_ticket(
                str(suggestion.get("title") or "咨询工单"),
                str(suggestion.get("content") or ""),
                str(suggestion.get("answer") or ""),
                st.session_state.token,
                st.session_state.api_base_url,
            )
            st.session_state.pending_ticket_suggestion = None
            st.success(f"工单已提交审批：#{ticket.get('id')}")
        except Exception as exc:
            show_error(exc)
    if col_clear.button("暂不创建", width="stretch"):
        st.session_state.pending_ticket_suggestion = None
        st.rerun()


def render_sidebar() -> str:
    """渲染侧边栏。

    :return: 返回渲染侧边栏得到的结果，返回类型为 ``str``。
    """
    with st.sidebar:
        st.subheader("服务")
        st.session_state.api_base_url = st.text_input("接口地址", value=st.session_state.api_base_url)

        if is_logged_in():
            st.divider()
            st.write(f"用户：{st.session_state.username}")
            st.write(f"角色：{role_label(st.session_state.role)}")
            st.success("已登录")
            if st.button("退出登录", width="stretch"):
                for key in ("token", "username", "role", "tier"):
                    st.session_state[key] = ""
                st.session_state.user_id = None
                st.session_state.messages = []
                st.session_state.messages_loaded_for = None
                st.session_state.tool_events = []
                st.session_state.last_chat = None
                st.session_state.pending_ticket_suggestion = None
                st.session_state.account_notice = ""
                st.rerun()

        pages = PAGE_NAMES if not is_logged_in() else [page for page in PAGE_NAMES if page != "登录"]
        selected_page = st.radio("页面", pages, horizontal=False, label_visibility="collapsed")
        query_page = st.query_params.get("page")
        page = resolve_page(selected_page, query_page)
        if is_logged_in() and page == "登录":
            return pages[0]
        return page


def render_login() -> None:
    """渲染执行登录。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("Knowledge Agent", "输入账号密码后进入问答与工单演示。")
    if is_logged_in():
        st.success(f"已登录：{st.session_state.username} / {role_label(st.session_state.role)}")
        st.info("请从左侧进入对话、工单、上传或账号管理。")
        return

    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.form("login_form"):
            username = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", width="stretch")

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

    load_history_into_chat()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    render_ticket_suggestion()

    question = st.chat_input("请输入问题")
    if not question:
        if st.session_state.tool_events:
            render_tool_events(st.session_state.tool_events)
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    st.session_state.tool_events = []
    final_data: dict[str, Any] | None = None
    tool_placeholder = st.container()

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        try:
            for event in stream_chat(question, st.session_state.token, st.session_state.api_base_url):
                if event["event"] == "tool" and isinstance(event["data"], dict):
                    st.session_state.tool_events.append(event["data"])
                    with tool_placeholder:
                        render_tool_events(st.session_state.tool_events)
                elif event["event"] in {"token", "delta"}:
                    answer_placeholder.markdown(str(event["data"]))
                elif event["event"] == "done" and isinstance(event["data"], dict):
                    final_data = event["data"]

            answer = str((final_data or {}).get("answer") or "接口未返回答复。")
            typed = ""
            for char in answer:
                typed += char
                answer_placeholder.markdown(typed)
                time.sleep(0.01)

            ticket_id = (final_data or {}).get("ticket_id")
            if ticket_id:
                st.info(f"关联工单：#{ticket_id}")
            if ticket_id:
                st.session_state.pending_ticket_suggestion = None
            else:
                suggestion = (final_data or {}).get("ticket_suggestion")
                st.session_state.pending_ticket_suggestion = suggestion if suggestion else None
            st.session_state.last_chat = final_data
            st.session_state.messages.append({"role": "assistant", "content": answer})
            render_ticket_suggestion()
        except Exception as exc:
            show_error(exc)


def render_tool_events(events: list[dict[str, Any]]) -> None:
    """渲染工具`events`。

    :param events: 函数处理所需的“`events`”数据，类型为 ``list[dict[str, Any]]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    if not events:
        return
    st.markdown("#### 工具调用过程")
    for event in events:
        st.status(describe_tool_event(event), state="complete", expanded=False)


def render_chat_history() -> None:
    """渲染处理对话历史记录。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    page_title("对话记录", "查看当前账号以前的问答记录。")
    if not render_auth_gate():
        return

    try:
        items = list_chat_history(st.session_state.token, st.session_state.api_base_url).get("items", [])
    except Exception as exc:
        show_error(exc)
        return

    if not items:
        st.info("暂无对话记录。")
        return

    rows = [
        {
            "编号": item.get("id"),
            "问题": item.get("question"),
            "答复": item.get("answer"),
            "关联工单": item.get("ticket_id") or "",
            "创建时间": item.get("created_at"),
        }
        for item in items
    ]
    st.dataframe(rows, width="stretch", hide_index=True)

    selected = st.selectbox(
        "查看详情",
        items,
        format_func=lambda item: f"#{item.get('id')} {item.get('question')}",
    )
    with st.chat_message("user"):
        st.markdown(str(selected.get("question") or ""))
    with st.chat_message("assistant"):
        st.markdown(str(selected.get("answer") or ""))
        if selected.get("ticket_id"):
            st.info(f"关联工单：#{selected['ticket_id']}")
    render_tool_events(selected.get("tool_events") or [])


def render_tickets() -> None:
    """渲染`tickets`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    caption = "管理员可查看并管理全部工单。" if is_admin() else "当前用户只能查看自己的咨询工单。"
    page_title("工单列表", caption)
    if not render_auth_gate():
        return

    col_refresh, col_export = st.columns([1, 1])
    refresh = col_refresh.button("刷新工单", width="stretch")
    if is_admin():
        if col_export.button("导出统计", width="stretch"):
            try:
                stat = export_ticket_stat(st.session_state.token, st.session_state.api_base_url)
                st.download_button(
                    "下载统计文件",
                    data=json.dumps(stat, ensure_ascii=False, indent=2),
                    file_name="ticket_stat.json",
                    mime="application/json",
                    width="stretch",
                )
                st.json(stat)
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

    if not items:
        st.info("暂无工单。")
        return

    rows = []
    for item in items:
        row = {
            "编号": item.get("id"),
            "标题": item.get("title"),
            "状态": status_label(str(item.get("status") or "")),
            "问题": item.get("content"),
            "答复": item.get("answer"),
            "创建时间": item.get("created_at"),
        }
        if is_admin():
            row["创建人编号"] = item.get("creator_id")
        rows.append(row)
    st.dataframe(rows, width="stretch", hide_index=True)

    if not is_admin():
        return

    st.divider()
    st.markdown("#### 管理工单")
    selected_ticket = st.selectbox(
        "选择工单",
        items,
        format_func=lambda item: f"#{item.get('id')} {item.get('title')} / {status_label(str(item.get('status') or ''))}",
    )
    status_options = ["pending", "approved", "rejected", "closed"]
    current_status = str(selected_ticket.get("status") or "pending")
    next_status = st.selectbox(
        "更新状态",
        status_options,
        index=status_options.index(current_status)
        if current_status in status_options
        else 0,
        format_func=status_label,
    )
    if st.button("保存工单状态", width="stretch"):
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

    uploaded = st.file_uploader("选择 PDF 或 Word 文档", type=["pdf", "docx", "doc"])
    if st.button("上传并入库", disabled=uploaded is None, width="stretch"):
        assert uploaded is not None
        progress = st.progress(0, text="准备上传")
        tmp_path: Path | None = None
        try:
            suffix = Path(uploaded.name).suffix
            with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = Path(tmp.name)
            progress.progress(25, text="正在上传文档")
            upload_result = upload_knowledge_file(tmp_path, st.session_state.token, st.session_state.api_base_url)
            progress.progress(55, text="上传完成，正在重建索引")
            rebuild_result = rebuild_knowledge(st.session_state.token, st.session_state.api_base_url)
            progress.progress(100, text="入库完成")
            st.success("文档已上传并入库")
            st.json({"upload": upload_result, "rebuild": rebuild_result})
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
                st.dataframe(docs, width="stretch", hide_index=True)
                selected_doc = st.selectbox(
                    "选择要删除的文档",
                    docs,
                    format_func=lambda item: f"#{item.get('id')} {item.get('title') or item.get('source_path')}",
                )
                confirm_doc_delete = st.checkbox("确认删除所选文档")
                if st.button("删除文档", disabled=not confirm_doc_delete, width="stretch"):
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
        old_password = st.text_input("旧密码", type="password")
        new_password = st.text_input("新密码", type="password", help="至少 6 位")
        submitted = st.form_submit_button("修改密码", width="stretch")
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
            username = st.text_input("新账号")
            role = st.selectbox(
                "身份",
                ["employee", "hr", "finance", "ops"],
                format_func=role_label,
            )
            created = st.form_submit_button("创建账号", width="stretch")
        if created:
            try:
                data = create_user(username, role, st.session_state.token, st.session_state.api_base_url)
                st.success(f"账号已创建：{data['username']}，默认密码：{data['default_password']}")
            except Exception as exc:
                show_error(exc)

    with create_admin_tab:
        with st.form("create_admin_form"):
            admin_username = st.text_input("管理员账号")
            admin_created = st.form_submit_button("添加管理员", width="stretch")
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

        rows = [
            {
                "编号": item.get("id"),
                "账号": item.get("username"),
                "身份": role_label(str(item.get("role") or "")),
                "创建时间": item.get("created_at"),
            }
            for item in users
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

        manageable_users = [item for item in users if item.get("id") != st.session_state.get("user_id")]
        manageable_users = [item for item in manageable_users if item.get("username") != st.session_state.username]
        if not manageable_users:
            st.info("没有可管理的其他账号。")
            return

        selected_user = st.selectbox(
            "选择账号",
            manageable_users,
            format_func=lambda item: f"{item.get('username')} / {role_label(str(item.get('role') or ''))}",
        )
        confirm_delete = st.checkbox("确认删除所选账号")
        col_reset, col_delete = st.columns(2)
        if col_reset.button("重置为默认密码", width="stretch"):
            try:
                data = reset_user_password(int(selected_user["id"]), st.session_state.token, st.session_state.api_base_url)
                st.success(f"{selected_user['username']} 的密码已重置为：{data.get('default_password', DEFAULT_PASSWORD)}")
            except Exception as exc:
                show_error(exc)
        if col_delete.button("删除账号", disabled=not confirm_delete, width="stretch"):
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
