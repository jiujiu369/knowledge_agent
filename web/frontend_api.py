from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
PAGE_NAMES = ["登录", "对话", "对话记录", "工单", "上传", "账号"]
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
    "ticket not found": "工单不存在",
    "admin approval required": "该工单需要管理员审批",
    "unsupported ticket status": "不支持的工单状态",
    "tool not found": "工具不存在",
    "tool forbidden": "当前角色无权使用该工具",
    "unsupported export format": "不支持的导出格式",
    "missing user": "缺少登录用户信息",
    "llm returned empty content": "模型未返回有效内容",
    "local bge model not found": "本地 BGE 模型未找到",
    "local vlm model not found or incomplete": "本地 VLM 模型未找到或不完整",
}


def api_base_url() -> str:
    return os.getenv("KNOWLEDGE_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def resolve_page(selected_page: str, query_page: str | None) -> str:
    if query_page in PAGE_NAMES:
        return str(query_page)
    if selected_page in PAGE_NAMES:
        return selected_page
    return PAGE_NAMES[0]


def parse_sse_events(lines: Iterable[str | bytes]) -> Iterator[dict[str, Any]]:
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


def stringify_error_message(message: Any) -> str:
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
    text = stringify_error_message(message).strip()
    if not text:
        return "请求失败"
    lowered = text.lower()
    for source, target in ERROR_MESSAGE_MAP.items():
        if lowered == source:
            return target
        if source in lowered:
            return text.replace(source, target)
    if any(keyword in lowered for keyword in ("field required", "value error", "input should", "validation error")):
        return "请求参数不合法"
    if any(keyword in lowered for keyword in ("httpconnectionpool", "connection refused", "failed to establish a new connection", "connection aborted")):
        return "无法连接后端服务，请确认后端已启动"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return text
    return f"操作失败：{text}"


def response_data(response: requests.Response) -> Any:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"接口返回非 JSON：HTTP {response.status_code}") from exc

    if response.status_code >= 400 or payload.get("code") != "ok":
        message = payload.get("message") if isinstance(payload, dict) else response.text
        raise RuntimeError(f"接口调用失败：HTTP {response.status_code}，{localize_error_message(message)}")
    return payload.get("data")


def login(username: str, password: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    return response_data(response)


def get_me(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url or api_base_url()}/api/auth/me",
        headers=auth_headers(token),
        timeout=15,
    )
    return response_data(response)


def list_users(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url or api_base_url()}/api/auth/admin/users",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_user(username: str, role: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/admin/users",
        json={"username": username, "role": role},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def reset_user_password(user_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/admin/users/{user_id}/reset-password",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def delete_user(user_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.delete(
        f"{base_url or api_base_url()}/api/auth/admin/users/{user_id}",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def change_password(old_password: str, new_password: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/auth/change-password",
        json={"old_password": old_password, "new_password": new_password},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def stream_chat(message: str, token: str, base_url: str | None = None) -> Iterator[dict[str, Any]]:
    with requests.post(
        f"{base_url or api_base_url()}/api/chat/stream",
        json={"message": message},
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
            raise RuntimeError(f"接口调用失败：HTTP {response.status_code}，{localize_error_message(message_text)}")
        yield from parse_sse_events(response.iter_lines(decode_unicode=True))


def list_chat_history(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url or api_base_url()}/api/chat/history",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def list_tickets(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url or api_base_url()}/api/tickets",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def create_ticket(title: str, content: str, answer: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/tickets",
        json={"title": title, "content": content, "answer": answer},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def update_ticket_status(ticket_id: int, status: str, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.patch(
        f"{base_url or api_base_url()}/api/tickets/{ticket_id}",
        json={"status": status},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def export_ticket_stat(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/tools/export_ticket_stat",
        json={},
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def list_knowledge(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url or api_base_url()}/api/knowledge",
        headers=auth_headers(token),
        timeout=20,
    )
    return response_data(response)


def rebuild_knowledge(token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{base_url or api_base_url()}/api/knowledge/rebuild",
        headers=auth_headers(token),
        timeout=300,
    )
    return response_data(response)


def upload_knowledge_file(file_path: Path, token: str, base_url: str | None = None) -> dict[str, Any]:
    with file_path.open("rb") as handle:
        response = requests.post(
            f"{base_url or api_base_url()}/api/knowledge/upload",
            files={"file": (file_path.name, handle)},
            headers=auth_headers(token),
            timeout=120,
        )
    return response_data(response)


def delete_knowledge_doc(doc_id: int, token: str, base_url: str | None = None) -> dict[str, Any]:
    response = requests.delete(
        f"{base_url or api_base_url()}/api/knowledge/{doc_id}",
        headers=auth_headers(token),
        timeout=300,
    )
    return response_data(response)
