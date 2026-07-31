from __future__ import annotations

from fastapi import HTTPException


ADMIN_TOOL_NAMES = {"export_ticket_stat", "knowledge_manage"}
EMPLOYEE_TOOL_NAMES = {
    "doc_retrieve",
    "match_similar_ticket",
    "create_consult_ticket",
    "query_ticket_list",
}
ALL_TOOL_NAMES = EMPLOYEE_TOOL_NAMES | ADMIN_TOOL_NAMES


def role_tier(role: str) -> str:
    return "admin" if role == "admin" else "employee"


def available_tools(role: str) -> set[str]:
    if role_tier(role) == "admin":
        return set(ALL_TOOL_NAMES)
    return set(EMPLOYEE_TOOL_NAMES)


def ensure_tool_allowed(role: str, tool_name: str) -> None:
    if tool_name not in ALL_TOOL_NAMES:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool_name not in available_tools(role):
        raise HTTPException(status_code=403, detail="tool forbidden")
