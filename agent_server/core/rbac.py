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
    """获取角色`tier`。

    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回获取角色`tier`得到的结果，返回类型为 ``str``。
    """
    return "admin" if role == "admin" else "employee"


def available_tools(role: str) -> set[str]:
    """`available``tools`。

    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回`available``tools`得到的结果，返回类型为 ``set[str]``。
    """
    if role_tier(role) == "admin":
        return set(ALL_TOOL_NAMES)
    return set(EMPLOYEE_TOOL_NAMES)


def ensure_tool_allowed(role: str, tool_name: str) -> None:
    """确保工具`allowed`。

    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :param tool_name: 函数处理所需的“工具`name`”数据，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if tool_name not in ALL_TOOL_NAMES:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool_name not in available_tools(role):
        raise HTTPException(status_code=403, detail="tool forbidden")
