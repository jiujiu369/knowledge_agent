from __future__ import annotations

import csv
import io
import json
import os
import re
import hashlib
from collections.abc import Iterable, Iterator
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
PAGE_NAMES = ["登录", "对话", "对话记录", "请假申请", "工单", "上传", "账号"]
GENERIC_ERROR_MESSAGE = "操作失败，请稍后重试；详细原因已记录到服务日志。"
ROLE_LABELS = {
    "admin": "管理员",
    "employee": "普通员工",
    "hr": "人事",
    "finance": "财务",
    "ops": "运维",
}
TICKET_STATUS_LABELS = {
    "pending": "待审批",
    "approved": "已批准",
    "rejected": "已驳回",
    "open": "待处理",
    "processing": "处理中",
    "processed": "已处理",
    "closed": "已关闭",
}
TICKET_TYPE_LABELS = {
    "consultation": "普通咨询",
    "leave": "请假申请",
}
HTTP_ERROR_MESSAGE_MAP = {
    401: "登录状态已失效，请重新登录",
    403: "当前账号没有执行此操作的权限",
    404: "请求的数据不存在或无权访问",
    409: "请求已处理，请勿重复提交",
    422: "提交内容格式不正确",
    429: "操作过于频繁，请稍后重试",
    500: "服务处理失败，请稍后重试",
}
ERROR_MESSAGE_MAP = {
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
    "document source not found": "文档源文件不存在",
    "document conversion failed": "旧版 Word 文档转换失败",
    "ticket not found": "工单不存在",
    "conversation not found": "会话不存在或无权访问",
    "chat history not found": "对话记录不存在或无权访问",
    "admin approval required": "该工单需要管理员审批",
    "unsupported ticket status": "不支持的工单状态",
    "unsupported ticket type": "不支持的工单类型",
    "unsupported leave review transition": "该请假申请已处理，不能重复审核",
    "invalid leave application": "请假申请内容不正确",
    "request already exists": "请求已处理，请勿重复提交",
    "permission denied": "当前账号没有执行此操作的权限",
    "unauthorized": "登录状态已失效，请重新登录",
    "forbidden": "当前账号没有执行此操作的权限",
    "tool not found": "工具不存在",
    "tool forbidden": "当前角色无权使用该工具",
    "unsupported export format": "不支持的导出格式",
    "missing user": "缺少登录用户信息",
    "llm returned empty content": "模型未返回有效内容",
    "interface did not return a valid completion event": "接口未返回有效完成事件",
    "接口未返回有效完成事件": "接口未返回有效完成事件",
    "connection refused": "无法连接后端服务，请确认后端已启动",
    "timeout": "请求超时，请稍后重试",
    "timed out": "请求超时，请稍后重试",
    "rate limit exceeded": "操作过于频繁，请稍后重试",
    "too many requests": "操作过于频繁，请稍后重试",
    "validation error": "提交内容格式不正确",
    "field required": "请求参数不合法",
    "local bge model not found": "本地 BGE 模型未找到",
    "local vlm model not found or incomplete": "本地 VLM 模型未找到或不完整",
    "local reranker model not found": "本地重排模型未找到",
    "missing agnes_api_key or ark_api_key environment variable": "未配置模型服务密钥",
    "bge embedding dimension must be": "BGE 向量维度不符合要求",
    "embedding output must be": "向量模型输出格式不符合要求",
    "document parsing failed": "文档解析失败",
    "ocr failed": "OCR 识别失败",
    "model loading failed": "模型加载失败",
    "input cannot be blank": "输入内容不能为空",
    "input too long": "输入内容过长",
    "input contains too many invalid characters": "输入内容包含过多无效字符",
    "end_at cannot be earlier than start_at": "结束时间不能早于开始时间",
}

KNOWLEDGE_COLUMN_LABELS = {
    "id": "编号",
    "source_path": "文件路径",
    "title": "文件名",
    "checksum": "校验值",
    "chunk_count": "文本块数",
    "created_at": "创建时间",
    "updated_at": "更新时间",
}

TICKET_COLUMN_LABELS = {
    "id": "编号",
    "creator_username": "申请人",
    "title": "标题",
    "ticket_type": "类型",
    "status": "状态",
    "content": "问题",
    "answer": "答复",
    "created_at": "创建时间",
}


def role_label(role: str | None) -> str:
    """将内部角色值转换为中文展示文本。

    :param role: 内部角色值。
    :return: 中文角色名称。
    """
    return ROLE_LABELS.get(str(role or ""), "未知角色")


def ticket_status_label(status: str | None) -> str:
    """将内部工单状态转换为中文展示文本。

    :param status: 内部工单状态。
    :return: 中文状态名称。
    """
    return TICKET_STATUS_LABELS.get(str(status or ""), "未知状态")


def ticket_type_label(ticket_type: str | None) -> str:
    """将内部工单类型转换为中文展示文本。

    :param ticket_type: 内部工单类型。
    :return: 中文类型名称。
    """
    return TICKET_TYPE_LABELS.get(str(ticket_type or ""), "未知类型")


def format_ui_datetime(value: Any) -> str:
    """将日期时间转换为适合界面展示的分钟格式。

    :param value: 日期时间值。
    :return: 中文界面使用的时间文本。
    """
    if value is None or value == "":
        return "—"
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else str(value)


def format_ui_value(value: Any) -> Any:
    """转换通用界面值，避免直接展示布尔值和空值。

    :param value: 原始字段值。
    :return: 安全的界面展示值。
    """
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None or value == "":
        return "—"
    return value


def display_chat_answer(answer: Any, is_error: bool = False) -> str:
    """仅转换后端错误答复，正常模型内容保持原样。

    :param answer: 后端返回的答复。
    :param is_error: 是否为错误答复。
    :return: 可直接展示的答复文本。
    """
    text = str(answer or "")
    return localize_error_message(text) if is_error else text


def api_base_url() -> str:
    """API基础`url`。

    :return: 返回API基础`url`得到的结果，返回类型为 ``str``。
    """
    return os.getenv("KNOWLEDGE_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def auth_headers(token: str) -> dict[str, str]:
    """认证请求头。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :return: 返回认证请求头得到的结果，返回类型为 ``dict[str, str]``。
    """
    return {"Authorization": f"Bearer {token}"}


def resolve_page(selected_page: str, query_page: str | None) -> str:
    """解析并确定页面。

    :param selected_page: 函数处理所需的“`selected`页面”数据，类型为 ``str``。
    :param query_page: 函数处理所需的“查询页面”数据，类型为 ``str | None``。
    :return: 返回解析并确定页面得到的结果，返回类型为 ``str``。
    """
    if query_page in PAGE_NAMES:
        return str(query_page)
    if selected_page in PAGE_NAMES:
        return selected_page
    return PAGE_NAMES[0]


def parse_sse_events(lines: Iterable[str | bytes]) -> Iterator[dict[str, Any]]:
    """解析`sse``events`。

    :param lines: 函数处理所需的“`lines`”数据，类型为 ``Iterable[str | bytes]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    event_name = "message"
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
        line = line.rstrip("\r\n")

        if not line:
            if data_lines:
                payload = "\n".join(data_lines)
                try:
                    data: Any = json.loads(payload)
                except json.JSONDecodeError:
                    data = payload
                yield {"event": event_name, "data": data}
            event_name = "message"
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())

    if data_lines:
        payload = "\n".join(data_lines)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = payload
        yield {"event": event_name, "data": data}


def describe_tool_event(data: dict[str, Any]) -> str:
    """生成说明工具事件。

    :param data: 函数处理所需的“数据”数据，类型为 ``dict[str, Any]``。
    :return: 返回生成说明工具事件得到的结果，返回类型为 ``str``。
    """
    tool = str(data.get("tool") or "")
    if tool == "identity_check":
        return "已确认当前登录身份"
    if tool == "doc_retrieve":
        return f"正在检索知识库，命中 {int(data.get('count') or 0)} 条片段"
    if tool == "match_similar_ticket":
        return f"正在匹配历史工单，找到 {int(data.get('count') or 0)} 条相似记录"
    if tool == "llm_decision":
        suffix = "需要创建工单" if data.get("needs_ticket") else "无需创建工单"
        return f"正在生成答复，并判断{suffix}"
    if tool == "create_consult_ticket":
        return f"已创建咨询工单 #{data.get('ticket_id')}"
    return f"正在执行工具：{tool or '未知工具'}"


def append_unique_tool_event(events: list[dict[str, Any]], event: dict[str, Any]) -> bool:
    """按后端调用标识将工具事件追加到当前助手消息。

    :param events: 当前助手消息已有的工具事件。
    :param event: 新收到的工具事件。
    :return: 实际追加时返回真，重复事件返回假。
    """
    event_id = str(event.get("event_id") or "")
    if event_id and any(str(item.get("event_id") or "") == event_id for item in events):
        return False
    events.append(dict(event))
    return True


def tool_event_details(data: dict[str, Any]) -> list[str]:
    """生成工具状态展开区域的精简详情。

    :param data: 工具事件数据。
    :return: 返回适合在状态框中展示的详情行。
    """
    tool = str(data.get("tool") or "")
    hits = data.get("hits") if isinstance(data.get("hits"), list) else []
    if tool == "doc_retrieve":
        if not hits:
            return ["未检索到相关知识片段"]
        grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            title = str(hit.get("title") or hit.get("source_path") or "未知来源")
            grouped.setdefault(title, []).append(hit)
        details: list[str] = []
        for title, items in grouped.items():
            extras: list[str] = []
            pages = sorted({int(item["page"]) for item in items if item.get("page") is not None})
            chunks = sorted({int(item["chunk"]) for item in items if item.get("chunk") is not None})
            if pages:
                extras.append("第 " + "、".join(str(page) for page in pages) + " 页")
            if chunks:
                extras.append("分块 " + "、".join(str(chunk) for chunk in chunks))
            suffix = "，" + "，".join(extras) if extras else ""
            details.append(f"{title}（{len(items)} 个片段{suffix}）")
        return details or ["未检索到相关知识片段"]
    if tool == "match_similar_ticket":
        if not hits:
            return ["未找到相似历史工单"]
        return [f"工单 #{hit.get('ticket_id')}：{hit.get('title') or '未命名工单'}" for hit in hits if isinstance(hit, dict)]
    return []


def ticket_suggestion_action_keys(conversation_id: str, suggestion_id: str) -> dict[str, str]:
    """生成当前会话和建议唯一的工单按钮 key。

    :param conversation_id: 当前会话稳定标识。
    :param suggestion_id: 当前建议稳定标识。
    :return: 返回创建与拒绝按钮的显式 key。
    """
    stable = re.sub(r"[^0-9A-Za-z_.-]+", "_", f"{conversation_id}_{suggestion_id}")
    return {"create": f"ticket_create_{stable}", "dismiss": f"ticket_dismiss_{stable}"}


def ticket_suggestion_id(suggestion: dict[str, Any]) -> str:
    """根据建议业务内容生成跨 rerun 稳定的短标识。

    :param suggestion: 待处理的工单建议。
    :return: 返回建议内容的稳定短摘要。
    """
    payload = json.dumps(suggestion, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def claim_ticket_suggestion_render(rendered: set[str], suggestion_key: str) -> bool:
    """保证同一次脚本运行只生成一组相同建议按钮。

    :param rendered: 本次运行已经渲染的建议集合。
    :param suggestion_key: 当前建议的稳定标识。
    :return: 首次认领返回真，重复认领返回假。
    """
    if suggestion_key in rendered:
        return False
    rendered.add(suggestion_key)
    return True


def claim_ticket_action(claimed: set[str], suggestion_key: str) -> bool:
    """认领一次工单创建动作，防止快速重复提交。

    :param claimed: 当前会话已经认领的动作集合。
    :param suggestion_key: 当前建议的稳定标识。
    :return: 首次认领返回真，重复认领返回假。
    """
    if suggestion_key in claimed:
        return False
    claimed.add(suggestion_key)
    return True


def stringify_error_message(message: Any) -> str:
    """转换为字符串错误信息消息。

    :param message: 用户提交或系统生成的消息文本，类型为 ``Any``。
    :return: 返回转换为字符串错误信息消息得到的结果，返回类型为 ``str``。
    """
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        if isinstance(message.get("message"), str):
            return message["message"]
        if isinstance(message.get("msg"), str):
            return message["msg"]
        return "请求参数不合法"
    if isinstance(message, (list, tuple)):
        parts: list[str] = []
        for item in message:
            if isinstance(item, dict):
                if isinstance(item.get("msg"), str):
                    parts.append(item["msg"])
                elif isinstance(item.get("message"), str):
                    parts.append(item["message"])
            else:
                parts.append(str(item))
        return "；".join(part for part in parts if part) or "请求参数不合法"
    return str(message)


def localize_error_message(message: Any) -> str:
    """本地化错误信息消息。

    :param message: 用户提交或系统生成的消息文本，类型为 ``Any``。
    :return: 返回本地化错误信息消息得到的结果，返回类型为 ``str``。
    """
    text = stringify_error_message(message).strip()
    if not text:
        return GENERIC_ERROR_MESSAGE
    lowered = text.lower()
    for source, target in ERROR_MESSAGE_MAP.items():
        if lowered == source:
            return target
        if source in lowered:
            return target
    if any(keyword in lowered for keyword in ("field required", "value error", "input should", "validation error")):
        return "请求参数不合法"
    if any(keyword in lowered for keyword in ("httpconnectionpool", "connection refused", "failed to establish a new connection", "connection aborted")):
        return "无法连接后端服务，请确认后端已启动"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return text
    return GENERIC_ERROR_MESSAGE


def localize_http_error(status_code: int, message: Any) -> str:
    """优先转换明确业务错误，否则按 HTTP 状态提供中文提示。

    :param status_code: HTTP 状态码。
    :param message: 后端错误消息。
    :return: 中文错误提示。
    """
    localized = localize_error_message(message)
    if localized != GENERIC_ERROR_MESSAGE:
        return localized
    return HTTP_ERROR_MESSAGE_MAP.get(status_code, GENERIC_ERROR_MESSAGE)


def response_data(response: requests.Response) -> Any:
    """响应数据。

    :param response: 需要解析或转换的 HTTP 响应对象，类型为 ``requests.Response``。
    :return: 返回响应数据得到的结果，返回类型为 ``Any``。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"接口返回非 JSON：HTTP {response.status_code}") from exc

    if response.status_code >= 400 or payload.get("code") != "ok":
        message = payload.get("message") if isinstance(payload, dict) else response.text
        raise RuntimeError(f"接口调用失败：HTTP {response.status_code}，{localize_http_error(response.status_code, message)}")
    return payload.get("data")


def login(username: str, password: str, base_url: str | None = None) -> dict[str, Any]:
    """执行登录。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param password: 函数处理所需的“密码”数据，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :param conversation_id: 当前会话编号。
    :param request_id: 本轮请求的幂等标识。
    :return: 返回执行登录得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    return response_data(response)


def get_me(token: str, base_url: str | None = None) -> dict[str, Any]:
    """获取`me`。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :param conversation_id: 需要读取的会话编号。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回获取`me`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/auth/me",
        headers=auth_headers(token),
        timeout=15,
    )
    return response_data(response)


def list_users(token: str, base_url: str | None = None) -> dict[str, Any]:
    """查询列表`users`。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回查询列表`users`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/auth/admin/users",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_user(username: str, role: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    """创建用户。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回创建用户得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/admin/users",
        json={"username": username, "role": role},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def reset_user_password(user_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """重置用户密码。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回重置用户密码得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/admin/users/{user_id}/reset-password",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def delete_user(user_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """删除用户。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回删除用户得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.delete(
        f"{base_url or api_base_url()}/api/auth/admin/users/{user_id}",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def change_password(old_password: str, new_password: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    """修改密码。

    :param old_password: 函数处理所需的“`old`密码”数据，类型为 ``str``。
    :param new_password: 函数处理所需的“`new`密码”数据，类型为 ``str``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回修改密码得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/change-password",
        json={"old_password": old_password, "new_password": new_password},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def stream_chat(
    message: str,
    token: str,
    base_url: str | None = None,
    conversation_id: int | None = None,
    request_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """流式处理处理对话。

    :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :param conversation_id: 当前会话编号。
    :param request_id: 本轮请求的幂等标识。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    with requests.post(
        f"{base_url or api_base_url()}/api/chat/stream",
        json={"message": message, "conversation_id": conversation_id, "request_id": request_id},
        headers=auth_headers(token),
        stream=True,
        timeout=(10, 180),
    ) as response:
        if response.status_code >= 400:
            try:
                payload = response.json()
                message_text = payload.get("message") if isinstance(payload, dict) else response.text
            except ValueError:
                message_text = response.text
            raise RuntimeError(
                f"接口调用失败：HTTP {response.status_code}，"
                f"{localize_http_error(response.status_code, message_text)}"
            )
        yield from parse_sse_events(response.iter_lines(decode_unicode=True))


def list_chat_history(
    token: str, base_url: str | None = None, conversation_id: int | None = None,
    limit: int = 50, before_id: int | None = None,
) -> dict[str, Any]:
    """查询列表处理对话历史记录。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :param conversation_id: 需要读取的会话编号。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回查询列表处理对话历史记录得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/chat/history",
        headers=auth_headers(token),
        params={
            key: value for key, value in {
                "conversation_id": conversation_id, "limit": limit, "before_id": before_id
            }.items() if value is not None
        },
        timeout=20,
    )
    return response_data(response)


def list_conversations(token: str, base_url: str | None = None) -> dict[str, Any]:
    """列出当前登录用户自己的会话。

    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回会话列表响应数据。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/chat/conversations",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_conversation(
    token: str,
    base_url: str | None = None,
    title: str = "新对话",
    request_id: str | None = None,
) -> dict[str, Any]:
    """创建一个空白会话。

    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :param title: 初始会话标题。
    :param request_id: 创建会话的幂等标识。
    :return: 返回新建会话数据。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/chat/conversations",
        json={"title": title, "request_id": request_id},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def get_conversation_messages(
    conversation_id: int, token: str, base_url: str | None = None,
    limit: int = 50, before_id: int | None = None,
) -> dict[str, Any]:
    """读取当前用户指定会话中的消息。

    :param conversation_id: 会话编号。
    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :param limit: 单页最多返回的记录数。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回会话消息响应数据。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/chat/conversations/{conversation_id}/messages",
        headers=auth_headers(token),
        params={key: value for key, value in {"limit": limit, "before_id": before_id}.items() if value is not None},
        timeout=20,
    )
    return response_data(response)


def delete_conversation(conversation_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """删除当前登录用户自己的会话。

    :param conversation_id: 待删除的会话编号。
    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回被删除的会话数据。
    """
    response = requests.delete(
        f"{base_url or api_base_url()}/api/chat/conversations/{conversation_id}",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def delete_chat_history(history_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """删除当前用户自己的一整轮持久化问答。

    :param history_id: 待删除的聊天记录编号。
    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回删除接口响应数据。
    """
    response = requests.delete(
        f"{base_url or api_base_url()}/api/chat/history/{history_id}",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def list_tickets(token: str, base_url: str | None = None) -> dict[str, Any]:
    """查询列表`tickets`。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回查询列表`tickets`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/tickets",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_ticket(title: str, content: str, answer: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    """创建工单。

    :param title: 函数处理所需的“`title`”数据，类型为 ``str``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回创建工单得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/tickets",
        json={"title": title, "content": content, "answer": answer},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def update_ticket_status(ticket_id: int, status: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    """更新工单获取状态。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param status: 函数处理所需的“获取状态”数据，类型为 ``str``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回更新工单获取状态得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.patch(
        f"{base_url or api_base_url()}/api/tickets/{ticket_id}",
        json={"status": status},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def export_ticket_stat(token: str, base_url: str | None = None) -> dict[str, Any]:
    """导出工单统计数据。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回导出工单统计数据得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/tools/export_ticket_stat",
        json={},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def list_knowledge(token: str, base_url: str | None = None) -> dict[str, Any]:
    """查询列表知识库。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回查询列表知识库得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/knowledge",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_leave_application(
    payload: dict[str, Any], token: str, base_url: str | None = None
) -> dict[str, Any]:
    """提交结构化请假申请。

    :param payload: 请假类型、时间、天数、原因和请求标识。
    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回创建的请假工单。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/tickets/leave",
        json=payload,
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def bulk_approve_consultations(token: str, base_url: str | None = None) -> dict[str, Any]:
    """批准全部待审批普通咨询工单。

    :param token: 管理员登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回批量审核统计。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/tickets/bulk-approve-consultations",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def bulk_process_open_tickets(token: str, base_url: str | None = None) -> dict[str, Any]:
    """将全部待处理的非请假工单批量更新为已处理。

    :param token: 管理员登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回批量处理统计。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/tickets/bulk-process-open",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def knowledge_table_rows(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将知识库记录转换为使用中文表头的表格数据。

    :param docs: 后端返回的知识文档列表。
    :return: 返回使用中文列名的表格行。
    """
    rows: list[dict[str, Any]] = []
    for doc in docs:
        row: dict[str, Any] = {}
        for field, label in KNOWLEDGE_COLUMN_LABELS.items():
            value = doc.get(field)
            row[label] = format_ui_datetime(value) if field.endswith("_at") else format_ui_value(value)
        rows.append(row)
    return rows


def ticket_table_rows(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将工单记录转换为中文表头和中文展示值。

    :param tickets: 后端工单记录。
    :return: 中文工单表格行。
    """
    rows: list[dict[str, Any]] = []
    for ticket in tickets:
        row: dict[str, Any] = {}
        for field, label in TICKET_COLUMN_LABELS.items():
            value = ticket.get(field)
            if field == "creator_username" and not value:
                value = "账号已删除"
            elif field == "ticket_type":
                value = ticket_type_label(value)
            elif field == "status":
                value = ticket_status_label(value)
            elif field.endswith("_at"):
                value = format_ui_datetime(value)
            else:
                value = format_ui_value(value)
            row[label] = value
        rows.append(row)
    return rows


def history_table_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将对话记录转换为中文表头和安全展示值。

    :param items: 后端对话记录。
    :return: 中文对话表格行。
    """
    return [
        {
            "编号": format_ui_value(item.get("id")),
            "问题": format_ui_value(item.get("question")),
            "答复": format_ui_value(item.get("answer")),
            "关联工单": format_ui_value(item.get("ticket_id")),
            "创建时间": format_ui_datetime(item.get("created_at")),
        }
        for item in items
    ]


def account_table_rows(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将账号记录转换为中文表头和中文角色。

    :param users: 后端账号记录。
    :return: 中文账号表格行。
    """
    return [
        {
            "编号": format_ui_value(item.get("id")),
            "账号": format_ui_value(item.get("username")),
            "身份": role_label(item.get("role")),
            "创建时间": format_ui_datetime(item.get("created_at")),
        }
        for item in users
    ]


def ticket_statistics_csv(statistics: dict[str, Any]) -> bytes:
    """生成带 UTF-8 BOM 的中文工单统计 CSV。

    :param statistics: 后端工单统计结果。
    :return: 可供 Windows Excel 打开的 CSV 字节。
    """
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["状态", "数量"])
    writer.writerow(["全部", int(statistics.get("total") or 0)])
    by_status = statistics.get("by_status")
    if isinstance(by_status, dict):
        for status, count in by_status.items():
            writer.writerow([ticket_status_label(str(status)), int(count or 0)])
    return output.getvalue().encode("utf-8-sig")


def get_knowledge_content(doc_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """读取已入库文档的原始正文。

    :param doc_id: 文档编号。
    :param token: 当前登录令牌。
    :param base_url: 后端基础地址。
    :return: 返回文档正文响应数据。
    """
    response = requests.get(
        f"{base_url or api_base_url()}/api/knowledge/{doc_id}/content",
        headers=auth_headers(token),
        timeout=120,
    )
    return response_data(response)


def rebuild_knowledge(token: str, base_url: str | None = None) -> dict[str, Any]:
    """重建知识库。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回重建知识库得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.post(
        f"{base_url or api_base_url()}/api/knowledge/rebuild",
        headers=auth_headers(token),
        timeout=300,
    )
    return response_data(response)


def upload_knowledge_file(
    file_path: Path,
    token: str,
    base_url: str | None = None,
    *,
    filename: str | None = None,
) -> dict[str, Any]:
    """上传知识库文件。

    :param file_path: 函数处理所需的“文件路径”数据，类型为 ``Path``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :param filename: 发送给后端的原始文件名；临时文件上传时用于保留用户选择的名称。
    :return: 返回上传知识库文件得到的结果，返回类型为 ``dict[str, Any]``。
    """
    with file_path.open("rb") as handle:
        response = requests.post(
            f"{base_url or api_base_url()}/api/knowledge/upload",
            files={"file": (filename or file_path.name, handle)},
            headers=auth_headers(token),
            timeout=120,
        )
    return response_data(response)


def delete_knowledge_doc(doc_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    """删除知识库知识文档。

    :param doc_id: 函数处理所需的“知识文档`id`”数据，类型为 ``int``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :param base_url: 函数处理所需的“基础`url`”数据，类型为 ``str | None``。
    :return: 返回删除知识库知识文档得到的结果，返回类型为 ``dict[str, Any]``。
    """
    response = requests.delete(
        f"{base_url or api_base_url()}/api/knowledge/{doc_id}",
        headers=auth_headers(token),
        timeout=300,
    )
    return response_data(response)
