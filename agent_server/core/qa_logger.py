from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "qa_events.jsonl"


def qa_log_path() -> Path:
    """`qa`记录路径。

    :return: 返回`qa`记录路径得到的结果，返回类型为 ``Path``。
    """
    return Path(os.getenv("QA_LOG_PATH", str(DEFAULT_LOG_PATH)))


def log_qa_event(user: dict[str, Any], question: str, result: dict[str, Any]) -> None:
    """记录`qa`事件。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param result: 函数处理所需的“结果”数据，类型为 ``dict[str, Any]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    path = qa_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "user_id": user.get("id"),
        "role": user.get("role"),
        "question": question,
        "answer": str(result.get("answer") or ""),
        "ticket_id": result.get("ticket_id"),
        "retrieval": _compact_retrieval(result.get("retrieval") or []),
        "similar_ticket_count": len(result.get("similar_tickets") or []),
        "guardrail": result.get("guardrail") or {},
        "tool_events": result.get("tool_events") or [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def safe_log_qa_event(user: dict[str, Any], question: str, result: dict[str, Any]) -> None:
    """安全地处理记录`qa`事件。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param result: 函数处理所需的“结果”数据，类型为 ``dict[str, Any]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    try:
        log_qa_event(user, question, result)
    except Exception:
        return


def _compact_retrieval(items: list[Any]) -> list[dict[str, Any]]:
    """`compact``retrieval`。

    :param items: 需要批量处理的数据项，类型为 ``list[Any]``。
    :return: 返回`compact``retrieval`得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    compact: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "doc_id": item.get("doc_id"),
                "score": item.get("score"),
                "source_path": item.get("source_path"),
                "content": str(item.get("content") or "")[:1000],
            }
        )
    return compact
