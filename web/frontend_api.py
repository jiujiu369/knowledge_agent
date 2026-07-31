from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
PAGE_NAMES = ["登录", "对话", "对话记录", "工单", "上传", "账号"]


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


def response_data(response: requests.Response) -> Any:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"接口返回非 JSON：HTTP {response.status_code}") from exc

    if response.status_code >= 400 or payload.get("code") != "ok":
        message = payload.get("message") if isinstance(payload, dict) else response.text
        raise RuntimeError(f"接口调用失败：HTTP {response.status_code}，{message}")
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
            raise RuntimeError(f"接口调用失败：HTTP {response.status_code}，{response.text}")
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
