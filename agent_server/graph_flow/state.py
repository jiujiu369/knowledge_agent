from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    user: dict[str, Any]
    question: str
    rag_results: list[dict[str, Any]] = field(default_factory=list)
    similar_tickets: list[dict[str, Any]] = field(default_factory=list)
    llm_answer: str = ""
    ticket: dict[str, Any] | None = None
    ticket_suggestion: dict[str, Any] | None = None
    guardrail: dict[str, Any] = field(default_factory=dict)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
