from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "qa_events.jsonl"


def qa_log_path() -> Path:
    return Path(os.getenv("QA_LOG_PATH", str(DEFAULT_LOG_PATH)))


def log_qa_event(user: dict[str, Any], question: str, result: dict[str, Any]) -> None:
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
    try:
        log_qa_event(user, question, result)
    except Exception:
        return


def _compact_retrieval(items: list[Any]) -> list[dict[str, Any]]:
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
